"""
Module 1 — Retrieval
---------------------
Fetches papers from three sources:
  1. arXiv           — always free, no key needed
  2. Semantic Scholar — free API key required (get at semanticscholar.org/product/api)
  3. OpenAlex        — completely free, no key, 250M+ papers indexed

Papers are deduplicated, quality-filtered, and BM25 re-ranked.
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional

import arxiv
import httpx
from rank_bm25 import BM25Okapi
from fuzzywuzzy import fuzz
from groq import Groq
from pipeline._llm import generate_json
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("CACHE_DIR", "data/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SS_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
SS_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OA_SEARCH_URL = "https://api.openalex.org/works"

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_key(topic: str) -> str:
    return hashlib.md5(topic.lower().strip().encode()).hexdigest()

def _load_cache(topic: str) -> Optional[list[dict]]:
    path = CACHE_DIR / f"{_cache_key(topic)}.json"
    if path.exists():
        logger.info(f"Cache hit for topic: '{topic}'")
        return json.loads(path.read_text(encoding="utf-8"))
    return None

def _save_cache(topic: str, papers: list[dict]) -> None:
    path = CACHE_DIR / f"{_cache_key(topic)}.json"
    path.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Cached {len(papers)} papers for topic: '{topic}'")

def _deduplicate(papers: list[dict]) -> list[dict]:
    seen: list[str] = []
    unique: list[dict] = []
    for p in papers:
        title = p.get("title", "")
        if not any(fuzz.ratio(title.lower(), s.lower()) > 88 for s in seen):
            seen.append(title)
            unique.append(p)
    return unique

# ---------------------------------------------------------------------------
# Query expansion via Groq
# ---------------------------------------------------------------------------

def expand_query(topic: str) -> list[str]:
    try:
        prompt = (
            f"Generate 4 alternative academic search queries for the topic: {topic}\n\n"
            f"Rules:\n"
            f"- Each query must be a plain search string (no JSON, no brackets)\n"
            f"- Each query should use different keywords or synonyms\n"
            f"- Return ONLY this exact JSON format, nothing else:\n"
            f'{{"queries": ["first query", "second query", "third query", "fourth query"]}}'
        )
        parsed = generate_json(prompt)
        raw_queries = []
        for v in parsed.values():
            if isinstance(v, list):
                raw_queries = v[:4]
                break

        # Validate: reject any query that looks like a JSON object/nested structure
        clean_queries = []
        for q in raw_queries:
            q = str(q).strip()
            # Skip if model returned JSON instead of a plain string
            if q.startswith("{") or q.startswith("[") or q.startswith("("):
                logger.warning(f"Query expansion: skipping malformed query: {q[:60]}")
                continue
            if len(q) > 10:
                clean_queries.append(q)

        if clean_queries:
            logger.info(f"Expanded queries: {clean_queries}")
            return [topic] + clean_queries

    except Exception as e:
        logger.warning(f"Query expansion failed: {e}. Using original topic only.")
    return [topic]


# ---------------------------------------------------------------------------
# Source 1 — arXiv
# ---------------------------------------------------------------------------

def _fetch_arxiv(query: str, max_results: int = 30, min_year: int = 2018) -> list[dict]:
    papers = []
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        for result in client.results(search):
            year = result.published.year
            if year < min_year:
                continue
            papers.append({
                "arxiv_id": result.entry_id.split("/")[-1],
                "ss_id": None,
                "title": result.title.strip(),
                "abstract": result.summary.strip().replace("\n", " "),
                "authors": [a.name for a in result.authors],
                "year": year,
                "citation_count": 0,
                "influential_citation_count": 0,
                "references": [],
                "pdf_url": result.pdf_url,
                "source": "arxiv",
            })
        logger.info(f"arXiv: {len(papers)} papers for '{query}'")
    except Exception as e:
        logger.error(f"arXiv fetch failed: {e}")
    return papers

# ---------------------------------------------------------------------------
# Source 2 — Semantic Scholar (direct API, with key)
# ---------------------------------------------------------------------------

def _fetch_semantic_scholar(query: str, max_results: int = 30, min_year: int = 2018) -> list[dict]:
    if not SS_API_KEY:
        logger.warning("SEMANTIC_SCHOLAR_API_KEY not set — skipping Semantic Scholar.")
        return []

    headers = {"x-api-key": SS_API_KEY}
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,authors,year,citationCount,influentialCitationCount,references,externalIds,openAccessPdf",
    }
    papers = []
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(SS_SEARCH_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        for item in data.get("data", []):
            if not item.get("abstract") or not item.get("year"):
                continue
            if item["year"] < min_year:
                continue
            arxiv_id = (item.get("externalIds") or {}).get("ArXiv")
            refs = [
                r["paperId"] for r in (item.get("references") or [])
                if r.get("paperId")
            ]
            pdf_url = None
            if item.get("openAccessPdf"):
                pdf_url = item["openAccessPdf"].get("url")

            papers.append({
                "arxiv_id": arxiv_id,
                "ss_id": item.get("paperId"),
                "title": item["title"].strip(),
                "abstract": item["abstract"].strip().replace("\n", " "),
                "authors": [a["name"] for a in (item.get("authors") or [])],
                "year": item["year"],
                "citation_count": item.get("citationCount") or 0,
                "influential_citation_count": item.get("influentialCitationCount") or 0,
                "references": refs[:50],
                "pdf_url": pdf_url,
                "source": "semantic_scholar",
            })
        logger.info(f"Semantic Scholar: {len(papers)} papers for '{query}'")
    except httpx.HTTPStatusError as e:
        logger.error(f"Semantic Scholar HTTP {e.response.status_code}: {e}")
    except Exception as e:
        logger.error(f"Semantic Scholar fetch failed: {e}")
    return papers

# ---------------------------------------------------------------------------
# Source 3 — OpenAlex (free, no key required)
# ---------------------------------------------------------------------------

def _fetch_openalex(query: str, max_results: int = 30, min_year: int = 2018) -> list[dict]:
    """
    OpenAlex: completely free, indexes 250M+ works, no API key needed.
    Uses 'polite pool' (faster) by sending an email in the User-Agent.
    """
    params = {
        "search": query,
        "filter": f"from_publication_date:{min_year}-01-01,type:article",
        "per-page": min(max_results, 50),
        "sort": "relevance_score:desc",
        "select": "id,title,abstract_inverted_index,authorships,publication_year,cited_by_count,doi,open_access,referenced_works",
    }
    headers = {
        # Polite pool — gets higher rate limits (10 req/s vs 1 req/s)
        "User-Agent": "ResearchLens/1.0 (research tool; mailto:research@example.com)",
    }
    papers = []
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(OA_SEARCH_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        for item in data.get("results", []):
            # Reconstruct abstract from inverted index
            abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
            if not abstract:
                continue

            year = item.get("publication_year")
            if not year or year < min_year:
                continue

            authors = [
                a["author"]["display_name"]
                for a in (item.get("authorships") or [])
                if a.get("author")
            ]
            doi = item.get("doi", "")
            pdf_url = None
            oa = item.get("open_access") or {}
            if oa.get("oa_url"):
                pdf_url = oa["oa_url"]

            # Extract arxiv ID from DOI if present
            arxiv_id = None
            if doi and "arxiv" in doi.lower():
                arxiv_id = doi.split("/")[-1]

            papers.append({
                "arxiv_id": arxiv_id,
                "ss_id": None,
                "openalex_id": item.get("id", ""),
                "title": item.get("title", "").strip(),
                "abstract": abstract,
                "authors": authors,
                "year": year,
                "citation_count": item.get("cited_by_count") or 0,
                "influential_citation_count": 0,
                "references": item.get("referenced_works") or [],  # list of OA work IDs
                "pdf_url": pdf_url,
                "source": "openalex",
            })
        logger.info(f"OpenAlex: {len(papers)} papers for '{query}'")
    except Exception as e:
        logger.error(f"OpenAlex fetch failed: {e}")
    return papers


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}. Reconstruct to string."""
    if not inverted_index:
        return ""
    try:
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)
    except Exception:
        return ""

# ---------------------------------------------------------------------------
# BM25 Re-ranking
# ---------------------------------------------------------------------------

def _bm25_rerank(papers: list[dict], topic: str, top_k: int = 50) -> list[dict]:
    if not papers:
        return papers
    tokenized = [p["abstract"].lower().split() for p in papers]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(topic.lower().split())
    ranked = sorted(zip(scores, papers), key=lambda x: x[0], reverse=True)
    selected = [p for _, p in ranked[:top_k]]
    logger.info(f"BM25 re-ranking: {len(papers)} → {len(selected)} papers")
    return selected

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_papers(
    topic: str,
    max_papers: int = 50,
    min_year: int = 2018,
    min_citations: int = 2,
    use_cache: bool = True,
) -> list[dict]:
    """
    Main entry point. Returns deduplicated, BM25-ranked papers from
    arXiv + Semantic Scholar + OpenAlex.
    """
    if use_cache:
        cached = _load_cache(topic)
        if cached:
            return cached

    # Only expand queries when we actually need to fetch new papers.
    # If the cache exists it was already returned above, so we only reach
    # this point on a genuine cache miss — expand_query is worth it here.
    queries = expand_query(topic)
    logger.info(f"Using {len(queries)} search queries across 3 sources.")

    all_papers: list[dict] = []
    for q in queries:
        all_papers.extend(_fetch_arxiv(q, max_results=25, min_year=min_year))
        time.sleep(0.5)
        all_papers.extend(_fetch_semantic_scholar(q, max_results=25, min_year=min_year))
        time.sleep(0.5)
        all_papers.extend(_fetch_openalex(q, max_results=25, min_year=min_year))
        time.sleep(0.5)

    logger.info(f"Total raw papers: {len(all_papers)}")

    all_papers = _deduplicate(all_papers)
    logger.info(f"After dedup: {len(all_papers)}")

    # Quality filter (citation filter only for SS/OA papers; arXiv has no citation data)
    filtered = []
    for p in all_papers:
        if not p.get("abstract"):
            continue
        if p["source"] != "arxiv" and p["citation_count"] < min_citations:
            continue
        filtered.append(p)
    logger.info(f"After quality filter: {len(filtered)}")

    # Step 5: Keyword relevance guard
    # Keep only papers whose abstract contains at least 1 significant topic word.
    # This removes generic NLP papers that slip through on broad queries.
    _STOPWORDS = {"in", "for", "the", "of", "a", "an", "with", "and", "on", "to", "using", "based"}
    topic_keywords = [w.lower() for w in topic.split() if w.lower() not in _STOPWORDS and len(w) > 3]
    if topic_keywords:
        keyword_filtered = [
            p for p in filtered
            if any(kw in p["abstract"].lower() for kw in topic_keywords)
        ]
        # Only apply if it doesn't wipe out too many papers
        if len(keyword_filtered) >= max_papers // 2:
            logger.info(f"After keyword guard: {len(keyword_filtered)} (was {len(filtered)})")
            filtered = keyword_filtered
        else:
            logger.info(f"Keyword guard skipped (would leave only {len(keyword_filtered)} papers)")

    final = _bm25_rerank(filtered, topic, top_k=max_papers)
    for i, p in enumerate(final):
        p["id"] = i

    _save_cache(topic, final)
    return final


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Delete cache first to force a fresh fetch
    cache_file = CACHE_DIR / f"{_cache_key('Retrieval-Augmented Generation in NLP')}.json"
    if cache_file.exists():
        cache_file.unlink()
        print("Cache cleared for fresh test.")

    papers = retrieve_papers("Retrieval-Augmented Generation in NLP", max_papers=30)
    print(f"\nRetrieved {len(papers)} papers")
    sources = {}
    for p in papers:
        sources[p["source"]] = sources.get(p["source"], 0) + 1
    print(f"By source: {sources}")
    for p in papers[:5]:
        print(f"  [{p['year']}] [{p['source']:17s}] {p['title'][:70]}  (citations: {p['citation_count']})")


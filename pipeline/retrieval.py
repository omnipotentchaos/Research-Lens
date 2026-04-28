"""
Module 1 — Retrieval
---------------------
Fetches papers from two sources:
  1. Semantic Scholar — API key required (get at semanticscholar.org/product/api)
  2. OpenAlex        — completely free, no key, 250M+ papers indexed

Papers are deduplicated, quality-filtered, and hybrid BM25+citation re-ranked.
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional

import httpx
from rank_bm25 import BM25Okapi
from fuzzywuzzy import fuzz
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
# Query expansion
# ---------------------------------------------------------------------------

def expand_query(topic: str, log_cb=None) -> tuple[list[str], bool]:
    """
    Returns (queries, is_title_mode).
    Uses the LLM to automatically detect if the query is a specific paper title or a general topic,
    and generates appropriate search queries.
    """
    # Hardcoded map for famous models to guarantee we find their foundational papers
    # regardless of LLM hallucinations.
    canonical_map = {
        "gpt 3": "Language Models are Few-Shot Learners",
        "gpt-3": "Language Models are Few-Shot Learners",
        "resnet": "Deep Residual Learning for Image Recognition",
        "yolo": "You Only Look Once: Unified, Real-Time Object Detection",
        "transformer": "Attention Is All You Need",
        "bert": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "vit": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
        "llama": "LLaMA: Open and Efficient Foundation Language Models",
        "llama 2": "Llama 2: Open Foundation and Fine-Tuned Chat Models",
        "llama 3": "The Llama 3 Herd of Models",
        "dall e": "Zero-Shot Text-to-Image Generation",
        "dall-e": "Zero-Shot Text-to-Image Generation",
        "dalle": "Zero-Shot Text-to-Image Generation",
        "dall e 2": "Hierarchical Text-Conditional Image Generation with CLIP Latents",
        "dall-e 2": "Hierarchical Text-Conditional Image Generation with CLIP Latents",
        "dalle 2": "Hierarchical Text-Conditional Image Generation with CLIP Latents"
    }
    
    clean_topic = topic.lower().strip()
    canonical_title = canonical_map.get(clean_topic)

    try:
        prompt = (
            f"The user entered the following search query: \"{topic}\"\n\n"
            f"Task 1: Determine if this query looks like the title of a specific academic paper, "
            f"or if it is a general research topic.\n"
            f"Task 2: If it is a paper title, extract the core research topic and generate 3 short search queries "
            f"(3-6 words each) that would find RELATED papers. If it is a general topic, generate 2 alternative "
            f"academic search queries using different keywords or synonyms.\n\n"
            f"Rules:\n"
            f"- Return ONLY this exact JSON format, nothing else:\n"
            f'{{\n'
            f'  "is_paper_title": true/false,\n'
            f'  "queries": ["query1", "query2", ...]\n'
            f'}}'
        )

        parsed = generate_json(prompt)
        is_title = bool(parsed.get("is_paper_title", False))
        
        if is_title:
            logger.info(f"LLM detected paper title — switching to 'find related papers' mode")

        raw_queries = parsed.get("queries", [])
        if not isinstance(raw_queries, list):
            raw_queries = []

        if is_title:
            raw_queries = raw_queries[:3]
        else:
            raw_queries = raw_queries[:2]

        # Validate: reject any query that looks like a JSON object/nested structure
        clean_queries = []
        for q in raw_queries:
            q = str(q).strip()
            if q.startswith("{") or q.startswith("[") or q.startswith("("):
                logger.warning(f"Query expansion: skipping malformed query: {q[:60]}")
                continue
            if len(q) > 5:
                clean_queries.append(q)

        if canonical_title:
            is_title = True
            logger.info(f"Hardcoded canonical title applied: {canonical_title}")
            if log_cb: log_cb(f"Detected famous shorthand! Searching for foundational paper: '{canonical_title}'")
            return [canonical_title, topic] + clean_queries, is_title

        if canonical_title:
            is_title = True
            logger.info(f"Hardcoded canonical title applied: {canonical_title}")
            if log_cb: log_cb(f"Detected famous shorthand! Searching for foundational paper: '{canonical_title}'")
            return [canonical_title, topic] + clean_queries, is_title

        if clean_queries:
            logger.info(f"Expanded queries: {clean_queries}")
            if log_cb:
                if is_title:
                    log_cb("Title Mode Active! Generating 'find related papers' queries...")
                else:
                    log_cb("Topic Mode Active! Generating alternative keyword queries...")
                for q in clean_queries:
                    log_cb(f"  → Generated query: {q}")
            return [topic] + clean_queries, is_title

    except Exception as e:
        logger.warning(f"Query expansion failed: {e}. Using original topic only.")
    
    # Fallback heuristic if LLM fails
    is_title_fallback = ":" in topic and len(topic.split()) >= 4
    return [topic], is_title_fallback


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

def _fetch_semantic_scholar(query: str, max_results: int = 30, min_year: int = 2018,
                            sort: str = "Relevance") -> list[dict]:
    """
    sort='Relevance'    — S2's default text-match ranking.
    sort='CitationCount' — highest-cited first (rescues foundational papers
                           whose titles don't overlap with the query).
    """
    if not SS_API_KEY:
        logger.warning("SEMANTIC_SCHOLAR_API_KEY not set — skipping Semantic Scholar.")
        return []

    headers = {"x-api-key": SS_API_KEY}
    params = {
        "query": query,
        "limit": max_results,
        "sort": sort,
        "fields": "title,abstract,authors,year,citationCount,influentialCitationCount,references,externalIds,openAccessPdf",
    }
    papers = []
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(SS_SEARCH_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        for item in data.get("data", []):
            if not item.get("title") or not item.get("year"):
                continue
            if item["year"] < min_year:
                continue

            # Use title as abstract fallback — large technical reports (e.g. "The Llama 3
            # Herd of Models") are often indexed by S2 without an abstract in the API response.
            abstract = (item.get("abstract") or "").strip().replace("\n", " ")
            if not abstract:
                abstract = item["title"].strip()   # fallback so BM25/embedding still works

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
                "abstract": abstract,
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

def _bm25_rerank(
    papers: list[dict],
    topic: str,
    top_k: int = 50,
    alpha: float = 0.65,
    beta: float = 0.35,
) -> list[dict]:
    """
    Hybrid re-ranking: BM25 relevance (alpha) + log-citation score (beta).

    - Topic mode (default):  alpha=0.65, beta=0.35  — relevance-primary
    - Title mode:            alpha=0.30, beta=0.70  — citation-primary
      (when the user pastes a paper title, the most influential paper in that
       research area should always appear near the top regardless of word overlap)

    Log scale is used for citations because the distribution is heavily skewed
    (e.g. GPT-3: 45 000 citations vs a typical paper: 50 citations).
    """
    import math
    if not papers:
        return papers

    # ── BM25 scores ─────────────────────────────────────────────────────────
    tokenized = [p["abstract"].lower().split() for p in papers]
    bm25 = BM25Okapi(tokenized)
    bm25_raw = bm25.get_scores(topic.lower().split())

    bm25_max = max(bm25_raw) if max(bm25_raw) > 0 else 1.0
    bm25_norm = [s / bm25_max for s in bm25_raw]          # → [0, 1]

    # ── Log-citation scores ──────────────────────────────────────────────────
    cite_log = [math.log1p(p.get("citation_count") or 0) for p in papers]
    cite_max = max(cite_log) if max(cite_log) > 0 else 1.0
    cite_norm = [s / cite_max for s in cite_log]           # → [0, 1]

    # ── Hybrid score ─────────────────────────────────────────────────────────
    hybrid = [
        alpha * bm + beta * cn
        for bm, cn in zip(bm25_norm, cite_norm)
    ]

    ranked = sorted(zip(hybrid, papers), key=lambda x: x[0], reverse=True)
    selected = [p for _, p in ranked[:top_k]]

    # ── Influential paper guarantee ───────────────────────────────────────────
    # The user specifically requested: "Whatever I search, it should tell me the top most influential paper."
    # We unconditionally pin the paper with the absolute highest citation count to position 0.
    if selected:
        max_cited = max(selected, key=lambda p: p.get("citation_count", 0))
        if selected[0] != max_cited and max_cited.get("citation_count", 0) > 0:
            current_pos = selected.index(max_cited)
            selected.insert(0, selected.pop(current_pos))
            logger.info(
                f"Pinned most influential paper to top: '{max_cited['title'][:60]}' "
                f"({max_cited['citation_count']} citations)"
            )

    logger.info(
        f"Hybrid re-ranking (BM25×{alpha} + citation×{beta}): "
        f"{len(papers)} → {len(selected)} papers"
    )
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
    log_cb = None,
) -> list[dict]:
    """
    Main entry point. Returns deduplicated, hybrid-ranked papers from
    Semantic Scholar + OpenAlex.

    Automatically detects two modes:
    - Topic mode  (default): user typed a general topic, e.g. 'Graph Neural Networks'
    - Title mode:            user pasted a specific paper title, e.g.
                             'Attention Is All You Need'

    In title mode:
      - min_year is relaxed to 2010 (foundational papers predate 2018)
      - an extra citation-sorted S2 batch is fetched to pin influential papers
      - BM25/citation weights shift to citation-primary (alpha=0.30, beta=0.70)
    """
    if use_cache:
        cached = _load_cache(topic)
        if cached:
            return cached

    # Expand queries + detect mode
    if log_cb: log_cb(f"Expanding query via LLM intent detection...")
    queries, is_title_mode = expand_query(topic, log_cb=log_cb)
    logger.info(f"Mode: {'paper-title' if is_title_mode else 'topic'} | {len(queries)} search queries")

    # In title mode, go back further — landmark papers predate 2018
    effective_min_year = 2010 if is_title_mode else min_year

    all_papers: list[dict] = []

    for q in queries:
        # Standard relevance-sorted fetch from both sources
        all_papers.extend(
            _fetch_semantic_scholar(q, max_results=50, min_year=effective_min_year, sort="Relevance")
        )
        time.sleep(0.5)
        all_papers.extend(
            _fetch_openalex(q, max_results=50, min_year=effective_min_year)
        )
        time.sleep(0.5)

    # Extra citation-sorted S2 batch — always added for the primary query.
    # This guarantees highly-cited foundational papers are captured even when
    # their abstracts don't match query terms well (BM25 blind spot).
    logger.info("Fetching citation-sorted S2 batch to capture influential papers …")
    all_papers.extend(
        _fetch_semantic_scholar(
            queries[0], max_results=30, min_year=effective_min_year, sort="CitationCount"
        )
    )
    time.sleep(0.5)

    logger.info(f"Total raw papers: {len(all_papers)}")

    all_papers = _deduplicate(all_papers)
    logger.info(f"After dedup: {len(all_papers)}")

    # Quality filter — year-aware citation threshold
    from datetime import datetime
    current_year = datetime.now().year
    filtered = []
    for p in all_papers:
        if not p.get("abstract"):
            continue
        paper_year = p.get("year") or 0
        # Relax citation filter for: (a) recent papers, (b) all papers in title mode
        # Title mode already fetches citation-sorted batch so quality is inherent
        if is_title_mode:
            effective_min = 0
        else:
            effective_min = 0 if paper_year >= current_year - 1 else min_citations
        if p["source"] != "arxiv" and p["citation_count"] < effective_min:
            continue
        filtered.append(p)
    logger.info(f"After quality filter: {len(filtered)}")

    # Keyword relevance guard (topic mode only — title mode uses citation-primary ranking)
    if not is_title_mode:
        _STOPWORDS = {"in", "for", "the", "of", "a", "an", "with", "and", "on", "to",
                      "using", "based", "from", "via", "its", "their", "this", "that"}
        import re as _re
        raw_words = [_re.sub(r'[^\w]', '', w) for w in topic.split()]
        raw_words = [w for w in raw_words if w and w.lower() not in _STOPWORDS and len(w) >= 2]

        def _specificity(word: str) -> int:
            has_upper = any(c.isupper() for c in word[1:])
            has_digit = any(c.isdigit() for c in word)
            is_all_caps = word == word.upper() and len(word) <= 6
            boost = 100 if (has_upper or has_digit or is_all_caps) else 0
            return boost + len(word)

        seen = set()
        unique_keywords = []
        for w in [w.lower() for w in sorted(raw_words, key=_specificity, reverse=True)]:
            if w not in seen:
                seen.add(w)
                unique_keywords.append(w)

        if unique_keywords:
            required = unique_keywords[:2] if len(unique_keywords) >= 2 else unique_keywords[:1]
            logger.info(f"Keyword guard — anchors: {required}")

            def _kw_in_paper(p: dict, kw: str) -> bool:
                return (kw in (p.get("abstract") or "").lower() or
                        kw in (p.get("title") or "").lower())

            and_filtered = [p for p in filtered if all(_kw_in_paper(p, kw) for kw in required)]

            if len(and_filtered) >= max_papers // 2:
                logger.info(f"Keyword guard (AND): {len(and_filtered)} papers")
                filtered = and_filtered
            elif len(required) > 1:
                or_filtered = [p for p in filtered if any(_kw_in_paper(p, kw) for kw in required)]
                if len(or_filtered) >= max_papers // 2:
                    logger.info(f"Keyword guard (OR): {len(or_filtered)} papers")
                    filtered = or_filtered
                else:
                    logger.info(f"Keyword guard skipped (OR would leave only {len(or_filtered)})")
            else:
                logger.info(f"Keyword guard skipped (AND left only {len(and_filtered)})")

    # Mode-aware ranking weights
    alpha = 0.30 if is_title_mode else 0.65   # citation-primary for title, relevance-primary for topic
    beta  = 0.70 if is_title_mode else 0.35

    final = _bm25_rerank(filtered, topic, top_k=max_papers, alpha=alpha, beta=beta)
    
    # If in title mode, guarantee the exact paper is at index 0 (overriding the max_cited fallback)
    if is_title_mode:
        target_title = queries[0].lower()
        for i, p in enumerate(final):
            if fuzz.ratio(p["title"].lower(), target_title) > 90:
                if i != 0:
                    final.insert(0, final.pop(i))
                    logger.info(f"Pinned exact title match to top: {p['title']}")
                break

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


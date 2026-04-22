"""
Module 2 — Information Extraction
-----------------------------------
Three-layer extraction for each paper:
  2a. LLM structured extraction via Groq (Llama 3.3 70B) → JSON schema
  2b. spaCy NER → MODEL / DATASET / METRIC entity nodes
  2c. REBEL relation extraction → typed triplets for knowledge graph edges
"""

import os
import re
import json
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import spacy
from groq import Groq
from pipeline._llm import generate_json
from transformers import pipeline as hf_pipeline
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialise models once at import time (heavy — cached after first load)
# ---------------------------------------------------------------------------

_groq_client: Optional[Groq] = None
_rebel_pipeline = None
_spacy_nlp = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


def _get_rebel():
    global _rebel_pipeline
    if _rebel_pipeline is None:
        logger.info("Loading REBEL model (first run: ~1.5 GB download) …")
        _rebel_pipeline = hf_pipeline(
            "text2text-generation",
            model="Babelscape/rebel-large",
            tokenizer="Babelscape/rebel-large",
            device=-1,  # CPU; set to 0 if you have a GPU
        )
        logger.info("REBEL loaded.")
    return _rebel_pipeline


def _get_spacy():
    global _spacy_nlp
    if _spacy_nlp is None:
        try:
            _spacy_nlp = spacy.load("en_core_web_trf")
        except OSError:
            logger.warning("en_core_web_trf not found, falling back to en_core_web_sm")
            _spacy_nlp = spacy.load("en_core_web_sm")
    return _spacy_nlp


# ---------------------------------------------------------------------------
# 2a — LLM Structured Extraction (batched: 5 papers per API call)
# ---------------------------------------------------------------------------

_BATCH_PROMPT = """\
You are a scientific paper analyst. Extract structured information from the following {n} papers.

Return ONLY a valid JSON object with a single key "results" containing an array of exactly {n} objects.
Each object must have exactly these keys:
  method, dataset, task, metrics, metric_values, key_contribution, limitations, future_work

Papers:
{papers_text}
"""

_EMPTY_FIELDS = {
    "method": "", "dataset": "", "task": "", "metrics": "",
    "metric_values": "", "key_contribution": "", "limitations": "", "future_work": "",
}


def _extract_batch_llm(papers: list[dict]) -> list[dict]:
    """Extract fields for a batch of papers using Gemini (JSON mode)."""
    papers_text = ""
    for i, p in enumerate(papers, 1):
        papers_text += f"\n[{i}] Title: {p['title']}\nAbstract: {p['abstract'][:600]}\n"

    prompt = _BATCH_PROMPT.format(n=len(papers), papers_text=papers_text)
    try:
        parsed = generate_json(prompt)
        results = parsed.get("results", [])
        while len(results) < len(papers):
            results.append(_EMPTY_FIELDS.copy())
        return results[:len(papers)]
    except Exception as e:
        logger.warning(f"Batch LLM extraction failed: {e}")
        return [_EMPTY_FIELDS.copy() for _ in papers]


# ---------------------------------------------------------------------------
# Extraction cache
# ---------------------------------------------------------------------------

_EXTRACT_CACHE_FILE = Path(os.getenv("CACHE_DIR", "data/cache")) / "extraction_cache.json"


def _load_extract_cache() -> dict:
    if _EXTRACT_CACHE_FILE.exists():
        return json.loads(_EXTRACT_CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_extract_cache(cache: dict) -> None:
    _EXTRACT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _EXTRACT_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _paper_cache_key(paper: dict) -> str:
    return hashlib.md5(paper["title"].lower().strip().encode()).hexdigest()


# ---------------------------------------------------------------------------
# 2b — spaCy NER
# ---------------------------------------------------------------------------

# Known scientific entities (seed lists — expandable)
_MODEL_SEEDS = {
    "bert", "gpt", "gpt-2", "gpt-3", "gpt-4", "llama", "t5", "bart",
    "roberta", "deberta", "electra", "xlnet", "albert", "lora", "qlora",
    "dpr", "rag", "colbert", "faiss", "bm25", "flare", "realm", "kilt",
    "flan", "palm", "claude", "mistral", "gemini", "falcon", "mpt",
    "specter", "scibert", "longformer", "bigbird", "pegasus",
}
_DATASET_SEEDS = {
    "squad", "triviaqa", "naturalquestions", "hotpotqa", "ms marco",
    "msmarco", "nq", "mmlu", "hellaswag", "winogrande", "arc", "drop",
    "coqa", "quac", "cnn/dailymail", "xsum", "newsqa", "eli5",
    "fever", "boolq", "wikidata", "commonsenseqa", "piqa", "openbookqa",
}
_METRIC_SEEDS = {
    "bleu", "rouge", "rouge-1", "rouge-2", "rouge-l", "f1", "exact match",
    "em", "accuracy", "ndcg", "map", "mrr", "precision", "recall",
    "bertscore", "meteor", "perplexity", "faithfulness",
}


def _extract_with_ner(text: str) -> dict:
    """
    Run spaCy NER + seed-list matching to extract domain entities.
    Returns dict with keys: models, datasets, metrics.
    """
    nlp = _get_spacy()
    doc = nlp(text[:1000])  # limit for speed

    found_models, found_datasets, found_metrics = set(), set(), set()

    # Seed-list scan (case-insensitive)
    lower = text.lower()
    for m in _MODEL_SEEDS:
        if m in lower:
            found_models.add(m.upper() if len(m) <= 4 else m.title())
    for d in _DATASET_SEEDS:
        if d in lower:
            found_datasets.add(d.upper() if len(d) <= 6 else d.title())
    for mt in _METRIC_SEEDS:
        if mt in lower:
            found_metrics.add(mt.upper())

    # spaCy named entities — ORG/PRODUCT often captures model names
    for ent in doc.ents:
        if ent.label_ in ("ORG", "PRODUCT") and 2 < len(ent.text) < 30:
            found_models.add(ent.text)

    return {
        "ner_models": sorted(found_models),
        "ner_datasets": sorted(found_datasets),
        "ner_metrics": sorted(found_metrics),
    }


# ---------------------------------------------------------------------------
# 2c — REBEL Relation Extraction
# ---------------------------------------------------------------------------

def _parse_rebel_output(text: str) -> list[dict]:
    """
    Parse REBEL's linearised triplet output into structured dicts.
    REBEL format: <triplet> head <subj> relation <obj> tail ...
    """
    triplets = []
    # Split on <triplet> tokens
    chunks = re.split(r"<triplet>", text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            # Extract subject
            subj_match = re.search(r"<subj>(.*?)<obj>", chunk, re.DOTALL)
            obj_match = re.search(r"<obj>(.*?)$", chunk, re.DOTALL)
            # The text before <subj> is the relation? No — REBEL format:
            # head_entity <subj> relation <obj> tail_entity
            parts = chunk.split("<subj>")
            head = parts[0].strip()
            if len(parts) < 2:
                continue
            rest = parts[1]
            rel_parts = rest.split("<obj>")
            if len(rel_parts) < 2:
                continue
            relation = rel_parts[0].strip()
            tail = rel_parts[1].strip()
            if head and relation and tail:
                triplets.append({"head": head, "relation": relation, "tail": tail})
        except Exception:
            continue
    return triplets


def _extract_triplets(abstract: str) -> list[dict]:
    """Extract relation triplets from an abstract using REBEL."""
    rebel = _get_rebel()
    try:
        # REBEL works best on individual sentences
        outputs = rebel(
            abstract[:512],
            return_tensors=False,
            return_text=True,
            max_length=512,
        )
        raw = outputs[0]["generated_text"]
        triplets = _parse_rebel_output(raw)
        return triplets
    except Exception as e:
        logger.warning(f"REBEL failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_paper_info(paper: dict, use_rebel: bool = True) -> dict:
    """
    Run all three extraction layers on a single paper.
    Returns paper dict enriched with extraction fields.
    """
    # 2a: LLM
    llm_fields = _extract_with_llm(paper)

    # 2b: NER on title + abstract
    combined_text = paper["title"] + " " + paper["abstract"]
    ner_fields = _extract_with_ner(combined_text)

    # 2c: REBEL (optional — can be slow on CPU)
    triplets = []
    if use_rebel:
        triplets = _extract_triplets(paper["abstract"])

    return {
        **paper,
        **llm_fields,
        **ner_fields,
        "triplets": triplets,
    }


def extract_all_papers(
    papers: list[dict],
    use_rebel: bool = False,
    batch_size: int = 8,    # llama3.1-8b has 8k context — keep batches small to avoid truncation
    max_workers: int = 1,   # fully sequential — no burst risk with the free tier
) -> list[dict]:
    """
    Extract structured info using Cerebras (llama3.1-8b).
    Sequential batches of 8 papers each → ~7 LLM calls for 50 papers.
    Small batch size prevents JSON truncation on the 8k-context model.
    """
    cache = _load_extract_cache()
    enriched: list = [None] * len(papers)

    to_extract_indices = []
    for i, paper in enumerate(papers):
        key = _paper_cache_key(paper)
        if key in cache:
            enriched[i] = {**paper, **cache[key]}
        else:
            to_extract_indices.append(i)

    cached_count = len(papers) - len(to_extract_indices)
    if cached_count:
        logger.info(f"Extraction cache: {cached_count}/{len(papers)} papers already cached")

    if not to_extract_indices:
        # All cached — still run NER on any that are missing it
        for i, paper in enumerate(papers):
            if enriched[i] is not None and "ner_models" not in enriched[i]:
                enriched[i] = {**enriched[i], **_extract_with_ner(paper["title"] + " " + paper["abstract"]), "triplets": []}
        return enriched

    # Build batches
    batches = [
        to_extract_indices[i:i + batch_size]
        for i in range(0, len(to_extract_indices), batch_size)
    ]
    total_batches = len(batches)
    logger.info(f"Extracting {len(to_extract_indices)} uncached papers in {total_batches} batches "
                f"(batch_size={batch_size}, workers={max_workers}) …")

    # Process in rounds of max_workers — sleep between rounds, not between every call
    completed = 0
    for round_start in range(0, total_batches, max_workers):
        round_batches = batches[round_start:round_start + max_workers]
        is_last_round = (round_start + max_workers >= total_batches)

        # Submit round concurrently
        with ThreadPoolExecutor(max_workers=len(round_batches)) as pool:
            future_map = {}
            for b_idx, batch_indices in enumerate(round_batches):
                batch_papers = [papers[i] for i in batch_indices]
                global_b = round_start + b_idx
                logger.info(
                    f"Extracting batch {global_b+1}/{total_batches} "
                    f"({len(batch_papers)} papers): {papers[batch_indices[0]]['title'][:50]} …"
                )
                future_map[pool.submit(_extract_batch_llm, batch_papers)] = batch_indices

            for future in as_completed(future_map):
                batch_indices = future_map[future]
                try:
                    llm_results = future.result()
                except Exception as e:
                    logger.warning(f"Batch failed: {e} — using empty fallback")
                    llm_results = [_EMPTY_FIELDS.copy() for _ in batch_indices]

                for idx, llm_fields in zip(batch_indices, llm_results):
                    paper = papers[idx]
                    ner_fields = _extract_with_ner(paper["title"] + " " + paper["abstract"])
                    triplets = _extract_triplets(paper["abstract"]) if use_rebel else []
                    combined = {**llm_fields, **ner_fields, "triplets": triplets}
                    cache[_paper_cache_key(paper)] = combined
                    enriched[idx] = {**paper, **combined}
                    completed += 1

        _save_extract_cache(cache)

        # Gemini has 1M TPM — no sleep needed between rounds

    # Fill NER for any cached papers that were missing it
    for i, paper in enumerate(papers):
        if enriched[i] is not None and "ner_models" not in enriched[i]:
            enriched[i] = {**enriched[i], **_extract_with_ner(paper["title"] + " " + paper["abstract"]), "triplets": []}

    return enriched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from pipeline.retrieval import retrieve_papers

    papers = retrieve_papers("Retrieval-Augmented Generation", max_papers=5)
    enriched = extract_all_papers(papers, use_rebel=False)  # set True when REBEL downloaded

    for p in enriched:
        print(f"\n{'='*60}")
        print(f"Title   : {p['title'][:70]}")
        print(f"Method  : {p.get('method', 'N/A')}")
        print(f"Dataset : {p.get('dataset', 'N/A')}")
        print(f"Contrib : {p.get('key_contribution', 'N/A')}")
        print(f"NER     : models={p.get('ner_models', [])}")
        print(f"Triplets: {p.get('triplets', [])[:2]}")

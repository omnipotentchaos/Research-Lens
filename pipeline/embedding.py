"""
Module 3a — Semantic Embeddings
---------------------------------
Uses SPECTER2 (AllenAI) to embed papers.
SPECTER2 is trained on citation signals — papers that cite each other
are pulled closer in vector space. Optimal for scientific paper clustering.

Embeddings are cached to disk as .npy files.
"""

import os
import logging
import hashlib
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("CACHE_DIR", "data/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SPECTER2_MODEL = "allenai/specter2_base"


def _papers_hash(papers: list[dict]) -> str:
    """Hash of paper titles — used to detect when paper set has changed."""
    titles = "".join(p.get("title", "") for p in papers)
    return hashlib.md5(titles.encode()).hexdigest()[:10]



_tokenizer = None
_model = None


def _get_device() -> str:
    """Return 'cuda' if CUDA is available AND working, else 'cpu'."""
    if not torch.cuda.is_available():
        return "cpu"
    try:
        # Quick sanity-check — catches driver/CUDA version mismatches early
        t = torch.zeros(1).cuda()
        _ = t @ t
        del t
        return "cuda"
    except Exception as e:
        logger.warning(
            f"CUDA detected but unusable ({e}). "
            "Falling back to CPU. Fix: update your NVIDIA driver to ≥520.06 "
            "for CUDA 11.8 (cu118) PyTorch."
        )
        return "cpu"


def _load_specter2():
    global _tokenizer, _model
    if _tokenizer is None:
        logger.info("Loading SPECTER2 (~500MB first run) …")
        _tokenizer = AutoTokenizer.from_pretrained(SPECTER2_MODEL)
        _model = AutoModel.from_pretrained(SPECTER2_MODEL)
        _model.eval()
        logger.info("SPECTER2 loaded.")
    return _tokenizer, _model


def _embed_batch(texts: list[str], batch_size: int = 16) -> np.ndarray:
    """Embed a list of strings in batches. Returns (N, 768) float32 array."""
    tokenizer, model = _load_specter2()
    device = _get_device()
    model.to(device)
    logger.info(f"SPECTER2 running on: {device.upper()}")

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            outputs = model(**inputs)
            embeddings = outputs.last_hidden_state[:, 0, :]
            all_embeddings.append(embeddings.cpu().numpy())

    return np.vstack(all_embeddings).astype(np.float32)


def _cache_path(papers: list[dict], field: str) -> Path:
    """Cache path includes a hash of the paper set — auto-invalidates on paper changes."""
    return CACHE_DIR / f"embeddings_{_papers_hash(papers)}_{field}.npy"


def embed_papers(
    papers: list[dict],
    topic: str,
    field: str = "abstract",
) -> np.ndarray:
    """
    Generate SPECTER2 embeddings for a list of papers.

    Args:
        papers: Enriched paper dicts (must have 'title' and 'abstract').
        topic: Used for cache file naming.
        field: One of 'abstract', 'contribution', 'combined'.
                'combined' averages abstract and key_contribution embeddings.

    Returns:
        numpy array of shape (N, 768).
    """
    cache = _cache_path(papers, field)
    if cache.exists():
        logger.info(f"Embedding cache hit: {cache.name}")
        return np.load(str(cache))

    logger.info(f"Embedding {len(papers)} papers with SPECTER2 (field='{field}') …")

    if field == "abstract":
        # SPECTER2 expected format: "title [SEP] abstract"
        texts = [
            p["title"].strip() + " [SEP] " + p["abstract"].strip()
            for p in papers
        ]
        embeddings = _embed_batch(texts)

    elif field == "contribution":
        texts = [
            p["title"].strip() + " [SEP] " + p.get("key_contribution", p["abstract"]).strip()
            for p in papers
        ]
        embeddings = _embed_batch(texts)

    elif field == "combined":
        # Average of abstract embedding and contribution embedding
        texts_abs = [
            p["title"].strip() + " [SEP] " + p["abstract"].strip()
            for p in papers
        ]
        texts_con = [
            p["title"].strip() + " [SEP] " + p.get("key_contribution", p["abstract"]).strip()
            for p in papers
        ]
        emb_abs = _embed_batch(texts_abs)
        emb_con = _embed_batch(texts_con)
        embeddings = (emb_abs + emb_con) / 2.0

    else:
        raise ValueError(f"Unknown field: {field}. Choose 'abstract', 'contribution', or 'combined'.")

    np.save(str(cache), embeddings)
    logger.info(f"Embeddings saved → {cache.name}  shape={embeddings.shape}")
    return embeddings


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from pipeline.retrieval import retrieve_papers
    from pipeline.extraction import extract_all_papers

    papers = retrieve_papers("Retrieval-Augmented Generation", max_papers=10)
    papers = extract_all_papers(papers, use_rebel=False)
    embs = embed_papers(papers, topic="Retrieval-Augmented Generation", field="combined")
    print(f"Embeddings shape: {embs.shape}")
    print(f"Sample norms: {np.linalg.norm(embs[:3], axis=1)}")

"""
Module 6 — Gap Detection (Novel Contribution)
-----------------------------------------------
Three-pronged approach:

Prong 1 — Geometric gaps:
  KDE over UMAP 2D space → low-density zones = no papers explored here.
  Cluster boundary regions = unexplored intersections between directions.
  e.g., "nobody has combined RAG with multilingual NER"

Prong 2 — Linguistic gaps:
  Extract all "future work" / "limitation" sentences from every paper.
  Embed + cluster those sentences → the research community's own stated gaps.

Prong 3 — LLM synthesis:
  Feed cluster summaries + geometric gaps + linguistic gaps to Groq.
  Output: ranked list of actionable, non-obvious research gaps.
"""

import os
import re
import json
import logging
import numpy as np
from collections import defaultdict
from typing import Optional

from scipy.stats import gaussian_kde
from sklearn.metrics.pairwise import euclidean_distances
from groq import Groq
from pipeline._llm import generate_json
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


# ---------------------------------------------------------------------------
# Prong 1 — Geometric Gap Detection
# ---------------------------------------------------------------------------

def detect_geometric_gaps(
    reduced_2d: np.ndarray,
    labels: np.ndarray,
    clusters: dict,
    grid_resolution: int = 80,
    n_gaps: int = 8,
) -> list[dict]:
    """
    Find low-density and boundary regions in the UMAP 2D embedding space.

    Steps:
      1. Fit KDE over all paper positions
      2. Sample a grid → find lowest-density points
      3. For each low-density point, find the 2 nearest cluster centroids
         → that point is a gap "between" those clusters

    Returns:
        List of gap dicts with cluster pair and position.
    """
    if len(reduced_2d) < 5:
        return []

    # Fit KDE
    kde = gaussian_kde(reduced_2d.T, bw_method="scott")

    # Create sampling grid
    x_min, x_max = reduced_2d[:, 0].min() - 1, reduced_2d[:, 0].max() + 1
    y_min, y_max = reduced_2d[:, 1].min() - 1, reduced_2d[:, 1].max() + 1
    xx, yy = np.mgrid[
        x_min:x_max:complex(grid_resolution),
        y_min:y_max:complex(grid_resolution),
    ]
    grid_points = np.vstack([xx.ravel(), yy.ravel()]).T
    density = kde(grid_points.T)

    # Exclude border of grid (less meaningful)
    border_mask = (
        (grid_points[:, 0] > x_min + 0.5)
        & (grid_points[:, 0] < x_max - 0.5)
        & (grid_points[:, 1] > y_min + 0.5)
        & (grid_points[:, 1] < y_max - 0.5)
    )
    inner_points = grid_points[border_mask]
    inner_density = density[border_mask]

    # Sort by density (ascending) → lowest density = most unexplored
    sorted_idx = np.argsort(inner_density)
    top_sparse = inner_points[sorted_idx[:n_gaps * 3]]  # oversample, deduplicate

    # Get cluster centroids (exclude noise)
    centroids = {}
    for cid, c in clusters.items():
        if not c.get("is_noise") and c.get("centroid_2d"):
            centroids[int(cid)] = np.array(c["centroid_2d"])

    if len(centroids) < 2:
        return []

    centroid_array = np.array(list(centroids.values()))
    centroid_ids = list(centroids.keys())

    gaps = []
    seen_pairs = set()

    for point in top_sparse:
        dists = euclidean_distances([point], centroid_array)[0]
        nearest_two = np.argsort(dists)[:2]
        cid_a = centroid_ids[nearest_two[0]]
        cid_b = centroid_ids[nearest_two[1]]
        pair = tuple(sorted([cid_a, cid_b]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        label_a = clusters[cid_a]["label"]
        label_b = clusters[cid_b]["label"]

        gaps.append({
            "type": "geometric",
            "cluster_a": cid_a,
            "cluster_b": cid_b,
            "label_a": label_a,
            "label_b": label_b,
            "description": f"Unexplored intersection between '{label_a}' and '{label_b}'",
            "position_2d": point.tolist(),
        })

        if len(gaps) >= n_gaps:
            break

    logger.info(f"Geometric gaps found: {len(gaps)}")
    return gaps


# ---------------------------------------------------------------------------
# Prong 2 — Linguistic Gap Detection
# ---------------------------------------------------------------------------

_GAP_KEYWORDS = [
    "future work", "future direction", "future research",
    "limitation", "challenge", "open problem", "remains to be",
    "not addressed", "needs further", "left for future", "open question",
    "unexplored", "to the best of our knowledge", "we leave",
]


def extract_future_work_sentences(papers: list[dict]) -> list[dict]:
    """
    Extract sentences containing future-work / limitation language from
    each paper's abstract + future_work LLM field.

    Returns:
        List of {paper_id, paper_title, sentence, year}
    """
    sentences = []
    for paper in papers:
        def _to_str(v) -> str:
            if isinstance(v, list): return " ".join(str(x) for x in v)
            return str(v) if v else ""
        text = _to_str(paper.get("abstract")) + " " + _to_str(paper.get("future_work")) + " " + _to_str(paper.get("limitations"))
        # Simple sentence split
        raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        for sent in raw_sentences:
            lower = sent.lower()
            if any(kw in lower for kw in _GAP_KEYWORDS) and len(sent.split()) > 8:
                sentences.append({
                    "paper_id": paper["id"],
                    "paper_title": paper["title"],
                    "sentence": sent.strip(),
                    "year": paper.get("year"),
                })
    logger.info(f"Extracted {len(sentences)} future-work sentences")
    return sentences


def cluster_gap_sentences(sentences: list[dict], n_clusters: int = 5) -> list[dict]:
    """
    Cluster future-work sentences using simple TF-IDF + KMeans
    (lighter than SPECTER2 for short sentences).

    Returns:
        List of gap clusters with representative sentences.
    """
    if len(sentences) < 3:
        return []

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans

    texts = [s["sentence"] for s in sentences]
    n_clusters = min(n_clusters, len(texts))

    vectorizer = TfidfVectorizer(max_features=500, stop_words="english")
    X = vectorizer.fit_transform(texts)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    cluster_ids = km.fit_predict(X)

    # Group by cluster
    cluster_groups: dict[int, list] = defaultdict(list)
    for sent, cid in zip(sentences, cluster_ids):
        cluster_groups[int(cid)].append(sent)

    gap_clusters = []
    for cid, sents in cluster_groups.items():
        # Pick most representative (closest to centroid)
        gap_clusters.append({
            "type": "linguistic",
            "cluster_id": cid,
            "representative_sentences": [s["sentence"] for s in sents[:3]],
            "source_papers": list({s["paper_title"] for s in sents}),
            "sentence_count": len(sents),
        })

    return gap_clusters


# ---------------------------------------------------------------------------
# Prong 3 — LLM Synthesis
# ---------------------------------------------------------------------------

def synthesize_gaps_with_llm(
    topic: str,
    clusters: dict,
    geometric_gaps: list[dict],
    linguistic_clusters: list[dict],
    seminal_papers: list[dict],
) -> list[dict]:
    """
    Feed all gathered evidence to the LLM and ask for ranked gap synthesis.
    Prompt is intentionally short to stay within llama3.1-8b's 8k context.
    """
    # Keep summaries short — 8B model has limited context
    cluster_lines = [
        f"- {c['label']} ({c['paper_count']} papers)"
        for cid, c in clusters.items()
        if not c.get("is_noise")
    ][:6]

    geo_lines = [
        f"- {g['description']}"
        for g in geometric_gaps[:3]
    ]

    ling_lines = [
        f"- {gc['representative_sentences'][0][:120]}"
        for gc in linguistic_clusters[:4]
        if gc.get("representative_sentences")
    ]

    prompt = f"""You are a research analyst. Identify 5 research gaps for the topic: "{topic}"

EXISTING CLUSTERS: {chr(10).join(cluster_lines) or "None"}

UNEXPLORED AREAS: {chr(10).join(geo_lines) or "None"}

STATED LIMITATIONS BY AUTHORS: {chr(10).join(ling_lines) or "None"}

Return a JSON object with a single key "gaps" containing an array of exactly 5 objects.
Each object must have these exact keys:
- title: gap name in 5-8 words
- description: 1-2 sentences on what is missing
- why_it_matters: 1 sentence
- suggested_methods: 1 sentence
- difficulty: one of low, medium, high
- gap_type: one of methodological, dataset, evaluation, application, cross-domain

Example format:
{{"gaps": [{{"title": "Example Gap Title Here", "description": "...", "why_it_matters": "...", "suggested_methods": "...", "difficulty": "medium", "gap_type": "methodological"}}]}}"""

    try:
        raw = generate_json(prompt)
        logger.info(f"Gap synthesis raw: type={type(raw).__name__}, preview={str(raw)[:200]}")

        # Handle both array and wrapped object responses
        if isinstance(raw, list):
            gaps = raw
        elif isinstance(raw, dict):
            # Look for any value that is a list (handles "gaps", "research_gaps", etc.)
            gaps = next((v for v in raw.values() if isinstance(v, list)), [])
        else:
            gaps = []

        # Filter out any malformed gap objects
        valid_gaps = [g for g in gaps if isinstance(g, dict) and "title" in g]

        # Add rank
        for i, g in enumerate(valid_gaps):
            g["rank"] = i + 1

        logger.info(f"LLM synthesised {len(valid_gaps)} research gaps")
        return valid_gaps
    except Exception as e:
        logger.error(f"LLM gap synthesis failed: {e}")
        return []



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_gaps(
    topic: str,
    papers: list[dict],
    reduced_2d: np.ndarray,
    labels: np.ndarray,
    clusters: dict,
    seminal_papers: list[dict],
) -> dict:
    """
    Full gap detection pipeline: geometric + linguistic + LLM synthesis.

    Returns:
        {geometric_gaps, linguistic_gaps, synthesized_gaps, future_work_sentences}
    """
    logger.info("Running gap detection …")

    # Prong 1
    geo_gaps = detect_geometric_gaps(reduced_2d, labels, clusters)

    # Prong 2
    fw_sentences = extract_future_work_sentences(papers)
    ling_clusters = cluster_gap_sentences(fw_sentences)

    # Prong 3
    synthesized = synthesize_gaps_with_llm(
        topic=topic,
        clusters=clusters,
        geometric_gaps=geo_gaps,
        linguistic_clusters=ling_clusters,
        seminal_papers=seminal_papers,
    )

    return {
        "geometric_gaps": geo_gaps,
        "linguistic_gap_clusters": ling_clusters,
        "synthesized_gaps": synthesized,
        "future_work_sentence_count": len(fw_sentences),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from pipeline.retrieval import retrieve_papers
    from pipeline.extraction import extract_all_papers
    from pipeline.embedding import embed_papers
    from pipeline.clustering import run_clustering
    from pipeline.knowledge_graph import build_and_export_graph
    import numpy as np

    topic = "Retrieval-Augmented Generation"
    papers = retrieve_papers(topic, max_papers=25)
    papers = extract_all_papers(papers, use_rebel=False)
    embs = embed_papers(papers, topic=topic)
    cluster_result = run_clustering(papers, embs)
    kg_result = build_and_export_graph(papers, cluster_result)

    reduced = np.array(cluster_result["reduced_2d"])
    labels = np.array(cluster_result["labels"])

    gaps = detect_gaps(
        topic=topic,
        papers=papers,
        reduced_2d=reduced,
        labels=labels,
        clusters=cluster_result["clusters"],
        seminal_papers=kg_result["seminal_papers"],
    )

    print(f"\nGeometric gaps: {len(gaps['geometric_gaps'])}")
    print(f"Linguistic gap clusters: {len(gaps['linguistic_gap_clusters'])}")
    print(f"\nSynthesized gaps:")
    for g in gaps["synthesized_gaps"]:
        print(f"  #{g['rank']} [{g['difficulty']}] {g['title']}")
        print(f"    → {g['description'][:100]}")

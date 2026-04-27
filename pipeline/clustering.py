"""
Module 3b — Clustering
------------------------
UMAP dimensionality reduction → HDBSCAN clustering → LLM cluster labeling.

Key design decisions:
- UMAP with cosine metric (best for high-dim text vectors)
- HDBSCAN: no K to specify, handles noise (label = -1), arbitrary cluster shapes
- Silhouette + Davies-Bouldin scores for quantitative evaluation (goes in report)
- Groq LLM auto-labels each cluster with a 3-5 word theme name
"""

import os
import json
import logging
import numpy as np
from typing import Optional

import umap
import hdbscan
from sklearn.metrics import silhouette_score, davies_bouldin_score
from pipeline._llm import generate_text, generate_json
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UMAP Reduction
# ---------------------------------------------------------------------------

def reduce_dimensions(
    embeddings: np.ndarray,
    n_components: int = 2,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    random_state: int = 42,
) -> np.ndarray:
    """
    Reduce high-dimensional embeddings to 2D via UMAP (for clustering + viz).

    Args:
        embeddings: (N, 768) array from SPECTER2.
        n_components: Target dimensions (2 for visualization).

    Returns:
        (N, 2) reduced array.
    """
    logger.info(f"Running UMAP: {embeddings.shape} → ({embeddings.shape[0]}, {n_components})")
    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=min(n_neighbors, len(embeddings) - 1),
        min_dist=min_dist,
        metric="cosine",
        random_state=random_state,
        low_memory=False,
    )
    reduced = reducer.fit_transform(embeddings)
    logger.info("UMAP reduction complete.")
    return reduced.astype(np.float32)


# ---------------------------------------------------------------------------
# HDBSCAN Clustering
# ---------------------------------------------------------------------------

def cluster_papers(
    reduced: np.ndarray,
    min_cluster_size: int = 3,
    min_samples: int = 2,
) -> tuple[np.ndarray, hdbscan.HDBSCAN]:
    """
    Cluster papers using HDBSCAN on the UMAP-reduced embeddings.

    Args:
        reduced: (N, 2) UMAP-reduced embeddings.
        min_cluster_size: Minimum papers per cluster.

    Returns:
        (labels array, fitted HDBSCAN object)
        Labels: -1 = noise/outlier, 0+ = cluster ID.
    """
    logger.info(f"Running HDBSCAN (min_cluster_size={min_cluster_size}) …")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )
    labels = clusterer.fit_predict(reduced)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int(np.sum(labels == -1))
    logger.info(f"HDBSCAN: {n_clusters} clusters, {n_noise} noise points")
    return labels, clusterer


# ---------------------------------------------------------------------------
# Evaluation Metrics
# ---------------------------------------------------------------------------

def evaluate_clustering(reduced: np.ndarray, labels: np.ndarray) -> dict:
    """
    Compute standard clustering evaluation metrics.
    These go directly into your project report.
    """
    # Only evaluate on non-noise points
    mask = labels != -1
    if mask.sum() < 2 or len(set(labels[mask])) < 2:
        return {"silhouette": None, "davies_bouldin": None, "n_clusters": 0, "n_noise": int(np.sum(~mask))}

    sil = float(silhouette_score(reduced[mask], labels[mask]))
    db = float(davies_bouldin_score(reduced[mask], labels[mask]))
    n_clusters = len(set(labels[mask]))
    n_noise = int(np.sum(~mask))

    logger.info(f"Silhouette={sil:.3f}  Davies-Bouldin={db:.3f}  Clusters={n_clusters}  Noise={n_noise}")
    return {
        "silhouette": sil,           # higher is better (range -1 to 1)
        "davies_bouldin": db,        # lower is better
        "n_clusters": n_clusters,
        "n_noise": n_noise,
    }


# ---------------------------------------------------------------------------
# Cluster Label Generation via LLM
# ---------------------------------------------------------------------------

def _label_all_clusters(cluster_groups: dict[int, list[dict]]) -> dict[int, str]:
    """
    Label ALL clusters in a single Cerebras call.
    Saves N-1 API calls vs calling once per cluster.
    Returns {cluster_id: label_string}
    """
    lines = []
    for cid, papers in sorted(cluster_groups.items()):
        titles = [p["title"] for p in papers[:5]]
        lines.append(f"Cluster {cid}:\n" + "\n".join(f"  - {t}" for t in titles))

    prompt = (
        "Below are groups of academic paper titles, each belonging to the same research cluster.\n"
        "For each cluster, provide a concise 2-5 word theme label.\n\n"
        + "\n\n".join(lines)
        + "\n\nReturn ONLY a JSON object like: "
        '{\"0\": \"Theme Label\", \"1\": \"Another Theme\", ...}'
    )
    try:
        result = generate_json(prompt)
        return {int(k): str(v) for k, v in result.items()}
    except Exception as e:
        logger.warning(f"Batch cluster labeling failed: {e}")
        return {cid: f"Cluster {cid}" for cid in cluster_groups}


def label_clusters(
    papers: list[dict],
    labels,
    reduced,
) -> dict[int, dict]:
    """
    Generate LLM labels for each cluster in ONE batched Cerebras call.
    Returns {cluster_id: {label, paper_ids, centroid, paper_count}}
    """
    cluster_ids = sorted(set(labels))
    cluster_map: dict[int, dict] = {}

    # Build per-cluster paper lists (sorted by proximity to centroid)
    cluster_groups: dict[int, list[dict]] = {}
    cluster_meta: dict[int, dict] = {}

    for cid in cluster_ids:
        mask = labels == cid
        cluster_papers = [papers[i] for i in range(len(papers)) if mask[i]]
        cluster_reduced = reduced[mask]
        centroid = cluster_reduced.mean(axis=0).tolist()
        dists = ((cluster_reduced - cluster_reduced.mean(axis=0)) ** 2).sum(axis=1) ** 0.5
        sorted_papers = [cluster_papers[i] for i in dists.argsort()]

        cluster_meta[int(cid)] = {
            "centroid": centroid,
            "mask_sum": int(mask.sum()),
            "paper_ids": [p["id"] for p in cluster_papers],
            "is_noise": cid == -1,
        }
        if cid != -1:
            cluster_groups[int(cid)] = sorted_papers

    # Single batched LLM call for all non-noise clusters
    labels_map = _label_all_clusters(cluster_groups) if cluster_groups else {}

    for cid in cluster_ids:
        meta = cluster_meta[int(cid)]
        label = "Noise / Outliers" if cid == -1 else labels_map.get(int(cid), f"Cluster {cid}")
        cluster_map[int(cid)] = {
            "cluster_id": int(cid),
            "label": label,
            "paper_count": meta["mask_sum"],
            "paper_ids": meta["paper_ids"],
            "centroid_2d": meta["centroid"],
            "is_noise": meta["is_noise"],
        }
        logger.info(f"Cluster {cid:2d} ({meta['mask_sum']:3d} papers): {label}")

    return cluster_map



# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

def run_clustering(
    papers: list[dict],
    embeddings: np.ndarray,
    min_cluster_size: int = 3,
) -> dict:
    """
    Run full UMAP → HDBSCAN → LLM labeling pipeline.

    Returns:
        {reduced_2d, labels, clusters, metrics}
    """
    # Reduce
    reduced = reduce_dimensions(embeddings)

    # Cluster
    labels, clusterer = cluster_papers(reduced, min_cluster_size=min_cluster_size)

    # Evaluate
    metrics = evaluate_clustering(reduced, labels)

    # Label
    clusters = label_clusters(papers, labels, reduced)

    return {
        "reduced_2d": reduced.tolist(),    # serializable
        "labels": labels.tolist(),
        "clusters": clusters,
        "clustering_metrics": metrics,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from pipeline.retrieval import retrieve_papers
    from pipeline.extraction import extract_all_papers
    from pipeline.embedding import embed_papers

    topic = "Graph neural networks"
    papers = retrieve_papers(topic, max_papers=20)
    papers = extract_all_papers(papers, use_rebel=False)
    embeddings = embed_papers(papers, topic=topic, field="combined")
    result = run_clustering(papers, embeddings)

    print(f"\nClustering metrics: {result['clustering_metrics']}")
    for cid, c in result["clusters"].items():
        print(f"  [{cid}] {c['label']}  ({c['paper_count']} papers)")

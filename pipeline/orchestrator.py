"""
Orchestrator — Runs the full ResearchLens pipeline end-to-end.
Chains: Retrieval → Extraction → Embedding & Clustering →
        Temporal Analysis → Gap Detection → unified JSON output.

Five discrete modules. Knowledge Graph removed (not in production pipeline).
"""

import logging
import time
import numpy as np
from pathlib import Path

from pipeline.retrieval import retrieve_papers
from pipeline.extraction import extract_all_papers
from pipeline.embedding import embed_papers
from pipeline.clustering import run_clustering
from pipeline.temporal import analyze_temporal
# knowledge_graph import removed — KG not part of the 5-module pipeline
from pipeline.gap_detection import detect_gaps

logger = logging.getLogger(__name__)


def run_pipeline(
    topic: str,
    max_papers: int = 40,
    min_year: int = 2018,
    use_rebel: bool = False,
    use_cache: bool = True,
    on_progress=None,   # callable(step: str, pct: int)
) -> dict:
    """
    Run the full ResearchLens pipeline for a given research topic.

    Args:
        topic: e.g. "Retrieval-Augmented Generation in NLP"
        max_papers: Papers to retrieve (after BM25 re-ranking).
        min_year: Earliest paper year to include.
        use_rebel: Whether to run REBEL relation extraction (slow on CPU).
        use_cache: Use cached retrieval + embeddings if available.

    Returns:
        Unified JSON-serialisable dict with all pipeline outputs.
    """
    def _progress(step: str, pct: int, log_msg: str = None):
        if on_progress:
            on_progress(step, pct, log_msg)

    def _log(msg: str):
        if on_progress:
            on_progress(None, None, msg)

    t0 = time.time()
    logger.info(f"\n{'='*60}\nResearchLens Pipeline\nTopic: {topic}\n{'='*60}")

    # ── Module 1: Retrieval ────────────────────────────────────────
    _progress("Retrieving papers …", 5)
    _log(f"Starting semantic retrieval for: {topic}")
    logger.info("\n[1/5] Retrieving papers …")
    papers = retrieve_papers(topic, max_papers=max_papers, min_year=min_year, use_cache=use_cache, log_cb=_log)
    _log(f"Kept {len(papers)} papers after BM25 re-ranking")
    logger.info(f"  ✓ {len(papers)} papers retrieved")

    if not papers:
        return {"error": "No papers found. Try a broader topic.", "topic": topic}

    # ── Module 2: Extraction ───────────────────────────────────────
    _progress("Extracting information …", 18)
    _log("Initializing NLP extraction pipeline ...")
    logger.info("\n[2/5] Extracting information …")
    papers = extract_all_papers(papers, use_rebel=use_rebel)
    _log("Finished concept/keyword extraction")
    logger.info(f"  ✓ Extraction complete ({len(papers)} papers)")

    # ── Module 3: Embeddings + Clustering ─────────────────────────
    _progress("Embedding + Clustering …", 40)
    _log("Generating semantic embeddings via SPECTER2 ...")
    logger.info("\n[3/5] Embedding + Clustering …")
    embeddings = embed_papers(papers, topic=topic, field="combined")
    _log("Running HDBSCAN spatial clustering ...")
    cluster_result = run_clustering(papers, embeddings)
    logger.info(
        f"  ✓ {cluster_result['clustering_metrics']['n_clusters']} clusters | "
        f"silhouette={cluster_result['clustering_metrics'].get('silhouette', 'N/A')}"
    )

    # ── Module 4: Temporal Analysis ───────────────────────────────
    _progress("Temporal analysis …", 60)
    _log("Analyzing historical trajectory & semantic shifts ...")
    logger.info("\n[4/5] Temporal analysis …")
    temporal = analyze_temporal(papers, embeddings)
    logger.info(f"  ✓ {len(temporal['timeline'])} years analysed")

    # ── Seminal paper identification (from clustering output) ──────
    # Top papers by citation count that appear across the most clusters.
    # Replaces the removed Knowledge Graph / PageRank approach.
    cluster_map = cluster_result["clusters"]
    paper_cluster: dict[int, int] = {}
    for cid_str, c in cluster_map.items():
        if not c.get("is_noise"):
            for pid in c.get("paper_ids", []):
                paper_cluster[pid] = int(cid_str)
    seminal = sorted(
        [p for p in papers if p.get("citation_count", 0) > 0],
        key=lambda p: p.get("citation_count", 0),
        reverse=True,
    )[:10]
    logger.info(f"  ✓ {len(seminal)} seminal papers identified by citation count")

    # ── Module 5: Gap Detection ────────────────────────────────────
    _progress("Detecting research gaps …", 88)
    _log("Synthesizing research gaps via LLM analysis ...")
    logger.info("\n[5/5] Detecting research gaps …")
    reduced_2d = np.array(cluster_result["reduced_2d"])
    labels_arr = np.array(cluster_result["labels"])
    gaps = detect_gaps(
        topic=topic,
        papers=papers,
        reduced_2d=reduced_2d,
        labels=labels_arr,
        clusters=cluster_result["clusters"],
        seminal_papers=seminal,
    )
    logger.info(f"  ✓ {len(gaps['synthesized_gaps'])} research gaps identified")

    elapsed = round(time.time() - t0, 1)
    logger.info(f"\n{'='*60}\nPipeline complete in {elapsed}s\n{'='*60}")

    # ── Unified output ─────────────────────────────────────────────
    return {
        "topic": topic,
        "metadata": {
            "paper_count": len(papers),
            "year_range": [
                min(p["year"] for p in papers if p.get("year")),
                2026,
            ],
            "cluster_count": cluster_result["clustering_metrics"]["n_clusters"],
            "seminal_paper_count": len(seminal),
            "pipeline_time_seconds": elapsed,
        },
        # Core outputs
        "papers": papers,
        "clusters": cluster_result["clusters"],
        "clustering_metrics": cluster_result["clustering_metrics"],
        "reduced_2d": cluster_result["reduced_2d"],   # for UMAP scatter plot
        "labels": cluster_result["labels"],
        # Temporal
        "temporal": temporal,
        # Seminal papers (top-cited, used as gap detection anchors)
        "seminal_papers": seminal,
        # Gap detection
        "gaps": gaps,
    }


if __name__ == "__main__":
    import json

    class _NumpyEncoder(json.JSONEncoder):
        """Handles numpy scalar/array types that json.dumps can't serialize."""
        def default(self, obj):
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    result = run_pipeline(
        topic="Prompt Injection in Large Language Models",
        max_papers=50,
        use_rebel=False,
        use_cache=True,
    )

    # Save full output
    out_path = Path("data/pipeline_output.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove non-serialisable items for JSON dump
    serialisable = {k: v for k, v in result.items() if k != "papers"}
    serialisable["paper_count"] = len(result.get("papers", []))

    out_path.write_text(json.dumps(serialisable, indent=2, ensure_ascii=False, cls=_NumpyEncoder), encoding="utf-8")
    print(f"\nFull output saved → {out_path}")

    print("\n=== SUMMARY ===")
    m = result.get("metadata", {})
    print(f"Papers      : {m.get('paper_count')}")
    print(f"Clusters    : {m.get('cluster_count')}")
    print(f"Seminal     : {m.get('seminal_paper_count')}")
    print(f"Time        : {m.get('pipeline_time_seconds')}s")

    print("\nResearch gaps:")
    for g in result.get("gaps", {}).get("synthesized_gaps", []):
        print(f"  #{g['rank']} [{g['difficulty']}] {g['title']}")

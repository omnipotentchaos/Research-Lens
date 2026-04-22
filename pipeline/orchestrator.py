"""
Orchestrator — Runs the full ResearchLens pipeline end-to-end.
Chains: Retrieval → Extraction → Embedding → Clustering →
        Temporal → Knowledge Graph → Gap Detection → unified JSON output.
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
from pipeline.knowledge_graph import build_and_export_graph
from pipeline.gap_detection import detect_gaps

logger = logging.getLogger(__name__)


def run_pipeline(
    topic: str,
    max_papers: int = 40,
    min_year: int = 2018,
    use_rebel: bool = False,
    use_cache: bool = True,
    output_dir: str = "data",
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
        output_dir: Directory to save knowledge graph HTML.

    Returns:
        Unified JSON-serialisable dict with all pipeline outputs.
    """
    def _progress(step: str, pct: int):
        if on_progress:
            on_progress(step, pct)

    t0 = time.time()
    logger.info(f"\n{'='*60}\nResearchLens Pipeline\nTopic: {topic}\n{'='*60}")

    # ── Module 1: Retrieval ────────────────────────────────────────
    _progress("Retrieving papers …", 5)
    logger.info("\n[1/6] Retrieving papers …")
    papers = retrieve_papers(topic, max_papers=max_papers, min_year=min_year, use_cache=use_cache)
    logger.info(f"  ✓ {len(papers)} papers retrieved")

    if not papers:
        return {"error": "No papers found. Try a broader topic.", "topic": topic}

    # ── Module 2: Extraction ───────────────────────────────────────
    _progress("Extracting information …", 18)
    logger.info("\n[2/6] Extracting information …")
    papers = extract_all_papers(papers, use_rebel=use_rebel)
    logger.info(f"  ✓ Extraction complete ({len(papers)} papers)")

    # ── Module 3: Embeddings + Clustering ─────────────────────────
    _progress("Embedding + Clustering …", 40)
    logger.info("\n[3/6] Embedding + Clustering …")
    embeddings = embed_papers(papers, topic=topic, field="combined")
    cluster_result = run_clustering(papers, embeddings)
    logger.info(
        f"  ✓ {cluster_result['clustering_metrics']['n_clusters']} clusters | "
        f"silhouette={cluster_result['clustering_metrics'].get('silhouette', 'N/A')}"
    )

    # ── Module 4: Temporal Analysis ───────────────────────────────
    _progress("Temporal analysis …", 60)
    logger.info("\n[4/6] Temporal analysis …")
    temporal = analyze_temporal(papers, embeddings)
    logger.info(f"  ✓ {len(temporal['timeline'])} years analysed")

    # ── Module 5: Knowledge Graph ──────────────────────────────────
    _progress("Building knowledge graph …", 75)
    logger.info("\n[5/6] Building knowledge graph …")
    kg_result = build_and_export_graph(papers, cluster_result, output_dir=output_dir)
    seminal = kg_result["seminal_papers"]
    logger.info(
        f"  ✓ Graph: {kg_result['graph']['stats']['n_nodes']} nodes, "
        f"{kg_result['graph']['stats']['n_edges']} edges | "
        f"{len(seminal)} seminal papers"
    )

    # ── Module 6: Gap Detection ────────────────────────────────────
    _progress("Detecting research gaps …", 88)
    logger.info("\n[6/6] Detecting research gaps …")
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
                max(p["year"] for p in papers if p.get("year")),
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
        # Knowledge graph
        "knowledge_graph": kg_result["graph"],
        "seminal_papers": seminal,
        "knowledge_graph_html": kg_result["html_path"],
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
        topic="Graph Neural Networks",
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

"""
Module 5 — Knowledge Graph
----------------------------
Builds a directed graph where:
  Nodes: papers, methods (from NER), datasets (from NER)
  Edges: cites (from SS references), uses_method, uses_dataset,
         extends/trained_on/evaluated_on (from REBEL triplets)

Seminal paper detection:
  PageRank on citation subgraph → influence score
  Cross-cluster citation analysis → papers that bridge clusters
  Seminal = top 5% PageRank AND cited by papers from 3+ clusters

Exports interactive PyVis HTML for frontend embedding.
"""

import logging
from collections import defaultdict
from pathlib import Path

import networkx as nx
from pyvis.network import Network

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_knowledge_graph(
    papers: list[dict],
    cluster_labels: dict | None = None,
) -> nx.DiGraph:
    """
    Build a rich directed knowledge graph from enriched papers.

    Args:
        papers: Enriched paper dicts (with NER + REBEL + LLM fields).
        cluster_labels: {paper_id: cluster_id} mapping (for node coloring).

    Returns:
        NetworkX DiGraph
    """
    G = nx.DiGraph()

    # Index papers by ss_id and arxiv_id for reference resolution
    id_map: dict[str, int] = {}
    for p in papers:
        if p.get("ss_id"):
            id_map[p["ss_id"]] = p["id"]
        if p.get("arxiv_id"):
            id_map[p["arxiv_id"]] = p["id"]
        if p.get("openalex_id"):
            id_map[p["openalex_id"]] = p["id"]

    cluster_label_map = cluster_labels or {}

    # ---- Paper nodes ----
    for p in papers:
        node_id = f"paper_{p['id']}"
        G.add_node(
            node_id,
            node_type="paper",
            title=p["title"],
            year=p.get("year", 0),
            citation_count=p.get("citation_count", 0),
            influential_citation_count=p.get("influential_citation_count", 0),
            cluster_id=cluster_label_map.get(p["id"], -1),
            label=p["title"][:40] + "…" if len(p["title"]) > 40 else p["title"],
        )

    # ---- Method nodes from NER ----
    for p in papers:
        for model in p.get("ner_models", []):
            node_id = f"method_{model.lower().replace(' ', '_')}"
            if not G.has_node(node_id):
                G.add_node(node_id, node_type="method", label=model)
            G.add_edge(f"paper_{p['id']}", node_id, relation="uses_method")

    # ---- Dataset nodes from NER ----
    for p in papers:
        for dataset in p.get("ner_datasets", []):
            node_id = f"dataset_{dataset.lower().replace(' ', '_')}"
            if not G.has_node(node_id):
                G.add_node(node_id, node_type="dataset", label=dataset)
            G.add_edge(f"paper_{p['id']}", node_id, relation="uses_dataset")

    # ---- Citation edges from Semantic Scholar references ----
    for p in papers:
        for ref_ss_id in p.get("references", []):
            if ref_ss_id in id_map:
                target_id = id_map[ref_ss_id]
                G.add_edge(
                    f"paper_{p['id']}",
                    f"paper_{target_id}",
                    relation="cites",
                )

    # ---- REBEL triplet edges (typed relations) ----
    for p in papers:
        for triplet in p.get("triplets", []):
            head = triplet.get("head", "").strip()
            relation = triplet.get("relation", "").strip()
            tail = triplet.get("tail", "").strip()
            if not (head and relation and tail):
                continue
            # Try to match head/tail to known paper titles
            head_node = f"entity_{head.lower().replace(' ', '_')[:30]}"
            tail_node = f"entity_{tail.lower().replace(' ', '_')[:30]}"
            for node in [head_node, tail_node]:
                if not G.has_node(node):
                    G.add_node(node, node_type="entity", label=head if node == head_node else tail)
            G.add_edge(head_node, tail_node, relation=relation)

    logger.info(
        f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
    )
    return G


# ---------------------------------------------------------------------------
# Seminal Paper Detection
# ---------------------------------------------------------------------------

def detect_seminal_papers(
    G: nx.DiGraph,
    papers: list[dict],
    cluster_labels: dict | None = None,
    top_pct: float = 0.10,
) -> list[dict]:
    """
    Identify seminal papers using PageRank + cross-cluster citation analysis.
    Falls back to citation_count ranking when no citation edges exist (arXiv-only data).
    """
    cluster_label_map = cluster_labels or {}

    # Build citation-only subgraph for PageRank
    citation_graph = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        if data.get("relation") == "cites":
            citation_graph.add_edge(u, v)

    pagerank = nx.pagerank(citation_graph, alpha=0.85) if citation_graph.number_of_nodes() > 0 else {}

    # Cross-cluster citation count per paper
    cross_cluster: dict[str, set] = defaultdict(set)
    for u, v, data in G.edges(data=True):
        if data.get("relation") == "cites" and v.startswith("paper_"):
            citing_id = int(u.replace("paper_", ""))
            citing_cluster = cluster_label_map.get(citing_id, -1)
            cross_cluster[v].add(citing_cluster)

    paper_nodes = [f"paper_{p['id']}" for p in papers]

    if not pagerank:
        # ── Fallback: no citation graph (arXiv-only) ──
        # Use raw citation_count from OpenAlex/SS as proxy for influence.
        logger.warning("No citation edges found — using citation_count as seminal proxy.")
        cited = [p for p in papers if p.get("citation_count", 0) > 0]
        cited.sort(key=lambda p: p.get("citation_count", 0), reverse=True)
        top_n = max(1, len(cited) // 10)  # top 10%
        seminal = [
            {**p, "pagerank": 0.0, "cross_cluster_citations": 0, "is_seminal": True}
            for p in cited[:top_n]
        ]
        logger.info(f"Detected {len(seminal)} seminal papers (citation_count fallback).")
        return seminal

    pr_values = [pagerank.get(n, 0) for n in paper_nodes]
    if not pr_values:
        return []
    threshold = sorted(pr_values, reverse=True)[max(1, int(len(pr_values) * top_pct))]

    seminal = []
    for p in papers:
        node = f"paper_{p['id']}"
        pr = pagerank.get(node, 0)
        clusters_citing = cross_cluster.get(node, set())
        if pr >= threshold and len(clusters_citing) >= 2:
            seminal.append({
                **p,
                "pagerank": round(pr, 6),
                "cross_cluster_citations": len(clusters_citing),
                "is_seminal": True,
            })

    seminal.sort(key=lambda x: x["pagerank"], reverse=True)
    logger.info(f"Detected {len(seminal)} seminal papers.")
    return seminal



# ---------------------------------------------------------------------------
# PyVis Export
# ---------------------------------------------------------------------------

_CLUSTER_COLORS = [
    "#4cc9f0", "#f72585", "#7209b7", "#3a0ca3", "#4361ee",
    "#4895ef", "#560bad", "#f3722c", "#f8961e", "#90be6d",
]

_NODE_TYPE_CONFIG = {
    "paper":   {"shape": "dot",     "color": "#4cc9f0", "size": 12},
    "method":  {"shape": "diamond", "color": "#f8961e", "size": 10},
    "dataset": {"shape": "square",  "color": "#90be6d", "size": 10},
    "entity":  {"shape": "ellipse", "color": "#aaaaaa", "size": 8},
}


def export_pyvis_html(
    G: nx.DiGraph,
    output_path: str = "data/knowledge_graph.html",
    seminal_ids: set | None = None,
) -> str:
    """
    Export the knowledge graph as a standalone interactive PyVis HTML file.

    Args:
        G: The NetworkX graph.
        output_path: Where to save the HTML file.
        seminal_ids: Set of paper node IDs (e.g. 'paper_3') that are seminal.

    Returns:
        Absolute path to the generated HTML file.
    """
    seminal_ids = seminal_ids or set()
    net = Network(
        height="700px",
        width="100%",
        directed=True,
        bgcolor="#0f0f1a",
        font_color="#e0e0e0",
    )
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=150)

    for node_id, data in G.nodes(data=True):
        node_type = data.get("node_type", "entity")
        cfg = _NODE_TYPE_CONFIG.get(node_type, _NODE_TYPE_CONFIG["entity"])

        # Cluster-based color for papers
        color = cfg["color"]
        if node_type == "paper":
            cluster_id = data.get("cluster_id", -1)
            if cluster_id >= 0:
                color = _CLUSTER_COLORS[cluster_id % len(_CLUSTER_COLORS)]

        # Seminal papers: gold star
        shape = cfg["shape"]
        size = cfg["size"]
        if node_id in seminal_ids:
            color = "#ffd700"
            shape = "star"
            size = 20

        # Size paper nodes by citation count
        if node_type == "paper":
            cites = data.get("citation_count", 0)
            size = max(8, min(30, 8 + cites // 20))

        tooltip = (
            f"{data.get('label', node_id)}"
            f" | year={data.get('year', '')}"
            f" | citations={data.get('citation_count', '')}"
        )

        net.add_node(
            node_id,
            label=data.get("label", node_id),
            title=tooltip,
            color=color,
            shape=shape,
            size=size,
        )

    for u, v, data in G.edges(data=True):
        net.add_edge(u, v, title=data.get("relation", ""), arrows="to", color="#444466")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    net.save_graph(output_path)
    logger.info(f"Knowledge graph saved → {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Serialise graph for JSON API response
# ---------------------------------------------------------------------------

def graph_to_dict(G: nx.DiGraph) -> dict:
    """Convert graph to JSON-serialisable dict for the API."""
    return {
        "nodes": [
            {"id": n, **{k: v for k, v in d.items() if isinstance(v, (str, int, float, bool, list))}}
            for n, d in G.nodes(data=True)
        ],
        "edges": [
            {"source": u, "target": v, "relation": d.get("relation", "")}
            for u, v, d in G.edges(data=True)
        ],
        "stats": {
            "n_nodes": G.number_of_nodes(),
            "n_edges": G.number_of_edges(),
        },
    }


# ---------------------------------------------------------------------------
# Public API wrapper
# ---------------------------------------------------------------------------

def build_and_export_graph(
    papers: list[dict],
    cluster_result: dict,
    output_dir: str = "data",
) -> dict:
    """
    Full knowledge graph pipeline: build → seminal detection → PyVis export.

    Args:
        papers: Enriched papers.
        cluster_result: Output from clustering.run_clustering().
        output_dir: Directory to save HTML.

    Returns:
        {graph_dict, seminal_papers, html_path}
    """
    # Build cluster label map: paper_id → cluster_id
    labels = cluster_result["labels"]
    cluster_label_map = {p["id"]: int(labels[i]) for i, p in enumerate(papers)}

    G = build_knowledge_graph(papers, cluster_labels=cluster_label_map)

    seminal = detect_seminal_papers(G, papers, cluster_labels=cluster_label_map)
    seminal_node_ids = {f"paper_{p['id']}" for p in seminal}

    html_path = export_pyvis_html(
        G,
        output_path=str(Path(output_dir) / "knowledge_graph.html"),
        seminal_ids=seminal_node_ids,
    )

    return {
        "graph": graph_to_dict(G),
        "seminal_papers": seminal,
        "html_path": html_path,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from pipeline.retrieval import retrieve_papers
    from pipeline.extraction import extract_all_papers
    from pipeline.embedding import embed_papers
    from pipeline.clustering import run_clustering

    topic = "Retrieval-Augmented Generation"
    papers = retrieve_papers(topic, max_papers=20)
    papers = extract_all_papers(papers, use_rebel=False)
    embs = embed_papers(papers, topic=topic)
    cluster_result = run_clustering(papers, embs)

    result = build_and_export_graph(papers, cluster_result)
    print(f"\nGraph: {result['graph']['stats']}")
    print(f"Seminal papers: {len(result['seminal_papers'])}")
    if result['seminal_papers']:
        for p in result['seminal_papers'][:3]:
            print(f"  [{p['year']}] {p['title'][:60]}  PR={p['pagerank']}")
    print(f"HTML saved → {result['html_path']}")

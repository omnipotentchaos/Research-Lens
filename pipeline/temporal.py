"""
Module 4 — Temporal Analysis & Evolution Tracking
----------------------------------------------------
Analyzes how the research field evolved year by year:
  - Method frequency: how often each method appears per year (rise/fall curves)
  - Topic drift: cosine distance between consecutive year centroids
  - Emerging vs fading methods (new this year vs declining from prior year)
  - Peak year detection per method
"""

import logging
from collections import defaultdict

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_methods_for_paper(paper: dict) -> list[str]:
    """
    Collect method mentions from LLM extraction + NER.
    Returns a flat, lowercase list for counting.
    """
    sources = []
    # LLM-extracted method field — may be a string or a list
    method = paper.get("method")
    if method:
        if isinstance(method, list):
            sources.extend([str(m).strip().lower() for m in method if m])
        else:
            sources.extend([m.strip().lower() for m in str(method).split(",")])
    # NER-extracted model names
    for m in paper.get("ner_models", []):
        sources.append(str(m).strip().lower())
    return [s for s in sources if s]


# ---------------------------------------------------------------------------
# Method Frequency Over Time
# ---------------------------------------------------------------------------

def method_frequency_over_time(papers: list[dict]) -> dict:
    """
    Count how often each method is mentioned per year.

    Returns:
        {method: {year: count, ...}, ...}
    """
    freq: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for p in papers:
        year = p.get("year")
        if not year:
            continue
        for method in _get_methods_for_paper(p):
            freq[method][year] += 1

    # Convert to plain dicts, filter noise (total mentions < 2)
    result = {}
    for method, years in freq.items():
        if sum(years.values()) >= 2:
            result[method] = dict(sorted(years.items()))
    return result


def detect_emerging_fading(freq: dict, all_years: list[int]) -> dict:
    """
    For each consecutive year pair, find methods that are new (emerging)
    or decreasing (fading).

    Returns:
        {year: {emerging: [...], fading: [...], dominant: [...]}}
    """
    timeline = {}
    sorted_years = sorted(all_years)

    for i, year in enumerate(sorted_years):
        prior_year = sorted_years[i - 1] if i > 0 else None

        year_counts = {m: freq[m].get(year, 0) for m in freq}
        prior_counts = {m: freq[m].get(prior_year, 0) for m in freq} if prior_year else {}

        dominant = sorted(
            [m for m in year_counts if year_counts[m] > 0],
            key=lambda m: year_counts[m],
            reverse=True,
        )[:5]

        emerging, fading = [], []
        if prior_year:
            for m in freq:
                cur = year_counts.get(m, 0)
                prev = prior_counts.get(m, 0)
                if cur > 0 and prev == 0:
                    emerging.append(m)
                elif prev > 1 and cur == 0:
                    fading.append(m)

        timeline[year] = {
            "dominant_methods": dominant,
            "emerging_methods": emerging,
            "fading_methods": fading,
        }

    return timeline


def peak_year_per_method(freq: dict) -> dict:
    """
    Find the year in which each method had maximum mentions.
    Returns: {method: peak_year}
    """
    peaks = {}
    for method, years in freq.items():
        if years:
            peaks[method] = max(years, key=years.get)
    return peaks


# ---------------------------------------------------------------------------
# Topic Drift (Centroid Shift)
# ---------------------------------------------------------------------------

def compute_topic_drift(
    papers: list[dict],
    embeddings: np.ndarray,
) -> dict[int, float]:
    """
    Measure how much the research "centre of mass" moves each year.
    Large shift = major change in the field that year.

    Returns:
        {year: cosine_distance_from_prior_year}
    """
    year_embeddings: dict[int, list[np.ndarray]] = defaultdict(list)
    for i, paper in enumerate(papers):
        year = paper.get("year")
        if year:
            year_embeddings[year].append(embeddings[i])

    sorted_years = sorted(year_embeddings.keys())
    centroids = {}
    for year in sorted_years:
        centroids[year] = np.mean(year_embeddings[year], axis=0)

    drift = {}
    for i, year in enumerate(sorted_years):
        if i == 0:
            drift[year] = 0.0
            continue
        prior = sorted_years[i - 1]
        sim = cosine_similarity(
            centroids[year].reshape(1, -1),
            centroids[prior].reshape(1, -1),
        )[0][0]
        drift[year] = round(float(1.0 - sim), 4)  # cosine distance

    return drift


# ---------------------------------------------------------------------------
# Paper Count Per Year
# ---------------------------------------------------------------------------

def paper_count_per_year(papers: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for p in papers:
        if p.get("year"):
            counts[p["year"]] += 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_temporal(papers: list[dict], embeddings: np.ndarray) -> dict:
    """
    Full temporal analysis for the pipeline.

    Returns:
        Structured dict with method_frequency, timeline, drift, paper_counts,
        peak_years ready to be consumed by the frontend charts.
    """
    logger.info("Running temporal analysis …")

    freq = method_frequency_over_time(papers)
    counts = paper_count_per_year(papers)
    all_years = sorted(counts.keys())
    emergence = detect_emerging_fading(freq, all_years)
    drift = compute_topic_drift(papers, embeddings)
    peaks = peak_year_per_method(freq)

    # Build per-year timeline
    timeline = []
    for year in all_years:
        timeline.append({
            "year": year,
            "paper_count": counts[year],
            "dominant_methods": emergence[year]["dominant_methods"],
            "emerging_methods": emergence[year]["emerging_methods"],
            "fading_methods": emergence[year]["fading_methods"],
            "centroid_drift": drift.get(year, 0.0),
        })

    logger.info(f"Temporal analysis complete: {len(all_years)} years, {len(freq)} methods tracked")

    return {
        "timeline": timeline,
        "method_frequency": freq,           # {method: {year: count}}
        "peak_year_per_method": peaks,
        "centroid_drift_per_year": drift,
        "paper_counts_per_year": counts,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from pipeline.retrieval import retrieve_papers
    from pipeline.extraction import extract_all_papers
    from pipeline.embedding import embed_papers

    topic = "Retrieval-Augmented Generation"
    papers = retrieve_papers(topic, max_papers=30)
    papers = extract_all_papers(papers, use_rebel=False)
    embs = embed_papers(papers, topic=topic, field="combined")
    temporal = analyze_temporal(papers, embs)

    print("\nYear-by-year timeline:")
    for entry in temporal["timeline"]:
        print(f"  {entry['year']} | papers={entry['paper_count']} | drift={entry['centroid_drift']} | dominant={entry['dominant_methods'][:3]}")

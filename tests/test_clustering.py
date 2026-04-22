"""
Tests for Module 3b — Clustering
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np
from sklearn.cluster import HDBSCAN
from pipeline.clustering import reduce_dimensions, cluster_papers, evaluate_clustering


def _make_fake_embeddings(n: int = 30, dim: int = 768) -> np.ndarray:
    """Create synthetic embeddings with 3 clear clusters."""
    np.random.seed(42)
    c1 = np.random.randn(n // 3, dim) + np.array([5.0] + [0.0] * (dim - 1))
    c2 = np.random.randn(n // 3, dim) + np.array([-5.0] + [0.0] * (dim - 1))
    c3 = np.random.randn(n - 2 * (n // 3), dim) + np.array([0.0, 5.0] + [0.0] * (dim - 2))
    return np.vstack([c1, c2, c3]).astype(np.float32)


def test_reduce_dimensions_output_shape():
    embs = _make_fake_embeddings(20)
    reduced = reduce_dimensions(embs, n_components=2)
    assert reduced.shape == (20, 2)


def test_reduce_dimensions_no_nan():
    embs = _make_fake_embeddings(20)
    reduced = reduce_dimensions(embs, n_components=2)
    assert not np.any(np.isnan(reduced))


def test_cluster_papers_returns_labels():
    embs = _make_fake_embeddings(30)
    reduced = reduce_dimensions(embs, n_components=2)
    labels, clusterer = cluster_papers(reduced, min_cluster_size=3)
    assert len(labels) == 30
    assert labels.dtype in [np.int32, np.int64, int]


def test_evaluate_clustering_keys():
    embs = _make_fake_embeddings(30)
    reduced = reduce_dimensions(embs, n_components=2)
    labels, _ = cluster_papers(reduced, min_cluster_size=3)
    metrics = evaluate_clustering(reduced, labels)
    assert "silhouette" in metrics
    assert "davies_bouldin" in metrics
    assert "n_clusters" in metrics


def test_evaluate_silhouette_range():
    embs = _make_fake_embeddings(30)
    reduced = reduce_dimensions(embs, n_components=2)
    labels, _ = cluster_papers(reduced, min_cluster_size=3)
    metrics = evaluate_clustering(reduced, labels)
    if metrics["silhouette"] is not None:
        assert -1 <= metrics["silhouette"] <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

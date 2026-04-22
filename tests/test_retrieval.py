"""
Tests for Module 1 — Retrieval
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from pipeline.retrieval import _deduplicate, _bm25_rerank, expand_query


# ── Deduplication ──────────────────────────────────────────────────────────

def test_deduplicate_removes_near_duplicates():
    papers = [
        {"title": "Retrieval-Augmented Generation for NLP", "abstract": "foo"},
        {"title": "Retrieval Augmented Generation for NLP", "abstract": "bar"},  # near-dup
        {"title": "Dense Passage Retrieval", "abstract": "baz"},
    ]
    result = _deduplicate(papers)
    assert len(result) == 2, "Near-duplicate should be removed"


def test_deduplicate_keeps_distinct_papers():
    papers = [
        {"title": "RAG for Open-Domain QA", "abstract": "a"},
        {"title": "BERT: Pre-training of Deep Bidirectional Transformers", "abstract": "b"},
        {"title": "T5: Exploring the Limits of Transfer Learning", "abstract": "c"},
    ]
    result = _deduplicate(papers)
    assert len(result) == 3


# ── BM25 Re-ranking ────────────────────────────────────────────────────────

def test_bm25_rerank_returns_top_k():
    papers = [
        {"title": f"Paper {i}", "abstract": f"This paper is about topic {i}"}
        for i in range(20)
    ]
    result = _bm25_rerank(papers, topic="topic 5", top_k=10)
    assert len(result) == 10


def test_bm25_rerank_ranks_relevant_first():
    papers = [
        {"title": "Unrelated paper about cats", "abstract": "Cats are domestic animals with fur."},
        {"title": "RAG paper", "abstract": "Retrieval-Augmented Generation combines dense retrieval with generation models."},
    ]
    result = _bm25_rerank(papers, topic="Retrieval-Augmented Generation", top_k=2)
    assert result[0]["title"] == "RAG paper", "RAG paper should rank first"


def test_bm25_rerank_handles_empty():
    result = _bm25_rerank([], topic="anything", top_k=10)
    assert result == []


# ── Query expansion ────────────────────────────────────────────────────────

def test_expand_query_returns_list():
    """Mocked test — does not call Groq API."""
    with patch("pipeline.retrieval.Groq") as MockGroq:
        mock_client = MagicMock()
        MockGroq.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"queries": ["query a", "query b", "query c", "query d"]}'))]
        )
        os.environ["GROQ_API_KEY"] = "fake"
        queries = expand_query("RAG in NLP")
        assert isinstance(queries, list)
        assert queries[0] == "RAG in NLP"  # original always first


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

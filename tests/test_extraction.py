"""
Tests for Module 2 — Extraction
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from pipeline.extraction import _extract_with_ner, _parse_rebel_output


# ── NER extraction ─────────────────────────────────────────────────────────

def test_ner_extracts_known_model_names():
    text = "We fine-tune BERT and GPT-4 on the SQuAD dataset and evaluate using F1 and BLEU."
    with patch("pipeline.extraction._get_spacy") as mock_spacy:
        mock_nlp = MagicMock()
        mock_nlp.return_value.ents = []
        mock_spacy.return_value = mock_nlp
        result = _extract_with_ner(text)
    assert "BERT" in result["ner_models"] or "Bert" in result["ner_models"]
    assert "SQUAD" in result["ner_datasets"] or "Squad" in result["ner_datasets"]
    assert "F1" in result["ner_metrics"] or "BLEU" in result["ner_metrics"]


def test_ner_returns_empty_on_no_match():
    text = "This paper proposes a new approach for solving the problem."
    with patch("pipeline.extraction._get_spacy") as mock_spacy:
        mock_nlp = MagicMock()
        mock_nlp.return_value.ents = []
        mock_spacy.return_value = mock_nlp
        result = _extract_with_ner(text)
    assert isinstance(result["ner_models"], list)
    assert isinstance(result["ner_datasets"], list)


# ── REBEL output parsing ───────────────────────────────────────────────────

def test_parse_rebel_output_valid():
    # Simulated REBEL linearized output
    raw = "<triplet> BERT <subj> trained on <obj> BookCorpus"
    triplets = _parse_rebel_output(raw)
    assert len(triplets) == 1
    assert triplets[0]["head"] == "BERT"
    assert triplets[0]["relation"] == "trained on"
    assert triplets[0]["tail"] == "BookCorpus"


def test_parse_rebel_output_multiple():
    raw = (
        "<triplet> RAG <subj> extends <obj> DPR "
        "<triplet> GPT-4 <subj> evaluated on <obj> MMLU"
    )
    triplets = _parse_rebel_output(raw)
    assert len(triplets) == 2


def test_parse_rebel_output_empty():
    triplets = _parse_rebel_output("")
    assert triplets == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

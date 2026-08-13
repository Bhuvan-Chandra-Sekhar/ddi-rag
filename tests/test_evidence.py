"""
Phase 4 exit gate: an explanation cannot change severity/action, and its
citations resolve to the exact evidence passages used to produce it.
"""

from unittest.mock import patch

import pandas as pd

from services import evidence as ev


def test_explanation_never_carries_clinical_fields():
    with patch.object(ev, "retrieve_supporting_evidence", return_value=[]), \
         patch.object(ev, "_call_groq_api", return_value="plain language explanation"):
        result = ev.explain_finding(
            finding_type="ddi", severity="major",
            clinical_effect="increases bleeding risk",
            recommended_action="prescriber review required",
            drug_name="warfarin", model_name="test-model",
        )

    # The function only ever returns explanation-shaped fields — it cannot
    # smuggle a different severity/type/action back to the caller.
    assert set(result.keys()) == {
        "explanation", "citations", "evidence_hash", "model_version", "prompt_version",
    }
    assert result["explanation"] == "plain language explanation"
    assert result["model_version"] == "test-model"
    assert result["prompt_version"] == ev.PROMPT_VERSION


def test_retrieve_supporting_evidence_returns_passages():
    fake_chunks = pd.DataFrame([
        {"generic_name": "warfarin", "section": "drug_interactions", "text": "some fda text", "score": 0.9},
    ])
    with patch.object(ev, "retrieve_chunks", return_value=fake_chunks):
        passages = ev.retrieve_supporting_evidence("bleeding risk", drug_name="warfarin")

    assert len(passages) == 1
    assert passages[0]["text"] == "some fda text"


def test_retrieve_supporting_evidence_fails_closed_on_error():
    with patch.object(ev, "retrieve_chunks", side_effect=RuntimeError("qdrant down")):
        passages = ev.retrieve_supporting_evidence("bleeding risk")
    assert passages == []


def test_evidence_hash_is_deterministic_and_sensitive_to_evidence():
    h1 = ev._evidence_hash("[ddi/major] effect", [{"text": "passage A"}])
    h2 = ev._evidence_hash("[ddi/major] effect", [{"text": "passage A"}])
    h3 = ev._evidence_hash("[ddi/major] effect", [{"text": "passage B"}])

    assert h1 == h2
    assert h1 != h3


def test_citations_in_result_match_retrieved_evidence():
    fake_chunks = pd.DataFrame([
        {"generic_name": "warfarin", "section": "warnings", "text": "citation text", "score": 0.8},
    ])
    with patch.object(ev, "retrieve_chunks", return_value=fake_chunks), \
         patch.object(ev, "_call_groq_api", return_value="explanation"):
        result = ev.explain_finding(
            finding_type="ddi", severity="major",
            clinical_effect="effect", recommended_action="action",
        )

    assert result["citations"] == [
        {"generic_name": "warfarin", "section": "warnings", "text": "citation text", "score": 0.8}
    ]

"""
routes_public.py — unauthenticated guest self-check. Covers: no login is
required, the deterministic rule engine is what actually produces findings
(not the LLM), /api/explain re-derives findings server-side instead of
trusting client-supplied clinical fields, and the item-count cap holds.
"""

from unittest.mock import patch

import pytest

from app import flask_app
from database import get_session
from enums import FindingType, RuleStatus, Severity
from models import ClinicalRule


@pytest.fixture
def client():
    return flask_app.test_client()


def _fake_identity(name):
    """Stand-in for resolve_medication_identity — avoids a live RxNorm call
    in tests; treats the typed name as its own single ingredient."""
    return {
        "rxcui": None, "ingredients": [name.strip().lower()],
        "matched_exactly": False, "identity_confirmed": False,
        "resolution_method": "unresolved",
    }


def test_self_check_requires_at_least_one_medication(client):
    resp = client.post("/api/self-check", json={"medications": []})
    assert resp.status_code == 400


def test_self_check_detects_duplicate_ingredient(client):
    with patch("routes_public.resolve_medication_identity", side_effect=lambda n: _fake_identity("aspirin")):
        resp = client.post("/api/self-check", json={"medications": ["Aspirin", "aspirin 81mg"]})
    assert resp.status_code == 200
    findings = resp.get_json()["findings"]
    assert any(f["type"] == "duplicate" for f in findings)


def test_self_check_detects_allergy_match(client):
    with patch("routes_public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        resp = client.post("/api/self-check", json={
            "medications": ["penicillin"], "allergies": ["penicillin"],
        })
    assert resp.status_code == 200
    findings = resp.get_json()["findings"]
    assert len(findings) == 1
    assert findings[0]["type"] == "allergy"
    assert findings[0]["severity"] == "critical"
    assert resp.get_json()["overall_severity"] == "critical"


def test_self_check_caps_medication_count(client):
    names = [f"drug{i}" for i in range(20)]
    with patch("routes_public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        resp = client.post("/api/self-check", json={"medications": names})
    assert resp.status_code == 200
    assert len(resp.get_json()["resolved_medications"]) == 8  # MAX_SELF_CHECK_ITEMS


def test_self_check_surfaces_reported_severity_for_unreviewed_ddi_pair(client):
    """The real bug this guards against: a DRAFT rule (every rule in the
    live database is DRAFT — none are pharmacist-approved yet) used to
    report severity=unknown with no way to tell a well-documented MAJOR
    interaction apart from one with no data behind it at all. Guests were
    getting "not yet reviewed" for everything, no matter how serious the
    underlying source data said it was."""
    with get_session() as session:
        session.add(ClinicalRule(
            rule_type=FindingType.DDI, pair_key="aspirin||warfarin",
            ingredient_a="aspirin", ingredient_b="warfarin",
            clinical_effect="increases bleeding risk", severity=Severity.MAJOR,
            status=RuleStatus.DRAFT, rule_version="ddinter-2.0-v1",
        ))
        session.flush()

    with patch("routes_public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        resp = client.post("/api/self-check", json={"medications": ["aspirin", "warfarin"]})

    assert resp.status_code == 200
    body = resp.get_json()
    finding = body["findings"][0]
    assert finding["type"] == "unknown"
    assert finding["severity"] == "unknown"           # governance severity: still not confirmed
    assert finding["reported_severity"] == "major"     # but the real signal isn't thrown away
    assert finding["see_a_doctor"] is True
    assert "doctor" in finding["patient_guidance"].lower()
    assert body["see_a_doctor"] is True


def test_patient_guidance_never_uses_pharmacy_operational_wording(client):
    """recommended_action is written for a pharmacist's dispensing workflow
    ("do not dispense without prescriber confirmation") — that text was
    previously shown to guests verbatim, who aren't dispensing anything.
    patient_guidance must be the patient-facing rewrite, not a passthrough."""
    with patch("routes_public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        resp = client.post("/api/self-check", json={
            "medications": ["penicillin"], "allergies": ["penicillin"],
        })
    finding = resp.get_json()["findings"][0]
    assert "dispense" not in finding["patient_guidance"].lower()
    assert finding["see_a_doctor"] is True


def test_explain_finds_and_explains_a_real_ddi_finding(client):
    with get_session() as session:
        session.add(ClinicalRule(
            rule_type=FindingType.DDI, pair_key="aspirin||warfarin",
            ingredient_a="aspirin", ingredient_b="warfarin",
            clinical_effect="increases bleeding risk", severity=Severity.MAJOR,
            status=RuleStatus.APPROVED, rule_version="v1",
        ))
        session.flush()

    with patch("routes_public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)), \
         patch("routes_public.explain_finding") as mock_explain:
        mock_explain.return_value = {
            "explanation": "plain language text", "citations": [], "evidence_hash": "abc",
            "model_version": "", "prompt_version": "explain-finding-v1",
        }
        resp = client.post("/api/explain", json={
            "medications": ["aspirin", "warfarin"], "finding_index": 0,
        })

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["explanation"] == "plain language text"
    # audience="patient" is the guest-checker contract — never the clinician wording.
    assert mock_explain.call_args.kwargs["audience"] == "patient"


def test_explain_rejects_out_of_range_index_instead_of_trusting_client_fields(client):
    """A client can't get a free explanation for a fabricated finding by
    just POSTing clinical_effect/severity directly — only finding_index
    into the server's own re-derived list is honored, and an empty
    medication list with no real findings has no valid index at all."""
    with patch("routes_public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        resp = client.post("/api/explain", json={
            "medications": ["ibuprofen"],
            "finding_index": 0,
            "clinical_effect": "fabricated by client", "severity": "critical",
        })
    assert resp.status_code == 400

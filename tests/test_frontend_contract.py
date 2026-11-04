"""
Contract between the Flask API and the React patient app.

The frontend unit tests mock every API response, so on their own they
cannot notice the backend renaming a field the UI reads (this suite found
exactly that: the dashboard keyed cases on `c.id` while the API sends
`case_id`). These tests pin both directions from the backend side:

  * every field the frontend reads is present in the real response, and
  * the frontend's lists of workflow states, severities, finding types
    and clinical roles stay equal to the backend enums.

The browser-level proof, with real React against real Flask, is the
Playwright suite in frontend-patient/e2e.
"""

import re
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from flask_jwt_extended import create_access_token

from app import flask_app
from core.auth import register_user
from core.rate_limit import limiter
from database import get_session, init_db
from enums import (
    DeliveryChannel, FindingType, PrescriptionStatus, SafetyCaseState, Severity, UserRole,
)
from models import ClinicalProfileSnapshot, Medication, Organization, Patient, Prescription, User
from services.professional_workflow import send_patient_communication
from services.safety_case import create_case, transition_case

FRONTEND_SRC = Path(__file__).resolve().parent.parent / "frontend-patient" / "src"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield


def _read(relative: str) -> str:
    return (FRONTEND_SRC / relative).read_text(encoding="utf-8")


def _object_keys(source: str, const_name: str) -> set:
    """Top-level keys of `export const NAME = { ... };` in a JS module."""
    start = source.index(f"export const {const_name} = {{")
    body = source[start:source.index("\n};", start)]
    return set(re.findall(r"^  ([A-Za-z_]+):", body, flags=re.MULTILINE))


def _fake_identity(name):
    return {
        "rxcui": None, "ingredients": [name.strip().lower()],
        "matched_exactly": False, "identity_confirmed": False,
        "resolution_method": "unresolved",
    }


def _enum_values(enum_cls) -> set:
    return {member.value for member in enum_cls}


# ── The frontend's own lists must equal the backend enums ───────────────────

def test_dashboard_state_labels_cover_every_workflow_state_exactly():
    frontend = _object_keys(_read("meta.js"), "STATE_META")
    assert frontend == _enum_values(SafetyCaseState), (
        "frontend STATE_META and SafetyCaseState differ: "
        f"missing in frontend {_enum_values(SafetyCaseState) - frontend}, "
        f"unknown to backend {frontend - _enum_values(SafetyCaseState)}"
    )


def test_severity_labels_cover_every_severity_exactly():
    frontend = _object_keys(_read("meta.js"), "SEVERITY_META")
    assert frontend == _enum_values(Severity)


def test_finding_titles_only_name_real_finding_types():
    referenced = set(re.findall(r"f\.type === '(\w+)'", _read("meta.js")))
    assert referenced <= _enum_values(FindingType), referenced - _enum_values(FindingType)
    # The types the guest self-check engine can actually emit.
    assert {"ddi", "allergy", "duplicate", "unknown"} <= referenced


def test_clinical_console_roles_are_real_roles():
    match = re.search(r"\[('pharmacist'[^\]]*)\]\.includes\(data\.user\?\.role\)", _read("screens/Auth.jsx"))
    assert match, "could not find the clinical role list in Auth.jsx"
    roles = set(re.findall(r"'(\w+)'", match.group(1)))
    assert roles <= _enum_values(UserRole)
    assert "patient" not in roles


# ── Guest self-check: everything Results / FindingCard read ─────────────────

def test_self_check_response_carries_every_field_the_results_screen_reads():
    client = flask_app.test_client()
    with patch("routes.public.resolve_medication_identity", side_effect=_fake_identity):
        resp = client.post("/api/self-check", json={
            "medications": ["penicillin", "penicillin", "zzdrug-a", "zzdrug-b"],
            "allergies": ["penicillin"],
        })
    assert resp.status_code == 200
    body = resp.get_json()

    for key in ("resolved_medications", "findings", "overall_severity", "see_a_doctor", "ddi_coverage"):
        assert key in body, f"Results.jsx reads `{key}`"

    for med in body["resolved_medications"]:
        assert {"input", "identity_confirmed"} <= med.keys()

    assert body["findings"], "fixture should produce findings"
    finding_types = {f["type"] for f in body["findings"]}
    assert {"allergy", "duplicate"} <= finding_types
    for position, finding in enumerate(body["findings"]):
        assert {
            "index", "type", "severity", "reported_severity", "clinical_effect",
            "recommended_action", "patient_guidance", "see_a_doctor", "patient_factors",
        } <= finding.keys()
        # The UI sends `index` back as finding_index to /api/explain.
        assert finding["index"] == position
        assert finding["severity"] in _object_keys(_read("meta.js"), "SEVERITY_META")
        assert isinstance(finding["see_a_doctor"], bool)

    coverage = body["ddi_coverage"]
    for key in (
        "pairs_checked", "pairs_approved", "pairs_with_no_rule",
        "pairs_unreviewed", "pairs_rejected", "unmatched_pairs",
    ):
        assert key in coverage, f"Results.jsx reads ddi_coverage.{key}"
    assert coverage["unmatched_pairs"], "fixture should leave at least one pair without a rule"
    assert {"ingredient_a", "ingredient_b"} <= coverage["unmatched_pairs"][0].keys()


def test_self_check_finding_factors_match_what_the_titles_read():
    client = flask_app.test_client()
    with patch("routes.public.resolve_medication_identity", side_effect=_fake_identity):
        body = client.post("/api/self-check", json={
            "medications": ["penicillin", "penicillin"], "allergies": ["penicillin"],
        }).get_json()
    by_type = {f["type"]: f for f in body["findings"]}
    assert "ingredient" in by_type["allergy"]["patient_factors"]
    assert "ingredient" in by_type["duplicate"]["patient_factors"]
    assert "occurrence_count" in by_type["duplicate"]["patient_factors"]


def test_explain_response_carries_what_the_explanation_component_reads():
    client = flask_app.test_client()
    explained = {
        "explanation": "Plain language.", "evidence_hash": "abc123", "model_version": "m",
        "prompt_version": "p",
        "citations": [{"generic_name": "penicillin", "section": "warnings", "text": "Source."}],
    }
    with patch("routes.public.resolve_medication_identity", side_effect=_fake_identity), \
         patch("routes.public.explain_finding", return_value=explained) as explain:
        resp = client.post("/api/explain", json={
            "medications": ["penicillin"], "allergies": ["penicillin"],
            "finding_index": 0, "patient_notes": "Previous rash",
        })
    assert resp.status_code == 200
    body = resp.get_json()
    assert {"explanation", "citations"} <= body.keys()
    assert {"generic_name", "section", "text"} <= body["citations"][0].keys()
    # The request body the frontend sends is accepted as-is, notes included.
    assert explain.call_args.kwargs["patient_notes"] == "Previous rash"


# ── Error envelopes: the UI shows `message` when present ────────────────────

def test_kill_switch_503_carries_a_human_message_alongside_the_code():
    client = flask_app.test_client()
    with patch("routes.public.KILL_SWITCH_SELF_CHECK", True):
        resp = client.post("/api/self-check", json={"medications": ["aspirin"]})
    body = resp.get_json()
    assert resp.status_code == 503
    assert body["error"] == "temporarily_unavailable"
    assert body["message"] and body["message"] != body["error"]


def test_explanation_outage_503_carries_a_human_message_alongside_the_code():
    from services.evidence import ExplanationUnavailable
    client = flask_app.test_client()
    with patch("routes.public.resolve_medication_identity", side_effect=_fake_identity), \
         patch("routes.public.explain_finding", side_effect=ExplanationUnavailable("down")):
        resp = client.post("/api/explain", json={
            "medications": ["penicillin"], "allergies": ["penicillin"], "finding_index": 0,
        })
    body = resp.get_json()
    assert resp.status_code == 503
    assert body["error"] == "explanation_unavailable"
    assert body["message"] and body["message"] != body["error"]


def test_unhandled_error_envelope_carries_a_human_message():
    client = flask_app.test_client()
    with patch("app.get_session", side_effect=RuntimeError("secret detail")):
        resp = client.get("/v1/organizations")
    body = resp.get_json()
    assert resp.status_code == 500
    assert body["error"] == "internal_error"
    assert body["message"] and "secret detail" not in str(body)


# ── Accounts and the dashboard ──────────────────────────────────────────────

@pytest.fixture
def org_id():
    init_db()
    with get_session() as session:
        organization = Organization(name=f"Contract Org {uuid.uuid4().hex[:8]}")
        session.add(organization)
        session.flush()
        return organization.id


def test_organizations_response_lists_id_and_name(org_id):
    resp = flask_app.test_client().get("/v1/organizations")
    assert resp.status_code == 200
    organizations = resp.get_json()["organizations"]
    assert any(o["id"] == org_id for o in organizations)
    assert all({"id", "name"} <= o.keys() for o in organizations)


def test_registration_accepts_the_exact_body_the_form_sends_and_login_returns_what_the_app_stores(org_id):
    client = flask_app.test_client()
    email = f"contract-{uuid.uuid4().hex[:8]}@example.com"
    # Field-for-field what Auth.jsx's RegisterForm posts.
    register = client.post("/api/auth/register", json={
        "email": email, "password": "password1",
        "first_name": "Sam", "last_name": "Lee", "full_name": "Sam Lee",
        "organization_id": org_id,
    })
    assert register.status_code == 201

    login = client.post("/api/auth/login", json={"email": email, "password": "password1"})
    assert login.status_code == 200
    body = login.get_json()
    assert body["access_token"]
    # Read by Auth.jsx (role), Dashboard.jsx (full_name) and the session store.
    assert {"id", "role", "full_name"} <= body["user"].keys()
    assert body["user"]["role"] == "patient"
    assert body["user"]["full_name"]


def test_registration_rejects_a_short_password_with_a_message_the_form_can_show(org_id):
    resp = flask_app.test_client().post("/api/auth/register", json={
        "email": f"short-{uuid.uuid4().hex[:8]}@example.com", "password": "short",
        "first_name": "Sam", "last_name": "Lee", "organization_id": org_id,
    })
    assert resp.status_code == 400
    assert "8" in resp.get_json()["error"]


def test_my_cases_entries_have_the_fields_the_dashboard_reads(org_id):
    email = f"cases-{uuid.uuid4().hex[:8]}@example.com"
    registered = register_user(
        email=email, password="password1", organization_id=org_id, first_name="Case", last_name="Owner",
    )
    with get_session() as session:
        user_id = session.query(User).filter_by(email=email).first().id
        patient = session.get(Patient, registered["patient_id"])
        medication = Medication(display_name="lisinopril")
        session.add(medication)
        session.flush()
        prescription = Prescription(
            organization_id=org_id, patient_id=patient.id, prescriber_id=patient.user_id,
            medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
        )
        snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
        session.add_all([prescription, snapshot])
        session.flush()
        case = create_case(session, org_id, prescription, snapshot)
        transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
        transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW)
        transition_case(session, case, SafetyCaseState.READY_TO_DISPENSE)
        send_patient_communication(
            session, case, approved_explanation="Reviewed and released.",
            delivery_channel=DeliveryChannel.PORTAL,
        )
    with flask_app.app_context():
        token = create_access_token(identity=user_id)

    resp = flask_app.test_client().get("/v1/my/cases", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    (entry,) = resp.get_json()["cases"]
    for key in ("case_id", "state", "medication", "created_at", "has_findings", "interaction_review", "communications"):
        assert key in entry, f"Dashboard.jsx reads `{key}`"
    assert "id" not in entry, "the dashboard keys cards on case_id; a bare `id` would be a different contract"
    assert entry["state"] in _object_keys(_read("meta.js"), "STATE_META")
    assert entry["communications"][0]["explanation"] == "Reviewed and released."

"""
Tests for three gaps found in a safety/compliance audit and fixed in the
same change:

    1. RETIRED rule state (services/clinical_rules.py, routes_clinical.py)
       — a previously-APPROVED rule can be withdrawn without erasing the
       fact it was once approved (unlike REJECTED, which only ever means
       "never valid"), and without going silent the way REJECTED
       correctly does — a retired rule still produces an UNKNOWN finding,
       because "this was once a confirmed interaction" going completely
       quiet would look identical to "never studied."
    2. Explanation-service outage handling (services/evidence.py,
       routes_public.py, routes_clinical.py) — _call_groq_api() never
       raises; on failure it returns a string like "Generation error:
       <exc>" that explain_finding() used to pass straight through as if
       it were real clinical content. Now it raises ExplanationUnavailable
       instead, and both HTTP routes turn that into an explicit 503.
    3. Audit coverage for the guest self-check path and authentication
       attempts — previously entirely unaudited (the public self-check
       endpoint had zero audit calls; login/register successes and
       failures were never recorded at all).

Scenarios below were written from what each feature is supposed to do
before re-reading the implementation.
"""

import uuid
from unittest.mock import patch

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import flask_app
from database import Base, get_session, init_db
from enums import FindingType, RuleStatus, Severity, UserRole
from models import AuditEvent, ClinicalRule, Organization, User
from services.clinical_rules import (
    approved_rules, ddi_coverage_report, evaluate_ddi_pairs, review_rule,
)
from services.evidence import ExplanationUnavailable
from core.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The Flask-Limiter in-memory storage is process-global, not reset
    between tests — this file alone makes enough /api/self-check and
    /api/auth/login calls to hit their per-minute caps if combined with
    whatever other test files ran earlier in the same pytest session,
    failing on rate limiting rather than on what's actually being tested."""
    limiter.reset()
    yield


# ── RETIRED rule state — service layer ──────────────────────────────────────

@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def approved_rule(session):
    rule = ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugx||drugy",
        ingredient_a="drugx", ingredient_b="drugy",
        severity=Severity.MAJOR, status=RuleStatus.APPROVED, rule_version="v1",
    )
    session.add(rule)
    session.flush()
    return rule


def test_retiring_an_approved_rule_sets_status_and_reviewer(session, approved_rule):
    rule = review_rule(session, approved_rule.id, RuleStatus.RETIRED, reviewer_user_id="reviewer-1")
    assert rule.status == RuleStatus.RETIRED
    assert rule.reviewer_user_id == "reviewer-1"
    assert rule.reviewed_at is not None


def test_cannot_retire_a_draft_rule(session):
    rule = ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugm||drugn",
        ingredient_a="drugm", ingredient_b="drugn",
        severity=Severity.CAUTION, status=RuleStatus.DRAFT, rule_version="v1",
    )
    session.add(rule)
    session.flush()
    with pytest.raises(ValueError):
        review_rule(session, rule.id, RuleStatus.RETIRED, reviewer_user_id="reviewer-1")
    assert rule.status == RuleStatus.DRAFT


def test_cannot_retire_a_rejected_rule(session):
    rule = ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugm2||drugn2",
        ingredient_a="drugm2", ingredient_b="drugn2",
        severity=Severity.CAUTION, status=RuleStatus.REJECTED, rule_version="v1",
    )
    session.add(rule)
    session.flush()
    with pytest.raises(ValueError):
        review_rule(session, rule.id, RuleStatus.RETIRED, reviewer_user_id="reviewer-1")


def test_cannot_retire_an_already_retired_rule_twice_via_wrong_path(session, approved_rule):
    review_rule(session, approved_rule.id, RuleStatus.RETIRED, reviewer_user_id="reviewer-1")
    with pytest.raises(ValueError):
        review_rule(session, approved_rule.id, RuleStatus.RETIRED, reviewer_user_id="reviewer-2")


def test_retired_rule_produces_an_unknown_finding_not_silence(session, approved_rule):
    """The core safety property: going from APPROVED to RETIRED must never
    make a once-confirmed interaction invisible, the way REJECTED
    correctly makes a never-valid one invisible."""
    review_rule(session, approved_rule.id, RuleStatus.RETIRED, reviewer_user_id="reviewer-1")
    findings = evaluate_ddi_pairs(session, ["drugx", "drugy"])
    assert len(findings) == 1
    f = findings[0]
    assert f["type"] == FindingType.UNKNOWN
    assert f["severity"] == Severity.UNKNOWN
    assert f["patient_factors"]["reported_severity"] == "major"
    assert f["evidence_refs"][0]["status"] == "retired"


def test_retired_rule_is_distinct_from_rejected_in_coverage_report(session, approved_rule):
    review_rule(session, approved_rule.id, RuleStatus.RETIRED, reviewer_user_id="reviewer-1")
    report = ddi_coverage_report(session, ["drugx", "drugy"])
    assert report["pairs_retired"] == 1
    assert report["pairs_approved"] == 0
    assert report["pairs_rejected"] == 0


def test_approved_rules_excludes_draft_rejected_and_retired(session, approved_rule):
    draft = ClinicalRule(rule_type=FindingType.DDI, pair_key="a||b", ingredient_a="a", ingredient_b="b",
                          severity=Severity.CAUTION, status=RuleStatus.DRAFT, rule_version="v1")
    rejected = ClinicalRule(rule_type=FindingType.DDI, pair_key="c||d", ingredient_a="c", ingredient_b="d",
                             severity=Severity.CAUTION, status=RuleStatus.REJECTED, rule_version="v1")
    retired = ClinicalRule(rule_type=FindingType.DDI, pair_key="e||f", ingredient_a="e", ingredient_b="f",
                            severity=Severity.CAUTION, status=RuleStatus.RETIRED, rule_version="v1")
    session.add_all([draft, rejected, retired])
    session.flush()
    rules = approved_rules(session)
    ids = {r.id for r in rules}
    assert approved_rule.id in ids
    assert draft.id not in ids
    assert rejected.id not in ids
    assert retired.id not in ids


# ── RETIRED rule state — HTTP layer ──────────────────────────────────────────

def _seed_reviewer_with_approved_rule():
    init_db()
    with get_session() as session:
        org = Organization(name="Retirement Test Hospital")
        session.add(org)
        session.flush()
        suffix = uuid.uuid4().hex[:8]
        pharmacist = User(organization_id=org.id, email=f"retire-pharm-{suffix}@example.com",
                           password_hash="x", role=UserRole.PHARMACIST)
        patient_account = User(organization_id=org.id, email=f"retire-patient-{suffix}@example.com",
                                password_hash="x", role=UserRole.PATIENT)
        session.add_all([pharmacist, patient_account])
        session.flush()
        rule = ClinicalRule(
            rule_type=FindingType.DDI, pair_key=f"retiredrug1-{suffix}||retiredrug2-{suffix}",
            ingredient_a=f"retiredrug1-{suffix}", ingredient_b=f"retiredrug2-{suffix}",
            severity=Severity.MAJOR, status=RuleStatus.APPROVED, rule_version="v1",
        )
        draft_rule = ClinicalRule(
            rule_type=FindingType.DDI, pair_key=f"draftdrug1-{suffix}||draftdrug2-{suffix}",
            ingredient_a=f"draftdrug1-{suffix}", ingredient_b=f"draftdrug2-{suffix}",
            severity=Severity.CAUTION, status=RuleStatus.DRAFT, rule_version="v1",
        )
        session.add_all([rule, draft_rule])
        session.flush()
        ids = {
            "pharmacist_id": pharmacist.id, "patient_user_id": patient_account.id,
            "rule_id": rule.id, "draft_rule_id": draft_rule.id,
        }
    with flask_app.app_context():
        tokens = {
            f"{name}_token": create_access_token(identity=ids[f"{name}_id" if name != "patient" else "patient_user_id"])
            for name in ("pharmacist", "patient")
        }
    return {**ids, **tokens}


def test_pharmacist_can_retire_an_approved_rule_end_to_end():
    ids = _seed_reviewer_with_approved_rule()
    client = flask_app.test_client()
    pharm_auth = {"Authorization": f"Bearer {ids['pharmacist_token']}"}

    resp = client.post(
        f"/v1/clinical-rules/{ids['rule_id']}/review",
        json={"decision": "retired"},
        headers=pharm_auth,
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "retired"


def test_retiring_a_draft_rule_via_http_returns_400_not_500():
    ids = _seed_reviewer_with_approved_rule()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/clinical-rules/{ids['draft_rule_id']}/review",
        json={"decision": "retired"},
        headers={"Authorization": f"Bearer {ids['pharmacist_token']}"},
    )
    assert resp.status_code == 400


def test_approved_rules_endpoint_lists_the_rule_and_excludes_draft():
    ids = _seed_reviewer_with_approved_rule()
    client = flask_app.test_client()
    resp = client.get("/v1/clinical-rules/approved", headers={"Authorization": f"Bearer {ids['pharmacist_token']}"})
    assert resp.status_code == 200
    rule_ids = {r["id"] for r in resp.get_json()["rules"]}
    assert ids["rule_id"] in rule_ids
    assert ids["draft_rule_id"] not in rule_ids


def test_patient_role_cannot_list_approved_rules():
    ids = _seed_reviewer_with_approved_rule()
    client = flask_app.test_client()
    resp = client.get("/v1/clinical-rules/approved", headers={"Authorization": f"Bearer {ids['patient_token']}"})
    assert resp.status_code == 403


# ── Explanation-service outage handling ──────────────────────────────────────

def test_explain_finding_raises_explanation_unavailable_on_groq_timeout():
    with patch("services.evidence._call_groq_api", return_value="Generation timed out. Please try again."):
        with pytest.raises(ExplanationUnavailable):
            from services.evidence import explain_finding
            explain_finding(
                finding_type="ddi", severity="major", clinical_effect="x",
                recommended_action="y", model_name="test-model",
            )


def test_explain_finding_raises_explanation_unavailable_without_leaking_raw_exception_text():
    """The raised exception's own message must stay generic — the raw
    "Generation error: <exc>" string (which can carry exception internals)
    must never reach a caller, only the server-side log."""
    with patch("services.evidence._call_groq_api", return_value="Generation error: connection reset by peer"):
        with pytest.raises(ExplanationUnavailable) as exc_info:
            from services.evidence import explain_finding
            explain_finding(
                finding_type="ddi", severity="major", clinical_effect="x",
                recommended_action="y", model_name="test-model",
            )
    assert "connection reset" not in str(exc_info.value)


def test_explain_finding_returns_normally_when_groq_succeeds():
    with patch("services.evidence._call_groq_api", return_value="A real explanation."):
        from services.evidence import explain_finding
        result = explain_finding(
            finding_type="ddi", severity="major", clinical_effect="x",
            recommended_action="y", model_name="test-model",
        )
    assert result["explanation"] == "A real explanation."


def test_guest_explain_endpoint_returns_503_not_500_on_outage():
    from unittest.mock import patch as mock_patch
    with get_session() as session:
        session.add(ClinicalRule(
            rule_type=FindingType.DDI, pair_key="outagedrug1||outagedrug2",
            ingredient_a="outagedrug1", ingredient_b="outagedrug2",
            clinical_effect="test effect", severity=Severity.MAJOR,
            status=RuleStatus.APPROVED, rule_version="v1",
        ))
    client = flask_app.test_client()
    with mock_patch("routes.public.resolve_medication_identity",
                     side_effect=lambda n: {"rxcui": None, "ingredients": [n.strip().lower()],
                                             "matched_exactly": False, "identity_confirmed": False,
                                             "resolution_method": "unresolved"}):
        with mock_patch("routes.public.explain_finding", side_effect=ExplanationUnavailable("down")):
            resp = client.post("/api/explain", json={
                "medications": ["outagedrug1", "outagedrug2"], "finding_index": 0,
            })
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"] == "explanation_unavailable"
    assert "down" not in body["message"]  # the route's own message, not the exception text


def test_clinical_explain_endpoint_returns_503_and_leaves_finding_untouched():
    from services.clinical_rules import evaluate_case
    from services.safety_case import create_case, transition_case
    from enums import PrescriptionStatus, ReviewStatus, SafetyCaseState
    from models import ClinicalProfileSnapshot, Finding, Medication, Patient, Prescription

    init_db()
    with get_session() as session:
        org = Organization(name="Outage Test Hospital")
        session.add(org)
        session.flush()
        suffix = uuid.uuid4().hex[:8]
        pharmacist = User(organization_id=org.id, email=f"outage-pharm-{suffix}@example.com",
                           password_hash="x", role=UserRole.PHARMACIST)
        session.add(pharmacist)
        session.flush()
        patient = Patient(organization_id=org.id, first_name="Outage", last_name="Test")
        medication = Medication(display_name="outage-test-drug")
        session.add_all([patient, medication])
        session.flush()
        prescription = Prescription(
            organization_id=org.id, patient_id=patient.id, prescriber_id=pharmacist.id,
            medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
        )
        snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
        session.add_all([prescription, snapshot])
        session.flush()
        case = create_case(session, org.id, prescription, snapshot)
        transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
        finding = Finding(
            case_id=case.id, type=FindingType.DDI, severity=Severity.MAJOR,
            clinical_effect="outage test interaction", review_status=ReviewStatus.PENDING,
        )
        session.add(finding)
        session.flush()
        finding_id = finding.id
        pharmacist_id = pharmacist.id

    with flask_app.app_context():
        token = create_access_token(identity=pharmacist_id)

    client = flask_app.test_client()
    with patch("routes.clinical.explain_finding", side_effect=ExplanationUnavailable("down")):
        resp = client.post(
            f"/v1/findings/{finding_id}/explain",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "explanation_unavailable"

    with get_session() as session:
        reloaded = session.get(Finding, finding_id)
        assert reloaded.explanation is None


# ── Audit coverage ────────────────────────────────────────────────────────────

def _fake_identity(name):
    return {
        "rxcui": None, "ingredients": [name.strip().lower()],
        "matched_exactly": False, "identity_confirmed": False,
        "resolution_method": "unresolved",
    }


def test_guest_self_check_writes_an_audit_event():
    client = flask_app.test_client()
    with patch("routes.public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        resp = client.post("/api/self-check", json={"medications": ["auditdrug1"]})
    assert resp.status_code == 200

    with get_session() as session:
        events = session.query(AuditEvent).filter_by(action="guest_self_check").all()
        assert len(events) >= 1
        latest = events[-1]
        assert latest.after_state["medication_count"] == 1
        # Privacy: the raw medication name must never appear in the audit trail.
        assert "auditdrug1" not in str(latest.after_state)


def test_guest_self_check_error_is_audited_and_returns_500_not_a_leak():
    client = flask_app.test_client()
    with patch("routes.public.resolve_medication_identity", side_effect=RuntimeError("boom")):
        resp = client.post("/api/self-check", json={"medications": ["anydrug"]})
    assert resp.status_code == 500
    assert "boom" not in resp.get_json()["error"]

    with get_session() as session:
        events = session.query(AuditEvent).filter_by(action="guest_self_check_error").all()
    assert len(events) >= 1


def test_login_success_is_audited_with_actor_user_id():
    from core.auth import register_user
    suffix = uuid.uuid4().hex[:8]
    with get_session() as session:
        org = Organization(name="Audit Login Hospital")
        session.add(org)
        session.flush()
        org_id = org.id
    user = register_user(
        email=f"audit-login-{suffix}@example.com", password="correcthorsebattery",
        organization_id=org_id, full_name="Audit Login", first_name="Audit", last_name="Login",
    )

    client = flask_app.test_client()
    resp = client.post("/api/auth/login", json={
        "email": f"audit-login-{suffix}@example.com", "password": "correcthorsebattery",
    })
    assert resp.status_code == 200

    with get_session() as session:
        events = session.query(AuditEvent).filter_by(action="auth.login_success").all()
        matching = [e for e in events if e.actor_user_id == user["id"]]
        assert len(matching) >= 1


def test_login_failure_is_audited_without_a_real_user_subject_id():
    suffix = uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    resp = client.post("/api/auth/login", json={
        "email": f"nonexistent-{suffix}@example.com", "password": "wrongpassword",
    })
    assert resp.status_code == 401

    with get_session() as session:
        events = session.query(AuditEvent).filter_by(action="auth.login_failed").all()
        matching = [e for e in events if e.after_state and e.after_state.get("email") == f"nonexistent-{suffix}@example.com"]
        assert len(matching) >= 1
        assert matching[-1].actor_user_id is None


def test_register_success_and_failure_are_both_audited():
    suffix = uuid.uuid4().hex[:8]
    with get_session() as session:
        org = Organization(name="Audit Register Hospital")
        session.add(org)
        session.flush()
        org_id = org.id

    client = flask_app.test_client()
    ok_resp = client.post("/api/auth/register", json={
        "email": f"audit-reg-{suffix}@example.com", "password": "correcthorsebattery",
        "organization_id": org_id, "first_name": "Audit", "last_name": "Reg",
    })
    assert ok_resp.status_code == 201

    dup_resp = client.post("/api/auth/register", json={
        "email": f"audit-reg-{suffix}@example.com", "password": "correcthorsebattery",
        "organization_id": org_id, "first_name": "Audit", "last_name": "Reg",
    })
    assert dup_resp.status_code == 400

    with get_session() as session:
        success_events = session.query(AuditEvent).filter_by(action="auth.register_success").all()
        failed_events = session.query(AuditEvent).filter_by(action="auth.register_failed").all()
        assert any(e.after_state.get("email") == f"audit-reg-{suffix}@example.com" for e in success_events)
        assert any(e.after_state.get("email") == f"audit-reg-{suffix}@example.com" for e in failed_events)


# ── Prototype-mode gating on real patient-record creation ───────────────────

def _seed_clinical_staff():
    init_db()
    with get_session() as session:
        org = Organization(name="Prototype Gate Hospital")
        session.add(org)
        session.flush()
        suffix = uuid.uuid4().hex[:8]
        pharmacist = User(organization_id=org.id, email=f"gate-pharm-{suffix}@example.com",
                           password_hash="x", role=UserRole.PHARMACIST)
        session.add(pharmacist)
        session.flush()
        pharmacist_id = pharmacist.id
    with flask_app.app_context():
        token = create_access_token(identity=pharmacist_id)
    return token


def test_creating_a_patient_without_acknowledgment_is_refused_in_prototype_mode():
    token = _seed_clinical_staff()
    client = flask_app.test_client()
    with patch("routes.clinical.PROTOTYPE_MODE", True):
        resp = client.post(
            "/v1/patients",
            json={"first_name": "Jane", "last_name": "Doe"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "synthetic_data_acknowledgment_required"


def test_creating_a_patient_with_acknowledgment_succeeds_in_prototype_mode():
    token = _seed_clinical_staff()
    client = flask_app.test_client()
    with patch("routes.clinical.PROTOTYPE_MODE", True):
        resp = client.post(
            "/v1/patients",
            json={"first_name": "Jane", "last_name": "Doe", "synthetic_data_acknowledged": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201

    from models import Patient
    with get_session() as session:
        patient = session.get(Patient, resp.get_json()["patient_id"])
        assert patient.is_synthetic_data is True


def test_patient_creation_gate_is_off_when_prototype_mode_is_disabled():
    token = _seed_clinical_staff()
    client = flask_app.test_client()
    with patch("routes.clinical.PROTOTYPE_MODE", False):
        resp = client.post(
            "/v1/patients",
            json={"first_name": "Jane", "last_name": "Doe"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201


# ── Infrastructure-failure handling ──────────────────────────────────────────

def test_self_check_survives_database_outage_during_both_the_lookup_and_the_audit_write():
    """The real bug this guards against: the original fix wrapped the
    lookup in try/except and tried to audit-log the failure — but the
    audit write used the SAME get_session(), so if the database is what's
    actually down, that fallback write raised again and crashed past the
    safe response. _try_audit() must swallow that second failure too."""
    client = flask_app.test_client()
    with patch("routes.public.get_session", side_effect=RuntimeError("database unreachable")):
        resp = client.post("/api/self-check", json={"medications": ["anydrug"]})
    assert resp.status_code == 500
    assert "database unreachable" not in resp.get_json()["error"]


def test_login_survives_database_outage_during_the_audit_write():
    """authenticate_user() succeeds using its own session (auth.py imports
    get_session directly from database.py); the audit write afterward goes
    through app.py's own get_session reference. Failing only that second
    one simulates "the database went down between the successful auth
    check and the audit write" — login() must still return 200, not a 500
    from _try_audit()'s own failure."""
    from core.auth import register_user
    suffix = uuid.uuid4().hex[:8]
    with get_session() as session:
        org = Organization(name="Outage Login Hospital")
        session.add(org)
        session.flush()
        org_id = org.id
    register_user(
        email=f"outage-login-{suffix}@example.com", password="correcthorsebattery",
        organization_id=org_id, full_name="Outage Login", first_name="Outage", last_name="Login",
    )

    client = flask_app.test_client()
    with patch("app.get_session", side_effect=RuntimeError("database unreachable")):
        resp = client.post("/api/auth/login", json={
            "email": f"outage-login-{suffix}@example.com", "password": "correcthorsebattery",
        })
    assert resp.status_code == 200


# ── Malformed-input handling ─────────────────────────────────────────────────

@pytest.mark.parametrize("payload", [
    {"medications": "not-a-list"},  # non-list medications -> coerces to []
    {"medications": 12345},
    {"medications": None},
    {},
])
def test_self_check_rejects_malformed_medications_with_400_not_a_crash(payload):
    """_clean_str_list() coerces any non-list `medications` value to [] —
    these all collapse to "no medications provided" (400), not an
    exception (500)."""
    client = flask_app.test_client()
    resp = client.post("/api/self-check", json=payload)
    assert resp.status_code == 400


@pytest.mark.parametrize("payload", [
    # A non-empty medications list with garbage items, or a malformed
    # (non-list) allergies value, degrades gracefully rather than being
    # rejected: safe_str() coerces each medication item to a string (so
    # these just become odd-looking "drug names" nothing matches), and a
    # malformed allergies value coerces to [] the same way medications
    # does. The property that actually matters is "never crashes" — this
    # is deliberately permissive, not a validation gap, since nothing here
    # can cause an unsafe clinical conclusion (unmatched names simply
    # produce no findings, never a false "safe").
    {"medications": [None, 123, {}, [], True]},
    {"medications": ["validdrug"], "allergies": "also-not-a-list"},
    {"medications": ["validdrug"], "allergies": {"nested": "object"}},
])
def test_self_check_never_500s_on_malformed_but_non_empty_input(payload):
    client = flask_app.test_client()
    with patch("routes.public.resolve_medication_identity",
               side_effect=lambda n: {"rxcui": None, "ingredients": [n.strip().lower()],
                                       "matched_exactly": False, "identity_confirmed": False,
                                       "resolution_method": "unresolved"}):
        resp = client.post("/api/self-check", json=payload)
    assert resp.status_code != 500


def test_self_check_rejects_non_json_body_without_crashing():
    client = flask_app.test_client()
    resp = client.post("/api/self-check", data="not json at all", content_type="text/plain")
    assert resp.status_code == 400


# ── Privacy ───────────────────────────────────────────────────────────────────

def test_explain_endpoint_never_persists_patient_notes_text_in_audit():
    with get_session() as session:
        session.add(ClinicalRule(
            rule_type=FindingType.DDI, pair_key="privacydrug1||privacydrug2",
            ingredient_a="privacydrug1", ingredient_b="privacydrug2",
            clinical_effect="test effect", severity=Severity.MAJOR,
            status=RuleStatus.APPROVED, rule_version="v1",
        ))
    client = flask_app.test_client()
    secret_notes = "I have a rare condition called XYZSYNDROME12345"
    with patch("routes.public.resolve_medication_identity",
               side_effect=lambda n: {"rxcui": None, "ingredients": [n.strip().lower()],
                                       "matched_exactly": False, "identity_confirmed": False,
                                       "resolution_method": "unresolved"}), \
         patch("routes.public.explain_finding", return_value={
             "explanation": "ok", "citations": [], "evidence_hash": "h",
         }):
        resp = client.post("/api/explain", json={
            "medications": ["privacydrug1", "privacydrug2"],
            "finding_index": 0, "patient_notes": secret_notes,
        })
    assert resp.status_code == 200

    with get_session() as session:
        recent = session.query(AuditEvent).filter_by(action="guest_explain_success").all()
        assert recent, "expected at least one guest_explain_success audit event"
        for event in recent:
            assert secret_notes not in str(event.after_state)


def test_login_failure_audit_never_includes_the_attempted_password():
    suffix = uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/api/auth/login", json={
        "email": f"privacy-login-{suffix}@example.com", "password": "SuperSecretPassword123!",
    })
    with get_session() as session:
        events = session.query(AuditEvent).filter_by(action="auth.login_failed").all()
        matching = [e for e in events if e.after_state and e.after_state.get("email") == f"privacy-login-{suffix}@example.com"]
        assert matching
        for event in matching:
            assert "SuperSecretPassword123!" not in str(event.after_state)


# ── Kill switches ─────────────────────────────────────────────────────────────

def test_self_check_kill_switch_returns_503_when_active():
    client = flask_app.test_client()
    with patch("routes.public.KILL_SWITCH_SELF_CHECK", True):
        resp = client.post("/api/self-check", json={"medications": ["anydrug"]})
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "temporarily_unavailable"


def test_self_check_works_normally_when_kill_switch_is_off():
    client = flask_app.test_client()
    with patch("routes.public.KILL_SWITCH_SELF_CHECK", False), \
         patch("routes.public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        resp = client.post("/api/self-check", json={"medications": ["anydrug"]})
    assert resp.status_code == 200


def test_explain_kill_switch_returns_503_when_active():
    client = flask_app.test_client()
    with patch("routes.public.KILL_SWITCH_EXPLAIN", True):
        resp = client.post("/api/explain", json={"medications": ["anydrug"], "finding_index": 0})
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "temporarily_unavailable"


def test_kill_switches_are_independent_of_each_other():
    """Disabling explain must not also disable self-check, and vice versa
    — an incident with one shouldn't force taking down the other."""
    client = flask_app.test_client()
    with patch("routes.public.KILL_SWITCH_EXPLAIN", True), \
         patch("routes.public.KILL_SWITCH_SELF_CHECK", False), \
         patch("routes.public.resolve_medication_identity", side_effect=lambda n: _fake_identity(n)):
        self_check_resp = client.post("/api/self-check", json={"medications": ["anydrug"]})
    assert self_check_resp.status_code == 200


# ── Deep health check ─────────────────────────────────────────────────────────

def test_shallow_health_check_never_touches_the_database():
    """render.yaml's healthCheckPath points at /api/health — it must stay
    independent of the database so a transient DB blip can't make the
    hosting platform decide the whole process is dead and restart it."""
    client = flask_app.test_client()
    with patch("app.get_session", side_effect=RuntimeError("database unreachable")):
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_deep_health_check_reports_ok_when_database_is_reachable():
    client = flask_app.test_client()
    resp = client.get("/api/health/deep")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


def test_deep_health_check_reports_degraded_when_database_is_unreachable():
    client = flask_app.test_client()
    with patch("app.get_session", side_effect=RuntimeError("database unreachable")):
        resp = client.get("/api/health/deep")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["status"] == "degraded"
    assert "unreachable" in body["checks"]["database"]


def test_deep_health_check_reports_kill_switch_state():
    client = flask_app.test_client()
    with patch("app.KILL_SWITCH_SELF_CHECK", True):
        resp = client.get("/api/health/deep")
    assert resp.get_json()["checks"]["self_check_kill_switch"] == "disabled"

"""
HTTP-layer test for the Phase 5 professional-workflow API
(/v1/safety-cases, /v1/interventions) — proves the service layer already
covered by test_vertical_slice.py is correctly wired behind real routes
with JWT auth.
"""

import uuid

from flask_jwt_extended import create_access_token

from app import flask_app
from database import get_session, init_db
from enums import (
    FindingType, PrescriberDecision, PrescriptionStatus, ReviewStatus,
    RuleStatus, SafetyCaseState, Severity, UserRole,
)
from models import (
    ClinicalProfileSnapshot, ClinicalRule, Finding, Medication, Organization,
    Patient, Prescription, User,
)
from services.safety_case import create_case, transition_case


def _seed_case_awaiting_review():
    init_db()
    with get_session() as session:
        org = Organization(name="API Test Hospital")
        session.add(org)
        session.flush()

        suffix = uuid.uuid4().hex[:8]
        # role= must be explicit — User.role defaults to UserRole.PATIENT
        # (models.py), and these routes now enforce role, not just tenant
        # membership (authz.py). Before that enforcement existed this was
        # silently harmless; now a defaulted PATIENT role here would make
        # every assess/intervention call below correctly get rejected.
        pharmacist = User(organization_id=org.id, email=f"api-pharm-{suffix}@example.com", password_hash="x", role=UserRole.PHARMACIST)
        prescriber = User(organization_id=org.id, email=f"api-doc-{suffix}@example.com", password_hash="x", role=UserRole.PRESCRIBER)
        session.add_all([pharmacist, prescriber])
        session.flush()

        patient = Patient(organization_id=org.id, first_name="Api", last_name="Test")
        medication = Medication(display_name="warfarin-api-test")
        session.add_all([patient, medication])
        session.flush()

        prescription = Prescription(
            organization_id=org.id, patient_id=patient.id, prescriber_id=prescriber.id,
            medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
        )
        snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
        session.add_all([prescription, snapshot])
        session.flush()

        case = create_case(session, org.id, prescription, snapshot)
        transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
        finding = Finding(
            case_id=case.id, type=FindingType.DDI, severity=Severity.MAJOR,
            clinical_effect="test interaction", review_status=ReviewStatus.PENDING,
        )
        session.add(finding)
        session.flush()
        transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW)

        ids = {
            "org_id": org.id, "pharmacist_id": pharmacist.id, "prescriber_id": prescriber.id,
            "case_id": case.id, "finding_id": finding.id,
        }

    with flask_app.app_context():
        pharmacist_token = create_access_token(identity=ids["pharmacist_id"])
        prescriber_token = create_access_token(identity=ids["prescriber_id"])

    return {**ids, "pharmacist_token": pharmacist_token, "prescriber_token": prescriber_token}


def test_pharmacist_queue_lists_the_case():
    ids = _seed_case_awaiting_review()
    client = flask_app.test_client()

    resp = client.get(
        "/v1/safety-cases/queue",
        headers={"Authorization": f"Bearer {ids['pharmacist_token']}"},
    )
    assert resp.status_code == 200
    case_ids = {c["id"] for c in resp.get_json()["cases"]}
    assert ids["case_id"] in case_ids


def test_queue_requires_auth():
    _seed_case_awaiting_review()
    client = flask_app.test_client()
    resp = client.get("/v1/safety-cases/queue")
    assert resp.status_code == 401


def test_full_intervention_flow_over_http():
    ids = _seed_case_awaiting_review()
    client = flask_app.test_client()
    pharm_auth = {"Authorization": f"Bearer {ids['pharmacist_token']}"}
    doc_auth = {"Authorization": f"Bearer {ids['prescriber_token']}"}

    assess_resp = client.post(
        f"/v1/safety-cases/{ids['case_id']}/findings/assess",
        json={"decisions": {ids["finding_id"]: "accepted"}},
        headers=pharm_auth,
    )
    assert assess_resp.status_code == 200
    assert assess_resp.get_json()["state"] == "awaiting_prescriber_response"

    create_resp = client.post(
        "/v1/interventions",
        json={
            "case_id": ids["case_id"], "target_prescriber_id": ids["prescriber_id"],
            "finding_id": ids["finding_id"], "urgency": "major",
            "question_or_recommendation": "Continue or hold?",
        },
        headers=pharm_auth,
    )
    assert create_resp.status_code == 201
    intervention_id = create_resp.get_json()["intervention_id"]

    respond_resp = client.post(
        f"/v1/interventions/{intervention_id}/response",
        json={
            "decision": "continue_with_rationale",
            "rationale": "Benefit outweighs risk.",
            "monitoring_plan": "Weekly INR for 4 weeks.",
        },
        headers=doc_auth,
    )
    assert respond_resp.status_code == 200
    assert respond_resp.get_json()["state"] == "ready_to_dispense"

    timeline_resp = client.get(f"/v1/safety-cases/{ids['case_id']}/timeline", headers=pharm_auth)
    assert timeline_resp.status_code == 200
    actions = [e["action"] for e in timeline_resp.get_json()["timeline"]]
    assert "prescriber_response.recorded" in actions


def test_invalid_decision_value_rejected():
    ids = _seed_case_awaiting_review()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/safety-cases/{ids['case_id']}/findings/assess",
        json={"decisions": {ids["finding_id"]: "not_a_real_status"}},
        headers={"Authorization": f"Bearer {ids['pharmacist_token']}"},
    )
    assert resp.status_code == 400


def test_user_from_a_different_organization_cannot_see_or_act_on_the_case():
    org_a_ids = _seed_case_awaiting_review()
    org_b_ids = _seed_case_awaiting_review()
    client = flask_app.test_client()
    org_b_auth = {"Authorization": f"Bearer {org_b_ids['pharmacist_token']}"}

    # Org B's queue must not contain org A's case.
    queue_resp = client.get("/v1/safety-cases/queue", headers=org_b_auth)
    assert org_a_ids["case_id"] not in {c["id"] for c in queue_resp.get_json()["cases"]}

    # Org B cannot read org A's case timeline.
    timeline_resp = client.get(f"/v1/safety-cases/{org_a_ids['case_id']}/timeline", headers=org_b_auth)
    assert timeline_resp.status_code == 404

    # Org B cannot assess findings on org A's case.
    assess_resp = client.post(
        f"/v1/safety-cases/{org_a_ids['case_id']}/findings/assess",
        json={"decisions": {org_a_ids["finding_id"]: "accepted"}},
        headers=org_b_auth,
    )
    assert assess_resp.status_code == 404

    # Org B cannot create an intervention against org A's case.
    create_resp = client.post(
        "/v1/interventions",
        json={
            "case_id": org_a_ids["case_id"], "target_prescriber_id": org_a_ids["prescriber_id"],
            "question_or_recommendation": "Should not be allowed.",
        },
        headers=org_b_auth,
    )
    assert create_resp.status_code == 404

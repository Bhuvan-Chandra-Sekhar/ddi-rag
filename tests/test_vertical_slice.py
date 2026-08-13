"""
Phase 5 exit gate / doc section 14 "First vertical slice to code":
one complete synthetic case, demonstrable end to end, from prescription
through patient communication, with a reproducible immutable timeline.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from enums import (
    DeliveryChannel, DispensingStatus, PrescriberDecision, PrescriptionStatus,
    ReviewStatus, RuleStatus, SafetyCaseState, Severity, FindingType,
)
from models import (
    ClinicalProfileSnapshot, ClinicalRule, Finding, Medication, Organization,
    Patient, Prescription, User,
)
from services.professional_workflow import (
    assess_findings_and_route, create_intervention, pharmacist_queue,
    record_dispensing_outcome, record_prescriber_response, run_case_analysis,
    send_patient_communication, case_timeline,
)
from services.safety_case import create_case, transition_case


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
def scenario(session):
    org = Organization(name="Synthetic General Hospital")
    session.add(org)
    session.flush()

    pharmacist = User(organization_id=org.id, email="pharm@example.com", password_hash="x", full_name="Pat Pharmacist")
    prescriber = User(organization_id=org.id, email="doc@example.com", password_hash="x", full_name="Dr. Prescriber")
    session.add_all([pharmacist, prescriber])
    session.flush()

    # Step 1: synthetic patient with demographics, existing medication,
    # allergy, condition, and one lab result.
    patient = Patient(
        organization_id=org.id, first_name="Jane", last_name="Synthetic",
        sex="female", consent_directives={"research_use": False},
    )
    session.add(patient)
    session.flush()

    snapshot = ClinicalProfileSnapshot(
        patient_id=patient.id,
        medications=["aspirin"],
        allergies=["penicillin"],
        conditions=["atrial_fibrillation"],
        labs=[{"name": "INR", "value": 1.1}],
    )
    session.add(snapshot)

    # Step 2: new prescription, normalized medication (Phase 2 already
    # covered separately by test_medication_identity.py).
    warfarin = Medication(display_name="warfarin", rxcui="11289", identity_confirmed=True)
    session.add(warfarin)
    session.flush()

    prescription = Prescription(
        organization_id=org.id, patient_id=patient.id, prescriber_id=prescriber.id,
        medication_id=warfarin.id, dose="5mg", route="oral", frequency="daily",
        status=PrescriptionStatus.ACTIVE,
    )
    session.add(prescription)

    # A clinically-approved DDI rule between the new drug and the patient's
    # existing medication, so the vertical slice has an actionable finding.
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="aspirin||warfarin",
        ingredient_a="aspirin", ingredient_b="warfarin",
        clinical_effect="Concurrent aspirin and warfarin increases bleeding risk.",
        severity=Severity.MAJOR, status=RuleStatus.APPROVED, rule_version="v1",
    ))
    session.flush()

    case = create_case(session, org.id, prescription, snapshot, actor_user_id=prescriber.id)

    return {
        "session": session, "org": org, "patient": patient, "snapshot": snapshot,
        "prescriber": prescriber, "pharmacist": pharmacist, "prescription": prescription,
        "medication": warfarin, "case": case,
    }


def test_full_case_journey_prescription_through_patient_communication(scenario):
    session, case = scenario["session"], scenario["case"]
    prescriber, pharmacist = scenario["prescriber"], scenario["pharmacist"]

    # Steps 3-4: deterministic rules + evidence (evidence retrieval is
    # exercised/tested separately in test_evidence.py; here we prove the
    # workflow routes correctly on the resulting finding).
    findings = run_case_analysis(
        session, case,
        ingredient_names=["aspirin", "warfarin"],
        allergy_names=["penicillin"],
        actor_user_id=None,
    )
    assert case.state == SafetyCaseState.AWAITING_PHARMACIST_REVIEW
    ddi_findings = [f for f in findings if f.type == FindingType.DDI]
    assert len(ddi_findings) == 1
    assert ddi_findings[0].severity == Severity.MAJOR

    # Step 5: case sits in the pharmacist queue.
    queue = pharmacist_queue(session, scenario["org"].id)
    assert case.id in {c.id for c in queue}

    # Pharmacist assesses all findings -> routes to prescriber (MAJOR finding).
    decisions = {f.id: ReviewStatus.ACCEPTED for f in findings}
    next_state = assess_findings_and_route(session, case, decisions, actor_user_id=pharmacist.id)
    assert next_state == SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE

    # Step 6: intervention sent to the synthetic prescriber.
    intervention = create_intervention(
        session, case, created_by_user_id=pharmacist.id, target_prescriber_id=prescriber.id,
        finding_id=ddi_findings[0].id, urgency=Severity.MAJOR,
        question_or_recommendation="Continue warfarin with aspirin, or hold one agent?",
    )

    # Step 7: prescriber responds (continue-with-rationale path).
    record_prescriber_response(
        session, case, intervention, responder_user_id=prescriber.id,
        decision=PrescriberDecision.CONTINUE_WITH_RATIONALE,
        rationale="Benefit outweighs risk for this patient; monitor INR weekly.",
        monitoring_plan="Weekly INR for 4 weeks.",
    )
    assert case.state == SafetyCaseState.READY_TO_DISPENSE

    # Step 8: dispensing outcome.
    record_dispensing_outcome(
        session, case, status=DispensingStatus.DISPENSED,
        professional_user_id=pharmacist.id, quantity="30 tablets",
    )

    # Step 9: constrained patient explanation delivered.
    send_patient_communication(
        session, case,
        approved_explanation="Your new medication may increase bleeding risk with "
                              "your other medication; your care team will monitor you closely.",
        delivery_channel=DeliveryChannel.PORTAL,
    )

    # Case closes only now — after outcome + patient notice are both recorded.
    transition_case(session, case, SafetyCaseState.CLOSED, actor_user_id=pharmacist.id)

    # Step 10 / definition of done: complete, reproducible, immutable timeline.
    timeline = case_timeline(session, case)
    actions = [e["action"] for e in timeline]
    assert actions == [
        "safety_case.created",
        "safety_case.state_changed",   # -> awaiting_analysis
        "safety_case.analysis_completed",
        "safety_case.state_changed",   # -> awaiting_pharmacist_review
        "finding.reviewed",
        "safety_case.state_changed",   # -> awaiting_prescriber_response
        "intervention.created",
        "prescriber_response.recorded",
        "safety_case.state_changed",   # -> ready_to_dispense
        "dispensing_outcome.recorded",
        "patient_communication.sent",
        "safety_case.state_changed",   # -> closed
    ]
    assert case.state == SafetyCaseState.CLOSED
    assert case.closed_at is not None


def test_prescriber_stop_decision_holds_the_case(scenario):
    session, case = scenario["session"], scenario["case"]
    findings = run_case_analysis(session, case, ["aspirin", "warfarin"], ["penicillin"])
    assess_findings_and_route(session, case, {f.id: ReviewStatus.ACCEPTED for f in findings},
                               actor_user_id=scenario["pharmacist"].id)
    intervention = create_intervention(
        session, case, created_by_user_id=scenario["pharmacist"].id,
        target_prescriber_id=scenario["prescriber"].id,
        question_or_recommendation="Hold warfarin?",
    )
    record_prescriber_response(
        session, case, intervention, responder_user_id=scenario["prescriber"].id,
        decision=PrescriberDecision.STOP, rationale="Too risky for this patient.",
    )
    assert case.state == SafetyCaseState.HELD_OR_CANCELLED


def test_prescriber_change_decision_escalates(scenario):
    session, case = scenario["session"], scenario["case"]
    findings = run_case_analysis(session, case, ["aspirin", "warfarin"], ["penicillin"])
    assess_findings_and_route(session, case, {f.id: ReviewStatus.ACCEPTED for f in findings},
                               actor_user_id=scenario["pharmacist"].id)
    intervention = create_intervention(
        session, case, created_by_user_id=scenario["pharmacist"].id,
        target_prescriber_id=scenario["prescriber"].id,
        question_or_recommendation="Consider alternative anticoagulant?",
    )
    record_prescriber_response(
        session, case, intervention, responder_user_id=scenario["prescriber"].id,
        decision=PrescriberDecision.CHANGE, rationale="Switching to a different agent.",
    )
    assert case.state == SafetyCaseState.ESCALATED


def test_case_with_no_actionable_finding_routes_straight_to_dispense(session):
    org = Organization(name="Org2")
    session.add(org)
    session.flush()
    prescriber = User(organization_id=org.id, email="d2@example.com", password_hash="x")
    pharmacist = User(organization_id=org.id, email="p2@example.com", password_hash="x")
    patient = Patient(organization_id=org.id, first_name="John", last_name="Doe")
    session.add_all([prescriber, pharmacist, patient])
    session.flush()

    med = Medication(display_name="acetaminophen")
    snapshot = ClinicalProfileSnapshot(patient_id=patient.id, medications=[])
    session.add_all([med, snapshot])
    session.flush()

    prescription = Prescription(
        organization_id=org.id, patient_id=patient.id, prescriber_id=prescriber.id,
        medication_id=med.id, status=PrescriptionStatus.ACTIVE,
    )
    session.add(prescription)
    session.flush()

    case = create_case(session, org.id, prescription, snapshot)
    findings = run_case_analysis(session, case, ["acetaminophen"], [])
    assert findings == []

    next_state = assess_findings_and_route(session, case, {}, actor_user_id=pharmacist.id)
    assert next_state == SafetyCaseState.READY_TO_DISPENSE

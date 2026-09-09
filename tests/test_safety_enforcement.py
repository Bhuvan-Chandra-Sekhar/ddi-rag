"""
Tests for the safety-rule enforcement added on top of the Phase 1-5 build:
    - dismissing/overriding a MAJOR/CRITICAL finding requires a documented reason
    - continuing a prescription requires rationale + monitoring plan
    - concurrent writes to the same SafetyCase/Finding cannot silently clobber
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.pool import StaticPool

from database import Base
from enums import (
    FindingType, PrescriberDecision, PrescriptionStatus, ReviewStatus,
    SafetyCaseState, Severity, UserRole,
)
from models import (
    ClinicalProfileSnapshot, Finding, Medication, Organization, Patient,
    Prescription, User,
)
from services.professional_workflow import (
    assess_findings_and_route, create_intervention, record_prescriber_response,
)
from services.safety_case import create_case, transition_case


@pytest.fixture
def engine():
    return create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )


@pytest.fixture
def session(engine):
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def scenario(session):
    org = Organization(name="Enforcement Test Hospital")
    session.add(org)
    session.flush()

    pharmacist = User(organization_id=org.id, email="enf-pharm@example.com", password_hash="x", role=UserRole.PHARMACIST)
    prescriber = User(organization_id=org.id, email="enf-doc@example.com", password_hash="x", role=UserRole.PRESCRIBER)
    patient = Patient(organization_id=org.id, first_name="Enf", last_name="Test")
    session.add_all([pharmacist, prescriber, patient])
    session.flush()

    medication = Medication(display_name="test-drug")
    snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
    session.add_all([medication, snapshot])
    session.flush()

    prescription = Prescription(
        organization_id=org.id, patient_id=patient.id, prescriber_id=prescriber.id,
        medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
    )
    session.add(prescription)
    session.flush()

    case = create_case(session, org.id, prescription, snapshot)
    transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
    finding = Finding(
        case_id=case.id, type=FindingType.DDI, severity=Severity.CRITICAL,
        clinical_effect="test critical interaction", review_status=ReviewStatus.PENDING,
    )
    session.add(finding)
    session.flush()
    transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW)

    return {"session": session, "org": org, "pharmacist": pharmacist, "prescriber": prescriber,
            "case": case, "finding": finding}


def test_dismissing_critical_finding_without_reason_is_rejected(scenario):
    session, case, finding = scenario["session"], scenario["case"], scenario["finding"]
    with pytest.raises(ValueError, match="requires a documented reason"):
        assess_findings_and_route(
            session, case, {finding.id: ReviewStatus.DISMISSED},
            actor_user_id=scenario["pharmacist"].id,
        )
    # Nothing was committed — status must remain untouched.
    session.refresh(finding)
    assert finding.review_status == ReviewStatus.PENDING


def test_dismissing_critical_finding_with_reason_is_recorded_and_audited(scenario):
    session, case, finding = scenario["session"], scenario["case"], scenario["finding"]
    assess_findings_and_route(
        session, case, {finding.id: ReviewStatus.DISMISSED},
        actor_user_id=scenario["pharmacist"].id,
        reasons={finding.id: "Confirmed with prescriber verbally prior to this review; documented separately."},
    )
    session.refresh(finding)
    assert finding.review_status == ReviewStatus.DISMISSED
    assert finding.review_reason
    assert finding.reviewed_by_user_id == scenario["pharmacist"].id
    assert finding.reviewed_at is not None


def test_accepting_critical_finding_does_not_require_a_reason(scenario):
    # ACCEPTED isn't a dismissal/override — no reason should be required.
    session, case, finding = scenario["session"], scenario["case"], scenario["finding"]
    next_state = assess_findings_and_route(
        session, case, {finding.id: ReviewStatus.ACCEPTED}, actor_user_id=scenario["pharmacist"].id,
    )
    assert next_state == SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE


def test_continue_with_rationale_requires_both_rationale_and_monitoring_plan(scenario):
    session, case = scenario["session"], scenario["case"]
    assess_findings_and_route(
        session, case, {scenario["finding"].id: ReviewStatus.ACCEPTED},
        actor_user_id=scenario["pharmacist"].id,
    )
    intervention = create_intervention(
        session, case, created_by_user_id=scenario["pharmacist"].id,
        target_prescriber_id=scenario["prescriber"].id,
        question_or_recommendation="Continue?",
    )

    with pytest.raises(ValueError, match="rationale"):
        record_prescriber_response(
            session, case, intervention, responder_user_id=scenario["prescriber"].id,
            decision=PrescriberDecision.CONTINUE_WITH_RATIONALE,
            rationale="", monitoring_plan="Weekly labs.",
        )

    with pytest.raises(ValueError, match="monitoring_plan"):
        record_prescriber_response(
            session, case, intervention, responder_user_id=scenario["prescriber"].id,
            decision=PrescriberDecision.CONTINUE_WITH_RATIONALE,
            rationale="Benefit outweighs risk.", monitoring_plan="",
        )

    # Case must still be sitting where it was — neither bad call moved it.
    assert case.state == SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE

    # A complete response succeeds.
    record_prescriber_response(
        session, case, intervention, responder_user_id=scenario["prescriber"].id,
        decision=PrescriberDecision.CONTINUE_WITH_RATIONALE,
        rationale="Benefit outweighs risk.", monitoring_plan="Weekly labs.",
    )
    assert case.state == SafetyCaseState.READY_TO_DISPENSE


def test_stop_decision_does_not_require_rationale(scenario):
    # STOP isn't gated the same way — only continue-with-rationale is.
    session, case = scenario["session"], scenario["case"]
    assess_findings_and_route(
        session, case, {scenario["finding"].id: ReviewStatus.ACCEPTED},
        actor_user_id=scenario["pharmacist"].id,
    )
    intervention = create_intervention(
        session, case, created_by_user_id=scenario["pharmacist"].id,
        target_prescriber_id=scenario["prescriber"].id,
        question_or_recommendation="Hold?",
    )
    record_prescriber_response(
        session, case, intervention, responder_user_id=scenario["prescriber"].id,
        decision=PrescriberDecision.STOP,
    )
    assert case.state == SafetyCaseState.HELD_OR_CANCELLED


def test_concurrent_case_updates_cannot_silently_overwrite_each_other(engine, scenario):
    Session = sessionmaker(bind=engine)
    case_id = scenario["case"].id
    scenario["session"].commit()

    session_a = Session()
    session_b = Session()
    try:
        case_a = session_a.get(type(scenario["case"]), case_id)
        case_b = session_b.get(type(scenario["case"]), case_id)

        transition_case(session_a, case_a, SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE)
        session_a.commit()

        # session_b is holding a stale version_id — its write must not
        # silently clobber session_a's already-committed transition.
        with pytest.raises(StaleDataError):
            transition_case(session_b, case_b, SafetyCaseState.READY_TO_DISPENSE)
            session_b.commit()
    finally:
        session_a.close()
        session_b.close()

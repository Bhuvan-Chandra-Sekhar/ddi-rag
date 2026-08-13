"""
Phase 1 exit gate: a synthetic case can move through every authorized state
with a complete, append-only audit trail, and a closed case is immutable.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from enums import PrescriptionStatus, SafetyCaseState
from models import (
    AuditEvent, ClinicalProfileSnapshot, Medication, Organization,
    Patient, Prescription, User,
)
from services.safety_case import (
    CaseClosedError, InvalidTransitionError, create_case, transition_case,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def case(session):
    org = Organization(name="Test Hospital")
    prescriber = User(
        organization_id=None, email="dr@example.com",
        password_hash="x", full_name="Dr. Synthetic",
    )
    session.add(org)
    session.flush()
    prescriber.organization_id = org.id
    session.add(prescriber)

    patient = Patient(organization_id=org.id, first_name="Jane", last_name="Synthetic")
    medication = Medication(display_name="warfarin")
    session.add_all([patient, medication])
    session.flush()

    prescription = Prescription(
        organization_id=org.id, patient_id=patient.id, prescriber_id=prescriber.id,
        medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
    )
    snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
    session.add_all([prescription, snapshot])
    session.flush()

    return create_case(session, org.id, prescription, snapshot)


def test_case_moves_through_full_authorized_sequence_with_audit_trail(session, case):
    transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
    transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW)
    transition_case(session, case, SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE)
    transition_case(session, case, SafetyCaseState.READY_TO_DISPENSE)
    transition_case(session, case, SafetyCaseState.CLOSED)

    assert case.state == SafetyCaseState.CLOSED
    assert case.closed_at is not None

    events = (
        session.query(AuditEvent)
        .filter_by(subject_type="safety_case", subject_id=case.id)
        .order_by(AuditEvent.timestamp)
        .all()
    )
    # 1 creation event + 5 transition events
    assert len(events) == 6
    assert events[-1].after_state == {"state": "closed"}


def test_invalid_transition_is_rejected(session, case):
    with pytest.raises(InvalidTransitionError):
        transition_case(session, case, SafetyCaseState.CLOSED)


def test_closed_case_is_immutable(session, case):
    transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
    transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW)
    transition_case(session, case, SafetyCaseState.READY_TO_DISPENSE)
    transition_case(session, case, SafetyCaseState.CLOSED)

    with pytest.raises(CaseClosedError):
        transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)

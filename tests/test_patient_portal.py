"""
Patient self-registration (auto-provisions a linked Patient record) and the
patient-scoped /v1/my/cases endpoint — must only ever return the calling
patient's own cases, never anyone else's.
"""

import uuid

import pytest
from flask_jwt_extended import create_access_token

from app import flask_app
from auth import authenticate_user, register_user
from database import get_session, init_db
from enums import DeliveryChannel, PrescriptionStatus, SafetyCaseState
from models import (
    ClinicalProfileSnapshot, Medication, Organization, Patient, Prescription,
)
from services.professional_workflow import send_patient_communication
from services.safety_case import create_case, transition_case


@pytest.fixture
def org():
    init_db()
    with get_session() as session:
        organization = Organization(name=f"Patient Portal Test Org {uuid.uuid4().hex[:8]}")
        session.add(organization)
        session.flush()
        return organization.id


def test_register_user_with_patient_role_creates_linked_patient(org):
    email = f"patient-{uuid.uuid4().hex[:8]}@example.com"
    result = register_user(
        email=email, password="testpass123", organization_id=org,
        first_name="Jane", last_name="Doe",
    )
    assert result["patient_id"] is not None

    with get_session() as session:
        patient = session.query(Patient).filter_by(id=result["patient_id"]).first()
        assert patient.first_name == "Jane"
        assert patient.last_name == "Doe"
        assert patient.organization_id == org


def test_register_user_requires_first_and_last_name(org):
    with pytest.raises(ValueError, match="first_name and last_name"):
        register_user(
            email=f"noname-{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123", organization_id=org,
        )


def test_authenticate_user_returns_patient_id(org):
    email = f"login-{uuid.uuid4().hex[:8]}@example.com"
    register_user(
        email=email, password="testpass123", organization_id=org,
        first_name="Jo", last_name="Smith",
    )
    with flask_app.app_context():
        result = authenticate_user(email=email, password="testpass123")
    assert result["user"]["patient_id"] is not None


def _register_and_token(org, email_prefix):
    email = f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com"
    reg = register_user(
        email=email, password="testpass123", organization_id=org,
        first_name="Case", last_name="Owner",
    )
    with flask_app.app_context():
        token = create_access_token(identity=_user_id_for(email))
    return reg["patient_id"], token


def _user_id_for(email):
    from models import User
    with get_session() as session:
        return session.query(User).filter_by(email=email).first().id


def test_my_cases_returns_empty_list_when_no_cases(org):
    _, token = _register_and_token(org, "empty")
    client = flask_app.test_client()
    resp = client.get("/v1/my/cases", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["cases"] == []


def test_my_cases_returns_own_case_with_communication(org):
    patient_id, token = _register_and_token(org, "owner")

    with get_session() as session:
        patient = session.get(Patient, patient_id)
        medication = Medication(display_name="lisinopril")
        session.add(medication)
        session.flush()
        prescription = Prescription(
            organization_id=org, patient_id=patient.id, prescriber_id=patient.user_id,
            medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
        )
        snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
        session.add_all([prescription, snapshot])
        session.flush()

        case = create_case(session, org, prescription, snapshot)
        transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
        transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW)
        transition_case(session, case, SafetyCaseState.READY_TO_DISPENSE)
        send_patient_communication(
            session, case, approved_explanation="Your prescription was reviewed and released.",
            delivery_channel=DeliveryChannel.PORTAL,
        )

    client = flask_app.test_client()
    resp = client.get("/v1/my/cases", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    cases = resp.get_json()["cases"]
    assert len(cases) == 1
    assert cases[0]["medication"] == "lisinopril"
    assert cases[0]["state"] == "ready_to_dispense"
    assert cases[0]["communications"][0]["explanation"] == "Your prescription was reviewed and released."


def test_my_cases_never_returns_another_patients_case(org):
    _, patient_a_token = _register_and_token(org, "patient-a")
    patient_b_id, _ = _register_and_token(org, "patient-b")

    with get_session() as session:
        patient_b = session.get(Patient, patient_b_id)
        medication = Medication(display_name="metformin")
        session.add(medication)
        session.flush()
        prescription = Prescription(
            organization_id=org, patient_id=patient_b.id, prescriber_id=patient_b.user_id,
            medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
        )
        snapshot = ClinicalProfileSnapshot(patient_id=patient_b.id)
        session.add_all([prescription, snapshot])
        session.flush()
        create_case(session, org, prescription, snapshot)

    client = flask_app.test_client()
    resp = client.get("/v1/my/cases", headers={"Authorization": f"Bearer {patient_a_token}"})
    assert resp.status_code == 200
    assert resp.get_json()["cases"] == []

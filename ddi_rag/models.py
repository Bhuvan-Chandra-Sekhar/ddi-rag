"""
models.py — SQLAlchemy ORM models for the medication-safety platform.

Entity set follows the architecture doc, section 6 (Data model): Organization,
User, Patient, ClinicalProfileSnapshot, Medication, Prescription, SafetyCase,
Finding, Intervention, PrescriberResponse, Escalation, DispensingOutcome,
PatientCommunication, AuditEvent, KnowledgeRelease.

Snapshot rule: ClinicalProfileSnapshot and AuditEvent rows are append-only —
never update them in place. A closed SafetyCase is immutable; see
services/safety_case.py for the enforcement of that invariant.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Integer,
    String, Text,
)
from sqlalchemy.orm import relationship

from database import Base
from enums import (
    DeliveryChannel, DispensingStatus, FindingType, PrescriberDecision,
    PrescriptionStatus, ReviewStatus, RuleStatus, SafetyCaseState, Severity,
    UserRole,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id                    = Column(String(36), primary_key=True, default=_uuid)
    name                  = Column(String(255), nullable=False)
    settings              = Column(JSON, nullable=True)
    clinical_policy_version = Column(String(64), nullable=True)
    retention_policy_days = Column(Integer, nullable=True)
    created_at            = Column(DateTime, default=_now)


class User(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(255), nullable=True)
    role          = Column(SAEnum(UserRole), nullable=False, default=UserRole.PATIENT)
    mfa_enabled   = Column(Boolean, nullable=False, default=False)
    created_at    = Column(DateTime, default=_now)


class Patient(Base):
    __tablename__ = "patients"

    id           = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    user_id      = Column(String(36), ForeignKey("users.id"), nullable=True)
    mrn          = Column(String(64), nullable=True, index=True)
    first_name   = Column(String(255), nullable=False)
    last_name    = Column(String(255), nullable=False)
    date_of_birth = Column(DateTime, nullable=True)
    sex          = Column(String(32), nullable=True)
    consent_directives      = Column(JSON, nullable=True)
    disclosure_preferences  = Column(JSON, nullable=True)
    created_at   = Column(DateTime, default=_now)


class ClinicalProfileSnapshot(Base):
    """Append-only point-in-time capture of a patient's clinical context."""
    __tablename__ = "clinical_profile_snapshots"

    id            = Column(String(36), primary_key=True, default=_uuid)
    patient_id    = Column(String(36), ForeignKey("patients.id"), nullable=False)
    medications   = Column(JSON, nullable=True)
    allergies     = Column(JSON, nullable=True)
    conditions    = Column(JSON, nullable=True)
    labs          = Column(JSON, nullable=True)
    organ_status  = Column(JSON, nullable=True)
    pregnancy_status = Column(String(32), nullable=True)
    source_timestamp = Column(DateTime, nullable=True)
    captured_at   = Column(DateTime, default=_now)


class Medication(Base):
    """Normalized medication reference. rxcui/ingredients are filled by the
    Phase 2 medication-identity service; unresolved rows have rxcui=NULL."""
    __tablename__ = "medications"

    id           = Column(String(36), primary_key=True, default=_uuid)
    # Exactly as entered/typed — never overwritten by normalization, so the
    # original text is always distinguishable from the resolved identity.
    display_name = Column(String(255), nullable=False)
    rxcui        = Column(String(32), nullable=True, index=True)
    ingredients  = Column(JSON, nullable=True)
    strength     = Column(String(128), nullable=True)
    dose_form    = Column(String(128), nullable=True)
    route        = Column(String(128), nullable=True)
    identity_confirmed = Column(Boolean, nullable=False, default=False)
    # How rxcui/ingredients were derived: "exact_match", "approximate_match",
    # or "unresolved" — and the resolver logic version, so a historical
    # decision can always be traced back to the method/version that made it.
    resolution_method  = Column(String(32), nullable=True)
    resolution_version = Column(String(32), nullable=True)
    created_at   = Column(DateTime, default=_now)


class Prescription(Base):
    __tablename__ = "prescriptions"

    id             = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    patient_id     = Column(String(36), ForeignKey("patients.id"), nullable=False)
    prescriber_id  = Column(String(36), ForeignKey("users.id"), nullable=False)
    medication_id  = Column(String(36), ForeignKey("medications.id"), nullable=False)
    encounter_id   = Column(String(64), nullable=True)
    dose           = Column(String(128), nullable=True)
    route          = Column(String(128), nullable=True)
    frequency      = Column(String(128), nullable=True)
    start_date     = Column(DateTime, nullable=True)
    end_date       = Column(DateTime, nullable=True)
    status         = Column(SAEnum(PrescriptionStatus), nullable=False,
                             default=PrescriptionStatus.ACTIVE)
    created_at     = Column(DateTime, default=_now)


class SafetyCase(Base):
    """
    Central workflow object. State transitions are governed by
    services/safety_case.py — do not mutate `state` directly.
    """
    __tablename__ = "safety_cases"

    id                    = Column(String(36), primary_key=True, default=_uuid)
    organization_id       = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    prescription_id       = Column(String(36), ForeignKey("prescriptions.id"), nullable=False)
    profile_snapshot_id   = Column(String(36), ForeignKey("clinical_profile_snapshots.id"), nullable=False)
    state                 = Column(SAEnum(SafetyCaseState), nullable=False,
                                    default=SafetyCaseState.DRAFT)
    owner_user_id         = Column(String(36), ForeignKey("users.id"), nullable=True)
    deadline_at           = Column(DateTime, nullable=True)
    created_at            = Column(DateTime, default=_now)
    updated_at            = Column(DateTime, default=_now, onupdate=_now)
    closed_at             = Column(DateTime, nullable=True)
    # Optimistic concurrency: SQLAlchemy bumps this on every UPDATE and
    # raises StaleDataError if a concurrent transaction already moved it —
    # two simultaneous writes to the same case can no longer silently
    # clobber each other.
    version_id            = Column(Integer, nullable=False, default=1)

    findings = relationship("Finding", backref="case")

    __mapper_args__ = {"version_id_col": version_id}


class Finding(Base):
    __tablename__ = "findings"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    case_id             = Column(String(36), ForeignKey("safety_cases.id"), nullable=False)
    type                = Column(SAEnum(FindingType), nullable=False)
    severity            = Column(SAEnum(Severity), nullable=False, default=Severity.UNKNOWN)
    clinical_effect      = Column(Text, nullable=True)
    recommended_action  = Column(Text, nullable=True)
    evidence_refs       = Column(JSON, nullable=True)
    patient_factors     = Column(JSON, nullable=True)
    missing_factors     = Column(JSON, nullable=True)
    review_status       = Column(SAEnum(ReviewStatus), nullable=False, default=ReviewStatus.PENDING)
    review_reason       = Column(Text, nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at         = Column(DateTime, nullable=True)
    explanation         = Column(Text, nullable=True)
    explanation_model_version  = Column(String(64), nullable=True)
    explanation_prompt_version = Column(String(64), nullable=True)
    evidence_hash       = Column(String(128), nullable=True)
    created_at          = Column(DateTime, default=_now)
    version_id          = Column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version_id}


class Intervention(Base):
    __tablename__ = "interventions"

    id                    = Column(String(36), primary_key=True, default=_uuid)
    case_id               = Column(String(36), ForeignKey("safety_cases.id"), nullable=False)
    finding_id            = Column(String(36), ForeignKey("findings.id"), nullable=True)
    created_by_user_id    = Column(String(36), ForeignKey("users.id"), nullable=False)
    target_prescriber_id  = Column(String(36), ForeignKey("users.id"), nullable=False)
    urgency               = Column(SAEnum(Severity), nullable=False, default=Severity.CAUTION)
    question_or_recommendation = Column(Text, nullable=False)
    created_at            = Column(DateTime, default=_now)


class PrescriberResponse(Base):
    __tablename__ = "prescriber_responses"

    id               = Column(String(36), primary_key=True, default=_uuid)
    intervention_id  = Column(String(36), ForeignKey("interventions.id"), nullable=False)
    responder_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    decision         = Column(SAEnum(PrescriberDecision), nullable=False)
    rationale        = Column(Text, nullable=True)
    monitoring_plan  = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=_now)


class Escalation(Base):
    __tablename__ = "escalations"

    id             = Column(String(36), primary_key=True, default=_uuid)
    case_id        = Column(String(36), ForeignKey("safety_cases.id"), nullable=False)
    policy         = Column(String(255), nullable=True)
    recipient_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    reason         = Column(Text, nullable=False)
    resolution     = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=_now)
    resolved_at    = Column(DateTime, nullable=True)


class DispensingOutcome(Base):
    __tablename__ = "dispensing_outcomes"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    case_id             = Column(String(36), ForeignKey("safety_cases.id"), nullable=False)
    status              = Column(SAEnum(DispensingStatus), nullable=False)
    quantity            = Column(String(64), nullable=True)
    professional_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    occurred_at         = Column(DateTime, default=_now)


class PatientCommunication(Base):
    __tablename__ = "patient_communications"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    case_id             = Column(String(36), ForeignKey("safety_cases.id"), nullable=False)
    approved_explanation = Column(Text, nullable=False)
    delivery_channel    = Column(SAEnum(DeliveryChannel), nullable=False)
    delivered_at        = Column(DateTime, nullable=True)
    acknowledged_at     = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=_now)


class AuditEvent(Base):
    """Append-only. Never update or delete a row — see services/audit.py."""
    __tablename__ = "audit_events"

    id             = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True)
    actor_user_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    action         = Column(String(128), nullable=False)
    subject_type   = Column(String(64), nullable=False)
    subject_id     = Column(String(36), nullable=False)
    request_id     = Column(String(64), nullable=True)
    before_state   = Column(JSON, nullable=True)
    after_state    = Column(JSON, nullable=True)
    timestamp      = Column(DateTime, default=_now)


class ClinicalRule(Base):
    """
    A normalized drug-pair (or future rule-class) candidate mined from a raw
    source dataset. `pair_key` is the two ingredient names lower-cased and
    sorted, so lookup is order-independent. Rows start DRAFT and are
    clinically inert until `status` becomes APPROVED by a qualified
    reviewer — see services/clinical_rules.py for enforcement.
    """
    __tablename__ = "clinical_rules"

    id                = Column(String(36), primary_key=True, default=_uuid)
    rule_type         = Column(SAEnum(FindingType), nullable=False, default=FindingType.DDI)
    pair_key          = Column(String(512), nullable=True, index=True)
    ingredient_a      = Column(String(255), nullable=True)
    ingredient_b      = Column(String(255), nullable=True)
    clinical_effect   = Column(Text, nullable=True)
    severity          = Column(SAEnum(Severity), nullable=False, default=Severity.UNKNOWN)
    source_description = Column(Text, nullable=True)
    source_dataset    = Column(String(255), nullable=True)
    status            = Column(SAEnum(RuleStatus), nullable=False, default=RuleStatus.DRAFT)
    rule_version      = Column(String(64), nullable=True)
    reviewer_user_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at       = Column(DateTime, nullable=True)
    created_at        = Column(DateTime, default=_now)


class KnowledgeRelease(Base):
    __tablename__ = "knowledge_releases"

    id             = Column(String(36), primary_key=True, default=_uuid)
    name           = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    rule_version   = Column(String(64), nullable=False)
    evidence_version = Column(String(64), nullable=True)
    reviewer_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    effective_at   = Column(DateTime, nullable=False)
    rollback_at    = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=_now)

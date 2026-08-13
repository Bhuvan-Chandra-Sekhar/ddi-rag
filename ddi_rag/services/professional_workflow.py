"""
services/professional_workflow.py — Pharmacist queue, prescriber
intervention, escalation, dispensing, and patient communication
(architecture doc, section 4 "Role-based applications" + roadmap Phase 5).

This module is the orchestration layer: it calls the deterministic rule
engine (services/clinical_rules) to populate findings, drives the
SafetyCase state machine (services/safety_case) as pharmacists and
prescribers act, and records every step as an audit event. It contains no
clinical judgment of its own — severity/action always come from
clinical_rules, never from this module.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from enums import (
    DispensingStatus, PrescriberDecision, ReviewStatus, SafetyCaseState,
    Severity,
)
from models import (
    DispensingOutcome, Escalation, Finding, Intervention, PatientCommunication,
    PrescriberResponse, SafetyCase,
)
from services.audit import record_audit_event
from services.clinical_rules import evaluate_case
from services.safety_case import transition_case

_ROUTE_TO_PRESCRIBER = {Severity.MAJOR, Severity.CRITICAL}
_SEVERE = {Severity.MAJOR, Severity.CRITICAL}
_REQUIRES_REASON = {ReviewStatus.DISMISSED, ReviewStatus.OVERRIDDEN}


def run_case_analysis(
    session,
    case: SafetyCase,
    ingredient_names: Sequence[str],
    allergy_names: Sequence[str] = (),
    actor_user_id: Optional[str] = None,
) -> List[Finding]:
    """Evaluation order steps 4-7 (doc section 5.1): evaluate deterministic
    rules, persist findings, then route to the pharmacist queue."""
    transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS, actor_user_id=actor_user_id)

    finding_dicts = evaluate_case(session, ingredient_names, allergy_names)
    findings = []
    for fd in finding_dicts:
        finding = Finding(case_id=case.id, **fd)
        session.add(finding)
        findings.append(finding)
    session.flush()

    record_audit_event(
        session, action="safety_case.analysis_completed", subject_type="safety_case",
        subject_id=case.id, organization_id=case.organization_id, actor_user_id=actor_user_id,
        after={"finding_count": len(findings)},
    )

    transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW, actor_user_id=actor_user_id)
    return findings


def pharmacist_queue(session, organization_id: str) -> List[SafetyCase]:
    return (
        session.query(SafetyCase)
        .filter_by(organization_id=organization_id, state=SafetyCaseState.AWAITING_PHARMACIST_REVIEW)
        .all()
    )


def assess_findings_and_route(
    session,
    case: SafetyCase,
    decisions: Dict[str, ReviewStatus],
    actor_user_id: str,
    reasons: Optional[Dict[str, str]] = None,
) -> SafetyCaseState:
    """Pharmacist records a review_status per finding, then the case routes
    to the prescriber if any MAJOR/CRITICAL finding remains actionable, or
    straight to ready-to-dispense otherwise (doc section 3.1 exit condition:
    'All findings assessed').

    Permanent rule: "Every override requires an identified professional and
    documented reason." Dismissing or overriding a MAJOR/CRITICAL finding
    without a non-empty reason raises ValueError — it is not silently
    accepted.
    """
    reasons = reasons or {}
    findings = session.query(Finding).filter_by(case_id=case.id).all()
    findings_by_id = {f.id: f for f in findings}

    for finding_id, new_status in decisions.items():
        finding = findings_by_id.get(finding_id)
        if finding is None:
            continue
        reason = (reasons.get(finding_id) or "").strip()
        if finding.severity in _SEVERE and new_status in _REQUIRES_REASON and not reason:
            raise ValueError(
                f"Finding {finding_id} is {finding.severity.value} severity — "
                f"{new_status.value} requires a documented reason."
            )
        finding.review_status = new_status
        finding.review_reason = reason or None
        finding.reviewed_by_user_id = actor_user_id
        finding.reviewed_at = datetime.now(timezone.utc)
        record_audit_event(
            session, action="finding.reviewed", subject_type="finding",
            subject_id=finding.id, organization_id=case.organization_id,
            actor_user_id=actor_user_id, after={"status": new_status.value, "reason": reason or None},
        )
    session.flush()

    needs_prescriber = any(
        f.severity in _ROUTE_TO_PRESCRIBER and f.review_status != ReviewStatus.DISMISSED
        for f in findings
    )
    next_state = (
        SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE if needs_prescriber
        else SafetyCaseState.READY_TO_DISPENSE
    )
    transition_case(session, case, next_state, actor_user_id=actor_user_id)
    return next_state


def create_intervention(
    session,
    case: SafetyCase,
    created_by_user_id: str,
    target_prescriber_id: str,
    question_or_recommendation: str,
    finding_id: Optional[str] = None,
    urgency: Severity = Severity.CAUTION,
    actor_user_id: Optional[str] = None,
) -> Intervention:
    intervention = Intervention(
        case_id=case.id, finding_id=finding_id,
        created_by_user_id=created_by_user_id, target_prescriber_id=target_prescriber_id,
        urgency=urgency, question_or_recommendation=question_or_recommendation,
    )
    session.add(intervention)
    session.flush()
    record_audit_event(
        session, action="intervention.created", subject_type="intervention",
        subject_id=intervention.id, organization_id=case.organization_id,
        actor_user_id=actor_user_id or created_by_user_id,
    )
    return intervention


def record_prescriber_response(
    session,
    case: SafetyCase,
    intervention: Intervention,
    responder_user_id: str,
    decision: PrescriberDecision,
    rationale: str = "",
    monitoring_plan: str = "",
    actor_user_id: Optional[str] = None,
) -> PrescriberResponse:
    """
    Record a prescriber's decision on an intervention.

    Rule: "Continuing requires a documented rationale and monitoring plan."
    CONTINUE_WITH_RATIONALE with an empty rationale or monitoring_plan
    raises ValueError rather than being silently accepted.
    """
    if decision == PrescriberDecision.CONTINUE_WITH_RATIONALE:
        if not rationale.strip():
            raise ValueError("continue_with_rationale requires a non-empty rationale.")
        if not monitoring_plan.strip():
            raise ValueError("continue_with_rationale requires a non-empty monitoring_plan.")

    response = PrescriberResponse(
        intervention_id=intervention.id, responder_user_id=responder_user_id,
        decision=decision, rationale=rationale, monitoring_plan=monitoring_plan,
    )
    session.add(response)
    session.flush()
    record_audit_event(
        session, action="prescriber_response.recorded", subject_type="intervention",
        subject_id=intervention.id, organization_id=case.organization_id,
        actor_user_id=actor_user_id or responder_user_id, after={"decision": decision.value},
    )

    actor = actor_user_id or responder_user_id
    if decision in (PrescriberDecision.ACCEPT, PrescriberDecision.CONTINUE_WITH_RATIONALE):
        transition_case(session, case, SafetyCaseState.READY_TO_DISPENSE, actor_user_id=actor)
    elif decision == PrescriberDecision.STOP:
        transition_case(session, case, SafetyCaseState.HELD_OR_CANCELLED, actor_user_id=actor)
    elif decision == PrescriberDecision.CHANGE:
        transition_case(session, case, SafetyCaseState.ESCALATED, actor_user_id=actor)
    # REQUEST_MORE_DATA: case stays in AWAITING_PRESCRIBER_RESPONSE.
    return response


def record_escalation(
    session,
    case: SafetyCase,
    recipient_user_id: str,
    reason: str,
    policy: str = "",
    actor_user_id: Optional[str] = None,
) -> Escalation:
    escalation = Escalation(
        case_id=case.id, policy=policy, recipient_user_id=recipient_user_id, reason=reason,
    )
    session.add(escalation)
    session.flush()
    record_audit_event(
        session, action="escalation.created", subject_type="escalation",
        subject_id=escalation.id, organization_id=case.organization_id, actor_user_id=actor_user_id,
    )
    return escalation


def resolve_escalation(
    session,
    case: SafetyCase,
    escalation: Escalation,
    resolution: str,
    next_state: SafetyCaseState,
    actor_user_id: Optional[str] = None,
) -> Escalation:
    escalation.resolution = resolution
    escalation.resolved_at = datetime.now(timezone.utc)
    session.flush()
    record_audit_event(
        session, action="escalation.resolved", subject_type="escalation",
        subject_id=escalation.id, organization_id=case.organization_id, actor_user_id=actor_user_id,
    )
    transition_case(session, case, next_state, actor_user_id=actor_user_id)
    return escalation


def record_dispensing_outcome(
    session,
    case: SafetyCase,
    status: DispensingStatus,
    professional_user_id: str,
    quantity: str = "",
    actor_user_id: Optional[str] = None,
) -> DispensingOutcome:
    outcome = DispensingOutcome(
        case_id=case.id, status=status, quantity=quantity, professional_user_id=professional_user_id,
    )
    session.add(outcome)
    session.flush()
    record_audit_event(
        session, action="dispensing_outcome.recorded", subject_type="safety_case",
        subject_id=case.id, organization_id=case.organization_id,
        actor_user_id=actor_user_id or professional_user_id, after={"status": status.value},
    )
    return outcome


def send_patient_communication(
    session,
    case: SafetyCase,
    approved_explanation: str,
    delivery_channel,
    actor_user_id: Optional[str] = None,
) -> PatientCommunication:
    comm = PatientCommunication(
        case_id=case.id, approved_explanation=approved_explanation, delivery_channel=delivery_channel,
    )
    session.add(comm)
    session.flush()
    record_audit_event(
        session, action="patient_communication.sent", subject_type="safety_case",
        subject_id=case.id, organization_id=case.organization_id, actor_user_id=actor_user_id,
    )
    return comm


def case_timeline(session, case: SafetyCase) -> List[dict]:
    """The complete, immutable, append-only audit trail for one case —
    doc section 14 definition of done: a reviewer can reproduce the full
    history from this alone. Includes events recorded directly against the
    case plus events recorded against its interventions and escalations."""
    from models import AuditEvent

    intervention_ids = [i.id for i in session.query(Intervention).filter_by(case_id=case.id).all()]
    escalation_ids = [e.id for e in session.query(Escalation).filter_by(case_id=case.id).all()]
    finding_ids = [f.id for f in session.query(Finding).filter_by(case_id=case.id).all()]

    query = session.query(AuditEvent).filter(
        (AuditEvent.subject_type == "safety_case") & (AuditEvent.subject_id == case.id)
        | ((AuditEvent.subject_type == "intervention") & (AuditEvent.subject_id.in_(intervention_ids)))
        | ((AuditEvent.subject_type == "escalation") & (AuditEvent.subject_id.in_(escalation_ids)))
        | ((AuditEvent.subject_type == "finding") & (AuditEvent.subject_id.in_(finding_ids)))
    )
    events = query.order_by(AuditEvent.timestamp).all()
    return [
        {
            "action": e.action, "timestamp": e.timestamp,
            "before": e.before_state, "after": e.after_state,
            "actor_user_id": e.actor_user_id,
        }
        for e in events
    ]

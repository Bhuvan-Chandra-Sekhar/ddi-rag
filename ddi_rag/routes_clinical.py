"""
routes_clinical.py — Clinical console API: patients, prescriptions, and the
safety-case detail/action endpoints the pharmacist/prescriber-facing
frontend (static/clinical/index.html) needs beyond what app.py already
exposes (queue, findings/assess, interventions, intervention response).
Also the knowledge-administration workflow (/v1/clinical-rules/*) —
reviewing candidate ClinicalRule rows and promoting them to APPROVED.

Tenant scoping AND role enforcement both go through authz.py's
authorized_case()/require_role() — 404 (not 403) on a cross-tenant case so
existence is never leaked, 403 on a same-tenant caller with the wrong
role. See authz.py's own docstring for why this exists: organization
membership alone used to be the entire check here, which meant a
`patient`-role account could call pharmacist-only actions.

Nothing in this module determines clinical facts. Findings still come only
from services/clinical_rules.py via run_case_analysis(); this module's
/explain route only attaches services/evidence.explain_finding()'s output
to an already-frozen Finding, exactly as evidence.py's own docstring
requires. The rule-review endpoints similarly never invent a severity —
review_rule() only ever promotes/demotes status and optionally confirms
or corrects the severity a source dataset already reported.
"""

from datetime import datetime
from typing import List, Optional

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from authz import authorized_case, get_caller, require_role
from config import GROQ_MODEL
from database import get_session
from enums import (
    DeliveryChannel, DispensingStatus, PrescriptionStatus, RuleStatus,
    SafetyCaseState, Severity, UserRole,
)
from models import (
    ClinicalProfileSnapshot, ClinicalRule, DispensingOutcome, Escalation,
    Finding, Intervention, Medication, Patient, PatientCommunication,
    PrescriberResponse, Prescription, SafetyCase, User,
)
from services.audit import record_audit_event
from services.clinical_rules import ddi_coverage_report, pending_rules, review_rule
from services.evidence import explain_finding
from services.medication_identity import get_or_create_medication
from services.professional_workflow import (
    record_dispensing_outcome, record_escalation, resolve_escalation,
    run_case_analysis, send_patient_communication,
)
from services.rag_pipeline import safe_str
from services.safety_case import (
    CaseClosedError, InvalidTransitionError, create_case, transition_case,
)

clinical_bp = Blueprint("clinical", __name__)

# Role groups — see app.py's identical constants for the same rationale;
# duplicated rather than imported from app.py to avoid a routes_clinical.py
# <-> app.py circular import (app.py registers this blueprint).
CLINICAL_STAFF    = (UserRole.PHARMACIST, UserRole.PRESCRIBER, UserRole.SAFETY_OFFICER)
PHARMACIST_REVIEW = (UserRole.PHARMACIST, UserRole.SAFETY_OFFICER)
RULE_REVIEWERS    = (UserRole.PHARMACIST, UserRole.SAFETY_OFFICER)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _str_list(values) -> List[str]:
    return [safe_str(v).strip().lower() for v in (values or []) if safe_str(v).strip()]


def _finding_dict(f: Finding) -> dict:
    return {
        "id": f.id, "type": f.type.value, "severity": f.severity.value,
        "clinical_effect": f.clinical_effect, "recommended_action": f.recommended_action,
        "evidence_refs": f.evidence_refs, "patient_factors": f.patient_factors,
        "missing_factors": f.missing_factors, "review_status": f.review_status.value,
        "review_reason": f.review_reason, "reviewed_by_user_id": f.reviewed_by_user_id,
        "reviewed_at": _iso(f.reviewed_at), "explanation": f.explanation,
        "explanation_model_version": f.explanation_model_version,
        "explanation_prompt_version": f.explanation_prompt_version,
    }


def _case_detail(session, case: SafetyCase) -> dict:
    prescription = session.get(Prescription, case.prescription_id)
    medication = session.get(Medication, prescription.medication_id) if prescription else None
    patient = session.get(Patient, prescription.patient_id) if prescription else None
    snapshot = session.get(ClinicalProfileSnapshot, case.profile_snapshot_id)

    findings = session.query(Finding).filter_by(case_id=case.id).order_by(Finding.created_at).all()
    interventions = session.query(Intervention).filter_by(case_id=case.id).order_by(Intervention.created_at).all()
    escalations = session.query(Escalation).filter_by(case_id=case.id).order_by(Escalation.created_at).all()
    dispensing_outcome = (
        session.query(DispensingOutcome).filter_by(case_id=case.id)
        .order_by(DispensingOutcome.occurred_at.desc()).first()
    )
    communications = (
        session.query(PatientCommunication).filter_by(case_id=case.id)
        .order_by(PatientCommunication.created_at.desc()).all()
    )

    intervention_list = []
    for iv in interventions:
        resp = (
            session.query(PrescriberResponse).filter_by(intervention_id=iv.id)
            .order_by(PrescriberResponse.created_at.desc()).first()
        )
        intervention_list.append({
            "id": iv.id, "finding_id": iv.finding_id, "created_by_user_id": iv.created_by_user_id,
            "target_prescriber_id": iv.target_prescriber_id, "urgency": iv.urgency.value,
            "question_or_recommendation": iv.question_or_recommendation, "created_at": _iso(iv.created_at),
            "response": ({
                "decision": resp.decision.value, "rationale": resp.rationale,
                "monitoring_plan": resp.monitoring_plan, "responder_user_id": resp.responder_user_id,
                "created_at": _iso(resp.created_at),
            } if resp else None),
        })

    # What the knowledge base actually knows about this case's own
    # medication list, independent of the findings list above — see
    # ddi_coverage_report()'s own docstring for why "no findings" alone
    # can't distinguish "checked, nothing concerning" from "checked, no
    # matching rule exists". Uses the same ingredient list
    # create_safety_case() built the findings from (snapshot's prior
    # medications + this case's own prescribed drug).
    ddi_coverage = (
        ddi_coverage_report(session, list(snapshot.medications or []) + [medication.display_name])
        if snapshot and medication else
        {"pairs_checked": 0, "pairs_with_rule": 0, "pairs_with_no_rule": 0,
         "pairs_approved": 0, "pairs_unreviewed": 0, "pairs_rejected": 0, "unmatched_pairs": []}
    )

    return {
        "id": case.id, "state": case.state.value,
        "created_at": _iso(case.created_at), "closed_at": _iso(case.closed_at),
        "patient": ({"id": patient.id, "name": f"{patient.first_name} {patient.last_name}"} if patient else None),
        "clinical_profile": ({
            "medications": snapshot.medications or [], "allergies": snapshot.allergies or [],
            "conditions": snapshot.conditions or [], "labs": snapshot.labs or [],
        } if snapshot else None),
        "ddi_coverage": ddi_coverage,
        "prescription": ({
            "id": prescription.id, "dose": prescription.dose, "route": prescription.route,
            "frequency": prescription.frequency, "status": prescription.status.value,
        } if prescription else None),
        "medication": ({
            "id": medication.id, "display_name": medication.display_name, "rxcui": medication.rxcui,
            "ingredients": medication.ingredients, "identity_confirmed": medication.identity_confirmed,
            "resolution_method": medication.resolution_method,
        } if medication else None),
        "findings": [_finding_dict(f) for f in findings],
        "interventions": intervention_list,
        "escalations": [
            {"id": e.id, "policy": e.policy, "recipient_user_id": e.recipient_user_id, "reason": e.reason,
             "resolution": e.resolution, "created_at": _iso(e.created_at), "resolved_at": _iso(e.resolved_at)}
            for e in escalations
        ],
        "dispensing_outcome": ({
            "status": dispensing_outcome.status.value, "quantity": dispensing_outcome.quantity,
            "professional_user_id": dispensing_outcome.professional_user_id,
            "occurred_at": _iso(dispensing_outcome.occurred_at),
        } if dispensing_outcome else None),
        "communications": [
            {"id": c.id, "approved_explanation": c.approved_explanation, "delivery_channel": c.delivery_channel.value,
             "delivered_at": _iso(c.delivered_at), "created_at": _iso(c.created_at)}
            for c in communications
        ],
    }


# ── Staff directory ──────────────────────────────────────────────────────────

@clinical_bp.route("/v1/staff", methods=["GET"])
@jwt_required()
def list_staff():
    with get_session() as session:
        caller, error = get_caller(session, get_jwt_identity())
        if error:
            return error
        role_error = require_role(caller, CLINICAL_STAFF)
        if role_error:
            return role_error
        staff = (
            session.query(User)
            .filter(
                User.organization_id == caller.organization_id,
                User.role.in_([UserRole.PHARMACIST, UserRole.PRESCRIBER, UserRole.SAFETY_OFFICER]),
            )
            .order_by(User.full_name).all()
        )
        return {"staff": [
            {"id": u.id, "full_name": u.full_name or u.email, "role": u.role.value} for u in staff
        ]}, 200


# ── Patients ──────────────────────────────────────────────────────────────────

@clinical_bp.route("/v1/patients", methods=["GET"])
@jwt_required()
def list_patients():
    with get_session() as session:
        caller, error = get_caller(session, get_jwt_identity())
        if error:
            return error
        role_error = require_role(caller, CLINICAL_STAFF)
        if role_error:
            return role_error
        patients = (
            session.query(Patient).filter_by(organization_id=caller.organization_id)
            .order_by(Patient.created_at.desc()).all()
        )
        result = []
        for p in patients:
            snap = (
                session.query(ClinicalProfileSnapshot).filter_by(patient_id=p.id)
                .order_by(ClinicalProfileSnapshot.captured_at.desc()).first()
            )
            result.append({
                "id": p.id, "name": f"{p.first_name} {p.last_name}",
                "medications": snap.medications if snap else [],
                "allergies": snap.allergies if snap else [],
            })
        return {"patients": result}, 200


@clinical_bp.route("/v1/patients", methods=["POST"])
@jwt_required()
def create_patient():
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    first_name = safe_str(payload.get("first_name", "")).strip()
    last_name = safe_str(payload.get("last_name", "")).strip()
    if not first_name or not last_name:
        return {"error": "first_name and last_name are required"}, 400

    with get_session() as session:
        caller, error = get_caller(session, actor_id)
        if error:
            return error
        role_error = require_role(caller, CLINICAL_STAFF)
        if role_error:
            return role_error

        patient = Patient(
            organization_id=caller.organization_id, first_name=first_name, last_name=last_name,
            sex=safe_str(payload.get("sex", "")).strip() or None,
        )
        session.add(patient)
        session.flush()

        snapshot = ClinicalProfileSnapshot(
            patient_id=patient.id,
            medications=_str_list(payload.get("medications")),
            allergies=_str_list(payload.get("allergies")),
            conditions=_str_list(payload.get("conditions")),
            labs=payload.get("labs") or [],
        )
        session.add(snapshot)
        session.flush()

        record_audit_event(
            session, action="patient.created", subject_type="patient", subject_id=patient.id,
            organization_id=caller.organization_id, actor_user_id=actor_id,
            after={"first_name": first_name, "last_name": last_name},
        )
        return {"patient_id": patient.id, "snapshot_id": snapshot.id}, 201


# ── Prescriptions ─────────────────────────────────────────────────────────────

@clinical_bp.route("/v1/prescriptions", methods=["POST"])
@jwt_required()
def create_prescription():
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    patient_id = safe_str(payload.get("patient_id", ""))
    medication_name = safe_str(payload.get("medication_name", "")).strip()
    if not patient_id or not medication_name:
        return {"error": "patient_id and medication_name are required"}, 400

    with get_session() as session:
        caller, error = get_caller(session, actor_id)
        if error:
            return error
        role_error = require_role(caller, CLINICAL_STAFF)
        if role_error:
            return role_error
        patient = session.get(Patient, patient_id)
        if not patient or patient.organization_id != caller.organization_id:
            return {"error": "not found"}, 404

        prescriber_id = safe_str(payload.get("prescriber_id", "")) or (
            actor_id if caller.role == UserRole.PRESCRIBER else ""
        )
        if not prescriber_id:
            return {"error": "prescriber_id is required unless the caller is a prescriber"}, 400
        prescriber = session.get(User, prescriber_id)
        if not prescriber or prescriber.organization_id != caller.organization_id:
            return {"error": "unknown prescriber_id"}, 400

        medication = get_or_create_medication(session, medication_name)

        prescription = Prescription(
            organization_id=caller.organization_id, patient_id=patient.id, prescriber_id=prescriber_id,
            medication_id=medication.id,
            dose=safe_str(payload.get("dose", "")).strip() or None,
            route=safe_str(payload.get("route", "")).strip() or None,
            frequency=safe_str(payload.get("frequency", "")).strip() or None,
            status=PrescriptionStatus.ACTIVE,
        )
        session.add(prescription)
        session.flush()

        record_audit_event(
            session, action="prescription.created", subject_type="prescription", subject_id=prescription.id,
            organization_id=caller.organization_id, actor_user_id=actor_id,
            after={"medication": medication.display_name},
        )
        return {
            "prescription_id": prescription.id,
            "medication": {
                "id": medication.id, "display_name": medication.display_name, "rxcui": medication.rxcui,
                "ingredients": medication.ingredients, "identity_confirmed": medication.identity_confirmed,
                "resolution_method": medication.resolution_method,
            },
        }, 201


# ── Safety cases: create + full detail ───────────────────────────────────────

@clinical_bp.route("/v1/safety-cases", methods=["POST"])
@jwt_required()
def create_safety_case():
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    prescription_id = safe_str(payload.get("prescription_id", ""))
    if not prescription_id:
        return {"error": "prescription_id is required"}, 400

    with get_session() as session:
        caller, error = get_caller(session, actor_id)
        if error:
            return error
        role_error = require_role(caller, CLINICAL_STAFF)
        if role_error:
            return role_error
        prescription = session.get(Prescription, prescription_id)
        if not prescription or prescription.organization_id != caller.organization_id:
            return {"error": "not found"}, 404
        medication = session.get(Medication, prescription.medication_id)
        snapshot = (
            session.query(ClinicalProfileSnapshot).filter_by(patient_id=prescription.patient_id)
            .order_by(ClinicalProfileSnapshot.captured_at.desc()).first()
        )
        if not snapshot:
            return {"error": "patient has no clinical profile snapshot yet"}, 400

        case = create_case(session, caller.organization_id, prescription, snapshot, actor_user_id=actor_id)

        ingredient_names = list(snapshot.medications or []) + [medication.display_name]
        run_case_analysis(
            session, case, ingredient_names=ingredient_names,
            allergy_names=snapshot.allergies or [], actor_user_id=actor_id,
        )
        return _case_detail(session, case), 201


@clinical_bp.route("/v1/safety-cases/<case_id>", methods=["GET"])
@jwt_required()
def get_safety_case(case_id):
    with get_session() as session:
        case, error = authorized_case(session, case_id, get_jwt_identity(), CLINICAL_STAFF)
        if error:
            return error
        return _case_detail(session, case), 200


@clinical_bp.route("/v1/safety-cases/<case_id>/dispense", methods=["POST"])
@jwt_required()
def dispense_safety_case(case_id):
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    try:
        status = DispensingStatus(payload.get("status", ""))
    except ValueError:
        return {"error": "invalid status"}, 400

    with get_session() as session:
        case, error = authorized_case(session, case_id, actor_id, PHARMACIST_REVIEW)
        if error:
            return error
        record_dispensing_outcome(
            session, case, status=status, professional_user_id=actor_id,
            quantity=safe_str(payload.get("quantity", "")), actor_user_id=actor_id,
        )
        return _case_detail(session, case), 200


@clinical_bp.route("/v1/safety-cases/<case_id>/communicate", methods=["POST"])
@jwt_required()
def communicate_safety_case(case_id):
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    explanation = safe_str(payload.get("approved_explanation", "")).strip()
    if not explanation:
        return {"error": "approved_explanation is required"}, 400
    try:
        channel = DeliveryChannel(payload.get("delivery_channel", "portal"))
    except ValueError:
        return {"error": "invalid delivery_channel"}, 400

    with get_session() as session:
        case, error = authorized_case(session, case_id, actor_id, PHARMACIST_REVIEW)
        if error:
            return error
        send_patient_communication(
            session, case, approved_explanation=explanation, delivery_channel=channel, actor_user_id=actor_id,
        )
        return _case_detail(session, case), 200


@clinical_bp.route("/v1/safety-cases/<case_id>/close", methods=["POST"])
@jwt_required()
def close_safety_case(case_id):
    actor_id = get_jwt_identity()
    with get_session() as session:
        case, error = authorized_case(session, case_id, actor_id, PHARMACIST_REVIEW)
        if error:
            return error
        try:
            transition_case(session, case, SafetyCaseState.CLOSED, actor_user_id=actor_id)
        except (InvalidTransitionError, CaseClosedError) as exc:
            return {"error": safe_str(exc)}, 400
        return _case_detail(session, case), 200


@clinical_bp.route("/v1/safety-cases/<case_id>/resolve-escalation", methods=["POST"])
@jwt_required()
def resolve_safety_case_escalation(case_id):
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    reason = safe_str(payload.get("reason", "")).strip()
    resolution = safe_str(payload.get("resolution", "")).strip()
    if not reason or not resolution:
        return {"error": "reason and resolution are required"}, 400
    try:
        next_state = SafetyCaseState(payload.get("next_state", ""))
    except ValueError:
        return {"error": "invalid next_state"}, 400
    if next_state not in (SafetyCaseState.READY_TO_DISPENSE, SafetyCaseState.HELD_OR_CANCELLED):
        return {"error": "next_state must be ready_to_dispense or held_or_cancelled"}, 400

    with get_session() as session:
        case, error = authorized_case(session, case_id, actor_id, PHARMACIST_REVIEW)
        if error:
            return error
        escalation = record_escalation(
            session, case, recipient_user_id=actor_id, reason=reason,
            policy=safe_str(payload.get("policy", "")), actor_user_id=actor_id,
        )
        try:
            resolve_escalation(
                session, case, escalation, resolution=resolution, next_state=next_state, actor_user_id=actor_id,
            )
        except (InvalidTransitionError, CaseClosedError) as exc:
            return {"error": safe_str(exc)}, 400
        return _case_detail(session, case), 200


# ── Findings: on-demand grounded explanation (Phase 4 service, exposed here) ──

@clinical_bp.route("/v1/findings/<finding_id>/explain", methods=["POST"])
@jwt_required()
def explain_case_finding(finding_id):
    actor_id = get_jwt_identity()
    with get_session() as session:
        caller, error = get_caller(session, actor_id)
        if error:
            return error
        role_error = require_role(caller, CLINICAL_STAFF)
        if role_error:
            return role_error
        finding = session.get(Finding, finding_id)
        if not finding:
            return {"error": "not found"}, 404
        case = session.get(SafetyCase, finding.case_id)
        if not case or case.organization_id != caller.organization_id:
            return {"error": "not found"}, 404

        prescription = session.get(Prescription, case.prescription_id)
        medication = session.get(Medication, prescription.medication_id) if prescription else None

        result = explain_finding(
            finding_type=finding.type.value, severity=finding.severity.value,
            clinical_effect=finding.clinical_effect or "", recommended_action=finding.recommended_action or "",
            drug_name=(medication.display_name if medication else None), model_name=GROQ_MODEL,
        )
        finding.explanation = result["explanation"]
        finding.explanation_model_version = result["model_version"]
        finding.explanation_prompt_version = result["prompt_version"]
        finding.evidence_hash = result["evidence_hash"]
        session.flush()

        record_audit_event(
            session, action="finding.explained", subject_type="finding", subject_id=finding.id,
            organization_id=case.organization_id, actor_user_id=actor_id,
        )
        return {
            "finding_id": finding.id, "explanation": result["explanation"],
            "citations": result["citations"], "evidence_hash": result["evidence_hash"],
        }, 200


# ── Knowledge administration: rule review (services/clinical_rules.review_rule) ──
# Previously absent entirely: RuleStatus.APPROVED was set only in test
# fixtures anywhere in this repo. These two routes are the first real path
# from an imported DRAFT candidate to a clinically-authoritative rule.

def _rule_dict(r: ClinicalRule) -> dict:
    return {
        "id": r.id, "pair_key": r.pair_key,
        "ingredient_a": r.ingredient_a, "ingredient_b": r.ingredient_b,
        "clinical_effect": r.clinical_effect, "severity": r.severity.value,
        "status": r.status.value, "source_dataset": r.source_dataset,
        "rule_version": r.rule_version,
        "reviewer_user_id": r.reviewer_user_id, "reviewed_at": _iso(r.reviewed_at),
        "created_at": _iso(r.created_at),
    }


@clinical_bp.route("/v1/clinical-rules/pending", methods=["GET"])
@jwt_required()
def list_pending_rules():
    actor_id = get_jwt_identity()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = max(int(request.args.get("offset", 0)), 0)
    with get_session() as session:
        caller, error = get_caller(session, actor_id)
        if error:
            return error
        role_error = require_role(caller, RULE_REVIEWERS)
        if role_error:
            return role_error
        rules = pending_rules(session, limit=limit, offset=offset)
        return {"rules": [_rule_dict(r) for r in rules]}, 200


@clinical_bp.route("/v1/clinical-rules/<rule_id>/review", methods=["POST"])
@jwt_required()
def review_clinical_rule(rule_id):
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    try:
        decision = RuleStatus(payload.get("decision", ""))
    except ValueError:
        return {"error": "decision must be 'approved' or 'rejected'"}, 400
    if decision not in (RuleStatus.APPROVED, RuleStatus.REJECTED):
        return {"error": "decision must be 'approved' or 'rejected'"}, 400

    severity_override = None
    raw_severity = payload.get("severity")
    if raw_severity:
        try:
            severity_override = Severity(raw_severity)
        except ValueError:
            return {"error": f"invalid severity: {safe_str(raw_severity)}"}, 400

    with get_session() as session:
        caller, error = get_caller(session, actor_id)
        if error:
            return error
        role_error = require_role(caller, RULE_REVIEWERS)
        if role_error:
            return role_error

        existing = session.get(ClinicalRule, rule_id)
        if not existing:
            return {"error": "not found"}, 404
        before = {"status": existing.status.value, "severity": existing.severity.value}

        try:
            rule = review_rule(
                session, rule_id, decision, reviewer_user_id=actor_id,
                severity_override=severity_override,
            )
        except ValueError as exc:
            return {"error": safe_str(exc)}, 400

        record_audit_event(
            session, action=f"rule.{decision.value}", subject_type="clinical_rule", subject_id=rule.id,
            actor_user_id=actor_id, before=before,
            after={"status": rule.status.value, "severity": rule.severity.value},
        )
        return _rule_dict(rule), 200

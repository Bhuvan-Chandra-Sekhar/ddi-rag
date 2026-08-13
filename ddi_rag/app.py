"""
app.py — Flask REST API for the DDI-RAG system.

Endpoints:
    GET  /api/health          — liveness check
    POST /api/auth/register   — create account
    POST /api/auth/login      — authenticate, receive JWT
    POST /api/query           — { prescription: str, top_k?: int }
                                 -> { detected_drugs: list, results: list }
                                 (JWT optional — works for anonymous callers too)

This API intentionally does not expose a pharmacy-finder or general-chatbot
endpoint — this app answers drug-interaction queries only. (Pharmacy lookup
still exists as an MCP tool in mcp_server.py for Claude Desktop, which is a
separate interface.)

Environment:
    Requires init_db() to be called before serving requests. Embeddings are
    a Cohere API call (services/evidence_store.py) — nothing to preload.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Allow imports from the ddi_rag package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.exceptions import HTTPException

from auth import authenticate_user, configure_jwt, register_user
from config import DEFAULT_TOP_K, MAX_PRESCRIPTION_LEN, MAX_TOP_K, PORT
from database import get_session, init_db
from enums import PrescriberDecision, ReviewStatus, Severity
from models import (
    Intervention, Medication, Patient, PatientCommunication, Prescription,
    SafetyCase, User,
)
from services.rag_pipeline import answer_ddi, safe_str
from services.professional_workflow import (
    assess_findings_and_route, case_timeline, create_intervention,
    pharmacist_queue, record_prescriber_response,
)

log = logging.getLogger("ddi.app")

flask_app = Flask("ddi")
CORS(flask_app)
configure_jwt(flask_app)

# ── Lookup tables (populated by init_lookups) ─────────────────────────────────
_BRAND_TO_GENERIC:  Dict[str, str]        = {}
_SORTED_NAMES:      List[str]             = []
_COMPILED_PATTERNS: Dict[str, re.Pattern] = {}


def init_lookups(chunk_df) -> None:
    """
    Build brand→generic mapping and pre-compile regex patterns
    from the chunk DataFrame. Call once at startup before serving requests.
    """
    global _BRAND_TO_GENERIC, _SORTED_NAMES, _COMPILED_PATTERNS

    b2g: Dict[str, str] = {}
    for _, row in chunk_df[["brand_name", "generic_name"]].drop_duplicates().iterrows():
        b = str(row["brand_name"]).strip().lower()
        g = str(row["generic_name"]).strip().lower()
        if b and b != "nan":
            b2g[b] = g

    _BRAND_TO_GENERIC  = b2g
    generics           = set(chunk_df["generic_name"].str.lower().str.strip().dropna().unique())
    all_names          = generics | set(b2g.keys())
    _SORTED_NAMES      = sorted(all_names, key=len, reverse=True)
    _COMPILED_PATTERNS = {
        n: re.compile(r"\b" + re.escape(n) + r"\b") for n in _SORTED_NAMES
    }
    log.info("Lookup tables built: %d names indexed.", len(_SORTED_NAMES))


def parse_prescription(text: str) -> List[str]:
    """
    Longest-match regex extraction of recognised drug names from prescription text.
    Brand names are resolved to their generic equivalent.
    """
    text_lower = text.lower()
    found:    List[str]             = []
    consumed: List[Tuple[int, int]] = []

    for name in _SORTED_NAMES:
        for m in _COMPILED_PATTERNS[name].finditer(text_lower):
            s, e = m.start(), m.end()
            if not any(cs <= s < ce or cs < e <= ce for cs, ce in consumed):
                generic = _BRAND_TO_GENERIC.get(name, name)
                if generic not in found:
                    found.append(generic)
                consumed.append((s, e))
    return found


# ── Flask error handler ───────────────────────────────────────────────────────
@flask_app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return {"error": e.description}, e.code
    log.exception("Unhandled exception")
    return {"error": safe_str(e)}, 500


# ── Routes ────────────────────────────────────────────────────────────────────
@flask_app.route("/api/health")
def health():
    return {"status": "ok"}, 200


@flask_app.route("/patient")
def patient_app():
    """Serves the patient-facing single-page app (static HTML, no build step)."""
    return send_from_directory(Path(__file__).resolve().parent / "static" / "patient", "index.html")


@flask_app.route("/v1/organizations", methods=["GET"])
def list_organizations():
    """Public directory of organization names only (no other fields) — lets
    a signup form offer a "choose your hospital" picker instead of requiring
    a raw organization_id UUID from a new patient."""
    from models import Organization
    with get_session() as session:
        orgs = session.query(Organization).order_by(Organization.name).all()
        return {"organizations": [{"id": o.id, "name": o.name} for o in orgs]}, 200


@flask_app.route("/api/auth/register", methods=["POST"])
def register():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        user = register_user(
            email           = safe_str(payload.get("email", "")),
            password        = str(payload.get("password", "")),
            organization_id = safe_str(payload.get("organization_id", "")),
            full_name       = safe_str(payload.get("full_name", "")),
            first_name      = safe_str(payload.get("first_name", "")),
            last_name       = safe_str(payload.get("last_name", "")),
        )
        return {"user": user}, 201
    except ValueError as exc:
        return {"error": str(exc)}, 400


@flask_app.route("/api/auth/login", methods=["POST"])
def login():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        result = authenticate_user(
            email    = safe_str(payload.get("email", "")),
            password = str(payload.get("password", "")),
        )
        return result, 200
    except ValueError as exc:
        return {"error": str(exc)}, 401


@flask_app.route("/api/query", methods=["POST"])
@jwt_required(optional=True)
def query_api():
    payload      = request.get_json(force=True, silent=True) or {}
    prescription = safe_str(payload.get("prescription", "")).strip()
    top_k        = min(int(payload.get("top_k", DEFAULT_TOP_K)), MAX_TOP_K)

    if not prescription:
        return {"error": "prescription field is required"}, 400
    if len(prescription) > MAX_PRESCRIPTION_LEN:
        return {"error": f"prescription must be <= {MAX_PRESCRIPTION_LEN} chars"}, 400

    try:
        detected = parse_prescription(prescription)
    except Exception:
        log.exception("parse_prescription failed")
        detected = []

    results = []
    for drug in (detected if detected else [None]):
        try:
            res = answer_ddi(drug_name=drug, top_k=top_k)
            results.append({
                "drug"   : safe_str(drug or prescription),
                "answer" : res["answer"],
                "sources": res["sources"],
            })
        except Exception as exc:
            log.exception("Processing failed for drug=%s", drug)
            results.append({
                "drug"   : safe_str(drug or prescription),
                "answer" : f"Processing error: {safe_str(exc)}",
                "sources": [],
            })

    return {"detected_drugs": detected, "results": results}, 200


# ── Professional workflow (section 7: /v1/safety-cases, /v1/interventions) ──
# Tenant scoping: every route resolves the case's organization_id and
# rejects with 403 if it doesn't match the caller's own organization_id.
# Role-gated actions (e.g. only pharmacists may assess findings) are Phase 6
# RBAC work and not implemented here — this only enforces tenant boundaries.

def _authorized_case_or_error(session, case_id: str, caller_user_id: str):
    """Return (case, None) if case_id exists and belongs to the caller's
    organization, else (None, (body, status)) for the caller to return."""
    user = session.get(User, caller_user_id)
    if not user:
        return None, ({"error": "unknown user"}, 401)
    case = session.get(SafetyCase, case_id)
    if not case:
        return None, ({"error": "not found"}, 404)
    if case.organization_id != user.organization_id:
        return None, ({"error": "not found"}, 404)  # 404, not 403 — don't leak existence across tenants
    return case, None


@flask_app.route("/v1/safety-cases/queue", methods=["GET"])
@jwt_required()
def safety_case_queue():
    with get_session() as session:
        user = session.get(User, get_jwt_identity())
        if not user:
            return {"error": "unknown user"}, 401
        cases = pharmacist_queue(session, user.organization_id)
        return {"cases": [{"id": c.id, "state": c.state.value} for c in cases]}, 200


@flask_app.route("/v1/safety-cases/<case_id>/timeline", methods=["GET"])
@jwt_required()
def safety_case_timeline(case_id):
    with get_session() as session:
        case, error = _authorized_case_or_error(session, case_id, get_jwt_identity())
        if error:
            return error
        timeline = case_timeline(session, case)
        return {"timeline": [
            {**e, "timestamp": e["timestamp"].isoformat() if e["timestamp"] else None}
            for e in timeline
        ]}, 200


@flask_app.route("/v1/safety-cases/<case_id>/findings/assess", methods=["POST"])
@jwt_required()
def assess_case_findings(case_id):
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    try:
        decisions = {
            safe_str(fid): ReviewStatus(status)
            for fid, status in (payload.get("decisions") or {}).items()
        }
    except ValueError as exc:
        return {"error": f"invalid review_status: {safe_str(exc)}"}, 400
    reasons = {safe_str(fid): safe_str(reason) for fid, reason in (payload.get("reasons") or {}).items()}

    with get_session() as session:
        case, error = _authorized_case_or_error(session, case_id, actor_id)
        if error:
            return error
        try:
            next_state = assess_findings_and_route(
                session, case, decisions, actor_user_id=actor_id, reasons=reasons,
            )
        except ValueError as exc:
            return {"error": safe_str(exc)}, 400
        return {"case_id": case.id, "state": next_state.value}, 200


@flask_app.route("/v1/interventions", methods=["POST"])
@jwt_required()
def create_intervention_route():
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    try:
        urgency = Severity(payload.get("urgency", "caution"))
    except ValueError:
        return {"error": "invalid urgency"}, 400

    with get_session() as session:
        case, error = _authorized_case_or_error(session, safe_str(payload.get("case_id", "")), actor_id)
        if error:
            return error
        intervention = create_intervention(
            session, case,
            created_by_user_id=actor_id,
            target_prescriber_id=safe_str(payload.get("target_prescriber_id", "")),
            question_or_recommendation=safe_str(payload.get("question_or_recommendation", "")),
            finding_id=payload.get("finding_id"),
            urgency=urgency,
        )
        return {"intervention_id": intervention.id}, 201


@flask_app.route("/v1/interventions/<intervention_id>/response", methods=["POST"])
@jwt_required()
def respond_to_intervention(intervention_id):
    payload = request.get_json(force=True, silent=True) or {}
    actor_id = get_jwt_identity()
    try:
        decision = PrescriberDecision(payload.get("decision", ""))
    except ValueError:
        return {"error": "invalid decision"}, 400

    with get_session() as session:
        intervention = session.get(Intervention, intervention_id)
        if not intervention:
            return {"error": "not found"}, 404
        case, error = _authorized_case_or_error(session, intervention.case_id, actor_id)
        if error:
            return error
        try:
            record_prescriber_response(
                session, case, intervention,
                responder_user_id=actor_id, decision=decision,
                rationale=safe_str(payload.get("rationale", "")),
                monitoring_plan=safe_str(payload.get("monitoring_plan", "")),
            )
        except ValueError as exc:
            return {"error": safe_str(exc)}, 400
        return {"case_id": case.id, "state": case.state.value}, 200


@flask_app.route("/v1/my/cases", methods=["GET"])
@jwt_required()
def my_cases():
    """
    A patient's own safety cases, scoped strictly to the Patient record
    linked to the calling account — never another patient's data. Returns
    only case state, the medication involved, and any approved patient
    communication text — never raw Finding severity/evidence, which is
    professional-facing.
    """
    with get_session() as session:
        patient = session.query(Patient).filter_by(user_id=get_jwt_identity()).first()
        if not patient:
            return {"error": "no patient record linked to this account"}, 404

        rows = (
            session.query(SafetyCase, Prescription, Medication)
            .join(Prescription, SafetyCase.prescription_id == Prescription.id)
            .join(Medication, Prescription.medication_id == Medication.id)
            .filter(Prescription.patient_id == patient.id)
            .order_by(SafetyCase.created_at.desc())
            .all()
        )

        cases = []
        for case, prescription, medication in rows:
            comms = (
                session.query(PatientCommunication)
                .filter_by(case_id=case.id)
                .order_by(PatientCommunication.created_at.desc())
                .all()
            )
            cases.append({
                "case_id": case.id,
                "state": case.state.value,
                "medication": medication.display_name,
                "created_at": case.created_at.isoformat() if case.created_at else None,
                "communications": [
                    {
                        "explanation": c.approved_explanation,
                        "delivered_at": c.delivered_at.isoformat() if c.delivered_at else None,
                    }
                    for c in comms
                ],
            })
        return {"cases": cases}, 200


if __name__ == "__main__":
    init_db()
    flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False, debug=False)

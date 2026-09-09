"""
routes_public.py — Unauthenticated "guest self-check" endpoints.

Lets a patient run the real deterministic rule engine (services/clinical_rules)
against a medication list they type in themselves, with no account and no
login — and therefore no persistence: nothing here writes a Patient,
Prescription, or SafetyCase row. Every call is stateless; a patient with
real prior history has to type it in again each time, same as this session
(there is no server-side memory to draw on without an account).

This is deliberately a *different*, lower-trust pathway than
/v1/safety-cases (routes_clinical.py): no pharmacist ever reviews these
results, so every response must stay honest about that — "not yet
clinically reviewed" is never allowed to read as "safe". Same governance
rule as everywhere else in this codebase: the LLM (services/evidence.explain_finding)
only explains a finding the rule engine already froze; it never determines
severity or action, here or anywhere else.

Cost/abuse note: MAX_SELF_CHECK_ITEMS/MAX_ITEM_LEN/MAX_NOTES_LEN (config.py)
bound the worst case of a single unauthenticated request (RxNorm lookups
are network calls; each /api/explain call is one Cohere + one Groq call).
Per-IP rate limiting (rate_limit.py's shared limiter) is applied below —
tighter than the app-wide default on /api/explain specifically, since that
one call is the expensive path (Cohere + Groq every time, vs. self_check's
DB-only lookups).
"""

import logging
from typing import List, Sequence, Tuple

from flask import Blueprint, request

from config import GROQ_MODEL, MAX_ITEM_LEN, MAX_NOTES_LEN, MAX_SELF_CHECK_ITEMS
from database import get_session
from enums import Severity
from rate_limit import limiter
from services.clinical_rules import ddi_coverage_report, evaluate_case
from services.evidence import explain_finding
from services.medication_identity import resolve_medication_identity
from services.rag_pipeline import safe_str

log = logging.getLogger("ddi.routes_public")

public_bp = Blueprint("public", __name__)

_SEVERITY_RANK = {
    Severity.CRITICAL: 4, Severity.MAJOR: 3, Severity.UNKNOWN: 2,
    Severity.CAUTION: 1, Severity.INFORMATIONAL: 0,
}


def _clean_str_list(raw, max_items: int, max_len: int) -> List[str]:
    """Best-effort coercion of a JSON value into a bounded list of trimmed,
    non-empty strings — never raises on malformed input, just drops it."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        s = safe_str(item).strip()[:max_len]
        if s:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _resolve_and_evaluate(
    session, medication_names: Sequence[str], allergy_names: Sequence[str],
) -> Tuple[List[dict], List[dict], List[str]]:
    """
    Resolve each typed medication name to its RxNorm ingredient(s) (falling
    back to the raw name if RxNorm can't identify it — an unresolved name
    still participates in duplicate/allergy checks, it just can't be
    trusted as "confirmed" identity), then run every deterministic rule
    class against the combined ingredient list.

    Deterministic given the same inputs — the guest checker has no session
    to persist a finding's identity in, so /api/explain re-derives this
    same list and reads it by index rather than trusting a client-supplied
    finding_id.

    Returns (resolved, findings_raw, ingredient_names) — the third element
    lets self_check() also run ddi_coverage_report() against the exact
    same ingredient list evaluate_case() used, without re-resolving names.
    """
    resolved = []
    ingredient_names: List[str] = []
    for name in medication_names:
        identity = resolve_medication_identity(name)
        ingredients = identity["ingredients"] or [name.strip().lower()]
        resolved.append({
            "input": name,
            "ingredients": ingredients,
            "identity_confirmed": identity["identity_confirmed"],
            "resolution_method": identity["resolution_method"],
        })
        ingredient_names.extend(ingredients)

    findings_raw = evaluate_case(session, ingredient_names, allergy_names)
    return resolved, findings_raw, ingredient_names


_STRONG_SEVERITIES = {"critical", "major"}


def _patient_guidance(f: dict) -> str:
    """
    Plain, patient-facing next-step text — deliberately separate from
    recommended_action (services/clinical_rules.py), which is written for a
    pharmacist's operational workflow ("do not dispense without prescriber
    confirmation" means nothing to someone checking their own medicine
    cabinet, and was previously shown to guests verbatim). This function
    never changes what happened — type/severity/review_status are already
    frozen by the rule engine — it only rewords the same facts for a
    different audience, same boundary evidence.explain_finding's
    audience="patient" mode draws for its LLM prompt.
    """
    ftype = f["type"].value
    severity = f["severity"].value
    reported = (f.get("patient_factors") or {}).get("reported_severity")

    if ftype == "allergy":
        return "This matches an allergy you told us about. Don't take this — contact your doctor or pharmacist first."
    if ftype == "duplicate":
        return "The same ingredient shows up more than once in what you listed. Check with your pharmacist that this is intentional."
    if ftype == "ddi":
        if severity in _STRONG_SEVERITIES:
            return "This combination needs urgent attention — please talk to your doctor or pharmacist before taking these together."
        if severity == "caution":
            return "Worth mentioning to your doctor or pharmacist soon — not necessarily urgent."
        return "For your awareness — no action needed based on what we found."
    if ftype == "unknown":
        if reported in _STRONG_SEVERITIES:
            return "No pharmacist has confirmed this yet, but our data suggests it could be a serious interaction. Please check with your doctor or pharmacist before taking these together."
        return "This hasn't been reviewed by a pharmacist yet. To be safe, mention it to your doctor or pharmacist before combining these."
    return "Check with your doctor or pharmacist if you have questions about this."


def _needs_doctor_visit(f: dict) -> bool:
    """True when either the confirmed severity or the source data's
    unreviewed severity rating is critical/major — drives the frontend's
    unmissable "see a doctor" callout rather than making it parse severity
    strings itself."""
    severity = f["severity"].value
    reported = (f.get("patient_factors") or {}).get("reported_severity")
    return severity in _STRONG_SEVERITIES or reported in _STRONG_SEVERITIES


def _serialize_finding(f: dict, index: int) -> dict:
    factors = f.get("patient_factors") or {}
    return {
        "index": index,
        "type": f["type"].value,
        "severity": f["severity"].value,
        # Only meaningful for type="unknown" DDI findings (an unapproved
        # rule) — the source dataset's own severity rating, e.g. DDInter's
        # "major", surfaced separately so it's never confused with a
        # pharmacist-confirmed severity. None when not applicable.
        "reported_severity": factors.get("reported_severity"),
        "clinical_effect": f["clinical_effect"],
        "recommended_action": f["recommended_action"],
        "patient_guidance": _patient_guidance(f),
        "see_a_doctor": _needs_doctor_visit(f),
        "review_status": f["review_status"].value,
        "missing_factors": f["missing_factors"],
        "patient_factors": factors,
    }


def _overall_severity(findings_raw: List[dict]) -> str | None:
    if not findings_raw:
        return None
    return max(findings_raw, key=lambda f: _SEVERITY_RANK[f["severity"]])["severity"].value


@public_bp.route("/api/self-check", methods=["POST"])
@limiter.limit("15 per minute")
def self_check():
    """
    { medications: [str], allergies: [str] } -> deterministic findings only,
    no LLM/embedding calls — cheap and safe to be fully public. Each
    finding's clinical_effect is already real dataset text; plain-language
    explanations are a separate, on-demand /api/explain call so a single
    submission never fans out into many Groq/Cohere calls automatically.
    """
    payload = request.get_json(force=True, silent=True) or {}
    medications = _clean_str_list(payload.get("medications"), MAX_SELF_CHECK_ITEMS, MAX_ITEM_LEN)
    allergies = _clean_str_list(payload.get("allergies"), MAX_SELF_CHECK_ITEMS, MAX_ITEM_LEN)

    if not medications:
        return {"error": "at least one medication is required"}, 400

    with get_session() as session:
        resolved, findings_raw, ingredient_names = _resolve_and_evaluate(session, medications, allergies)
        coverage = ddi_coverage_report(session, ingredient_names)

    findings = [_serialize_finding(f, i) for i, f in enumerate(findings_raw)]
    return {
        "resolved_medications": resolved,
        "findings": findings,
        "overall_severity": _overall_severity(findings_raw),
        "see_a_doctor": any(f["see_a_doctor"] for f in findings),
        # What was actually checked, not just what was found — "no findings"
        # on its own can't distinguish "checked, nothing concerning" from
        # "checked, but the knowledge base has no rule for this pair at
        # all" (pairs_with_no_rule below). Absence of a finding was already
        # documented throughout this codebase as "not a safety claim" —
        # this is that principle actually reaching the API response instead
        # of staying a comment.
        "ddi_coverage": coverage,
    }, 200


@public_bp.route("/api/explain", methods=["POST"])
@limiter.limit("10 per minute")  # tighter than self_check — this is the
# expensive path (real Cohere + Groq calls every time), not just a DB lookup.
def explain_self_check_finding():
    """
    On-demand plain-language explanation for one finding from a prior
    /api/self-check response. Re-runs the same deterministic evaluation
    from the raw (medications, allergies) inputs rather than trusting a
    client-supplied clinical_effect/severity directly — otherwise this
    endpoint would let anyone get our Groq/Cohere keys to "explain" an
    arbitrary fabricated finding that the rule engine never actually
    produced.
    """
    payload = request.get_json(force=True, silent=True) or {}
    medications = _clean_str_list(payload.get("medications"), MAX_SELF_CHECK_ITEMS, MAX_ITEM_LEN)
    allergies = _clean_str_list(payload.get("allergies"), MAX_SELF_CHECK_ITEMS, MAX_ITEM_LEN)
    patient_notes = safe_str(payload.get("patient_notes", "")).strip()[:MAX_NOTES_LEN]

    try:
        finding_index = int(payload.get("finding_index"))
    except (TypeError, ValueError):
        return {"error": "finding_index must be an integer"}, 400

    if not medications:
        return {"error": "at least one medication is required"}, 400

    with get_session() as session:
        resolved, findings_raw, _ = _resolve_and_evaluate(session, medications, allergies)

    if finding_index < 0 or finding_index >= len(findings_raw):
        return {"error": "finding_index out of range for these inputs"}, 400

    finding = findings_raw[finding_index]
    factors = finding.get("patient_factors") or {}
    drug_name = factors.get("ingredient") or factors.get("ingredient_a") or None

    result = explain_finding(
        finding_type=finding["type"].value,
        severity=finding["severity"].value,
        clinical_effect=finding["clinical_effect"],
        recommended_action=finding["recommended_action"],
        drug_name=drug_name,
        model_name=GROQ_MODEL,
        audience="patient",
        patient_notes=patient_notes,
    )
    return {
        "explanation": result["explanation"],
        "citations": result["citations"],
        "evidence_hash": result["evidence_hash"],
    }, 200

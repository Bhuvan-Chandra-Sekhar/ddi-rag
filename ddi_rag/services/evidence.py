"""
services/evidence.py — Evidence retrieval + constrained explanation
(architecture doc, section 4 "Evidence service" / "Explanation service" +
roadmap Phase 4).

This module explains a Finding that the deterministic rule engine
(services/clinical_rules.py) already froze — it never determines or
modifies type, severity, or recommended_action. Structurally, the
functions here only ever return explanation-shaped fields (explanation
text, citations, evidence_hash, model/prompt version); callers attach
those to an existing Finding row without touching its clinical fields.

pgvector retrieval and Groq generation are the same underlying calls
services/rag_pipeline.py already makes — this module is the "internal
interface" the doc asks for so nothing outside this file talks to the
evidence store/Groq directly for explanation purposes.
"""

import hashlib
import logging
from typing import List, Optional

from services.rag_pipeline import _call_groq_api, retrieve_chunks, safe_str

log = logging.getLogger("ddi.evidence")

PROMPT_VERSION = "explain-finding-v1"

_EXPLAIN_SYSTEM_PROMPT = (
    "You are a clinical pharmacist writing a plain-language explanation of a "
    "SAFETY FINDING that has already been determined by a deterministic rule "
    "engine. The finding's type, severity, and recommended action are FIXED "
    "and FINAL — you must not restate them differently, contradict them, "
    "soften them, escalate them, or invent a different action. Your only job "
    "is to explain, in plain clinical language, why this finding matters, "
    "using ONLY the FDA evidence passages provided. Do not invent facts not "
    "present in the evidence. Do not give a different clinical recommendation."
)


def retrieve_supporting_evidence(query: str, drug_name: Optional[str] = None, top_k: int = 3) -> List[dict]:
    """Thin wrapper over rag_pipeline.retrieve_chunks — the evidence-service
    boundary. Returns [] on any retrieval failure rather than raising, since
    missing evidence must not block a finding from reaching the pharmacist."""
    try:
        chunks = retrieve_chunks(query=query, top_k=top_k, drug_name=drug_name)
    except Exception:
        log.exception("Evidence retrieval failed for query=%r", query)
        return []

    if chunks.empty:
        return []
    return [
        {
            "generic_name": safe_str(row.get("generic_name", "")),
            "section": safe_str(row.get("section", "")),
            "text": safe_str(row.get("text", "")),
            "score": float(row.get("score", 0.0)),
        }
        for _, row in chunks.iterrows()
    ]


def _evidence_hash(finding_summary: str, evidence: List[dict]) -> str:
    """Stable hash over the frozen finding + the exact evidence passages used,
    so an explanation's citations can always be traced back to what produced them."""
    joined = finding_summary + "||" + "||".join(e["text"] for e in evidence)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def explain_finding(
    finding_type: str,
    severity: str,
    clinical_effect: str,
    recommended_action: str,
    drug_name: Optional[str] = None,
    model_name: str = "",
) -> dict:
    """
    Generate a constrained explanation for an already-frozen finding.

    Returns:
        explanation   : str
        citations     : list[dict]  — the exact evidence passages used
        evidence_hash : str
        model_version : str
        prompt_version: str

    Never returns or implies a type/severity/action — those are inputs the
    caller already decided; this function only explains them.
    """
    finding_summary = f"[{finding_type}/{severity}] {clinical_effect}"
    query = clinical_effect or finding_summary
    evidence = retrieve_supporting_evidence(query, drug_name=drug_name)

    evidence_block = "\n".join(
        f"[{i}] ({e['section']}) {e['text'][:300]}" for i, e in enumerate(evidence, 1)
    ) or "(no supporting FDA evidence passage retrieved)"

    messages = [
        {"role": "system", "content": _EXPLAIN_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Finding type: {finding_type}\n"
                f"Severity (fixed, do not change): {severity}\n"
                f"Clinical effect: {clinical_effect}\n"
                f"Recommended action (fixed, do not change): {recommended_action}\n\n"
                f"FDA evidence:\n{evidence_block}\n\n"
                "Write a short plain-language explanation of this finding for "
                "the reviewing pharmacist, grounded only in the evidence above."
            ),
        },
    ]

    explanation = _call_groq_api(messages, temperature=0.2, max_tokens=400)

    return {
        "explanation": safe_str(explanation),
        "citations": evidence,
        "evidence_hash": _evidence_hash(finding_summary, evidence),
        "model_version": model_name,
        "prompt_version": PROMPT_VERSION,
    }

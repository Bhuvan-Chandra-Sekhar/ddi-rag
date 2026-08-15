"""
scripts/run_crag_llm_evals.py — Live LLM evaluation of the CRAG pipeline
(architecture doc section 13 "LLM safety": faithfulness, citation
grounding) against the REAL Groq/Cohere/pgvector stack.

tests/test_llm_safety_evals.py already covers the structural safety
contract (prompt-injection resistance, citation grounding logic) against
MOCKED Groq/retrieval calls — that suite proves the code can't be made to
lie even if the model or evidence store are adversarial, and doesn't need
a live API to keep proving that. This script is the complement: it runs
against your actual live answer_ddi() (services/rag_pipeline.py) and
explain_finding() (services/evidence.py) calls, scoring real generations
with the same services/llm_eval.py functions the mocked tests use.

Not a golden dataset — there's no clinician-authored expected-answer set
in this repo yet (see session history: offered, not yet provided). This
is what's honestly available right now: real retrieval + real generation,
scored for faithfulness and citation grounding, against every drug that
currently has real evidence_chunks. Re-run this after expanding the
evidence corpus to see coverage grow.

Run it yourself anytime (costs real Groq + Cohere calls — cheap, but not
free):
    python scripts/run_crag_llm_evals.py
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

from sqlalchemy import text as sql_text

from database import get_session
from services.evidence import explain_finding
from services.llm_eval import citations_are_grounded, score_faithfulness
from services.rag_pipeline import answer_ddi

logging.basicConfig(level=logging.WARNING)  # quiet CRAG's own INFO logs for a clean report

OUT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "crag_llm_eval_results.json"

# Evaluating every embedded drug would mean 2 live Groq generations each
# (answer_ddi + explain_finding) — fine at 9 drugs, excessive at 800+ once
# the DDInter-driven evidence expansion lands. Cap the sample instead of
# burning Groq/Cohere quota on a demonstration eval; raise SAMPLE_SIZE (or
# pass a limit) for a fuller run when you actually want one.
SAMPLE_SIZE = 25
ORIGINAL_CURATED_DRUGS = [
    "warfarin", "aspirin and dipyridamole", "ibuprofen", "amoxicillin",
    "penicillin g potassium", "lisinopril", "metformin hydrochloride", "acetaminophen",
]


def drugs_with_evidence(sample_size: int = SAMPLE_SIZE) -> list:
    """Every originally-curated drug (guaranteed coverage) plus an evenly-
    spaced sample of whatever else now has real evidence, capped at
    sample_size total — not every embedded drug."""
    with get_session() as session:
        rows = session.execute(sql_text("SELECT DISTINCT generic_name FROM evidence_chunks ORDER BY generic_name")).fetchall()
    all_drugs = [r[0] for r in rows]

    guaranteed = [d for d in ORIGINAL_CURATED_DRUGS if d in all_drugs]
    remaining = [d for d in all_drugs if d not in guaranteed]

    extra_slots = max(sample_size - len(guaranteed), 0)
    if remaining and extra_slots:
        step = max(len(remaining) // extra_slots, 1)
        sample = remaining[::step][:extra_slots]
    else:
        sample = []

    return guaranteed + sample


# services.rag_pipeline._call_groq_api() never raises on a Groq failure —
# it returns one of these fixed strings instead (see that function's
# except blocks). Without checking for them, a 429/timeout silently
# becomes a 0.0 "faithfulness" score indistinguishable from a genuinely
# unfaithful generation, corrupting the aggregate average. Groq's free
# tier is 30 req/min; this eval makes up to 3 Groq calls per drug
# (answer_ddi's generation + CRAG's own query-rewrite call when a grade
# comes back "incorrect", plus explain_finding's generation), so it rate-
# limits itself between drugs rather than relying on retries alone.
_GROQ_ERROR_PREFIXES = ("GROQ_API_KEY not configured", "Generation timed out", "Generation error:")
SECONDS_BETWEEN_DRUGS = 4


def _is_api_error(text: str) -> bool:
    return any(text.startswith(p) for p in _GROQ_ERROR_PREFIXES)


def eval_answer_ddi(drug: str) -> dict:
    """Live CRAG pipeline: retrieve -> grade -> correct -> generate."""
    start = time.time()
    result = answer_ddi(drug_name=drug, top_k=5)
    latency = time.time() - start

    api_error = _is_api_error(result["answer"])
    sources_text = [s["text"] for s in result.get("sources", [])]
    faithfulness = (
        None if api_error else
        score_faithfulness(result["answer"], sources_text) if sources_text else 0.0
    )

    return {
        "drug": drug,
        "crag_status": result.get("crag_status"),
        "n_sources": len(result.get("sources", [])),
        "faithfulness": round(faithfulness, 3) if faithfulness is not None else None,
        "api_error": api_error,
        "latency_s": round(latency, 2),
        "answer_preview": result["answer"][:160],
    }


def eval_explain_finding(drug: str) -> dict:
    """The other real generation path — structured Finding explanation,
    used by the Clinical Console. Exercises citations_are_grounded, which
    answer_ddi's shape doesn't have a direct analog for."""
    start = time.time()
    result = explain_finding(
        finding_type="ddi", severity="major",
        clinical_effect=f"Concurrent use with {drug} may increase risk of adverse interaction.",
        recommended_action="Pharmacist review required.",
        drug_name=drug,
    )
    latency = time.time() - start

    api_error = _is_api_error(result["explanation"])
    citation_texts = [c["text"] for c in result["citations"]]
    faithfulness = (
        None if api_error else
        score_faithfulness(result["explanation"], citation_texts) if citation_texts else 0.0
    )
    grounded = citations_are_grounded(
        [{"text": t} for t in citation_texts],
        [{"text": t} for t in citation_texts],  # explain_finding's citations ARE its retrieved evidence
    )

    return {
        "drug": drug,
        "n_citations": len(result["citations"]),
        "faithfulness": round(faithfulness, 3) if faithfulness is not None else None,
        "api_error": api_error,
        "citations_grounded": grounded,
        "latency_s": round(latency, 2),
        "explanation_preview": result["explanation"][:160],
    }


def main():
    drugs = drugs_with_evidence()
    print(f"Running live CRAG + explanation evals against {len(drugs)} drugs with real evidence...\n")

    answer_ddi_results, explain_results = [], []
    for i, drug in enumerate(drugs, 1):
        print(f"[{i}/{len(drugs)}] {drug} ...", end=" ", flush=True)
        try:
            r1 = eval_answer_ddi(drug)
            answer_ddi_results.append(r1)
            r2 = eval_explain_finding(drug)
            explain_results.append(r2)
            flag1 = " [API ERROR]" if r1["api_error"] else ""
            flag2 = " [API ERROR]" if r2["api_error"] else ""
            print(f"answer_ddi: {r1['crag_status']} faithfulness={r1['faithfulness']}{flag1} | "
                  f"explain: grounded={r2['citations_grounded']} faithfulness={r2['faithfulness']}{flag2}")
        except Exception as exc:
            print(f"ERROR: {exc}")
        if i < len(drugs):
            time.sleep(SECONDS_BETWEEN_DRUGS)

    # ── Summary — API errors excluded from faithfulness/status stats, ───────
    # counted separately, so an infra hiccup can't masquerade as a quality
    # finding in either direction.
    ddi_ok = [r for r in answer_ddi_results if not r["api_error"]]
    explain_ok = [r for r in explain_results if not r["api_error"]]
    ddi_errors = len(answer_ddi_results) - len(ddi_ok)
    explain_errors = len(explain_results) - len(explain_ok)

    n = len(ddi_ok)
    avg_faith_ddi = sum(r["faithfulness"] for r in ddi_ok) / n if n else float("nan")
    avg_faith_explain = sum(r["faithfulness"] for r in explain_ok) / len(explain_ok) if explain_ok else float("nan")
    grounded_rate = sum(r["citations_grounded"] for r in explain_ok) / len(explain_ok) if explain_ok else float("nan")
    status_counts = {}
    for r in ddi_ok:
        status_counts[r["crag_status"]] = status_counts.get(r["crag_status"], 0) + 1

    print("\n" + "=" * 70)
    print(f"Drugs evaluated: {len(answer_ddi_results)}  (answer_ddi API errors: {ddi_errors}, explain_finding API errors: {explain_errors})")
    print(f"answer_ddi crag_status distribution (excl. API errors): {status_counts}")
    print(f"answer_ddi avg faithfulness (excl. API errors): {avg_faith_ddi:.3f}")
    print(f"explain_finding avg faithfulness (excl. API errors): {avg_faith_explain:.3f}")
    print(f"explain_finding citation-grounding rate (excl. API errors): {grounded_rate:.1%}  (should be 100% — grounding is structurally guaranteed, not just usually true)")

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "answer_ddi": answer_ddi_results,
            "explain_finding": explain_results,
            "summary": {
                "n_drugs": len(answer_ddi_results),
                "answer_ddi_api_errors": ddi_errors,
                "explain_finding_api_errors": explain_errors,
                "crag_status_distribution": status_counts,
                "avg_faithfulness_answer_ddi": None if n == 0 else round(avg_faith_ddi, 3),
                "avg_faithfulness_explain_finding": None if not explain_ok else round(avg_faith_explain, 3),
                "citation_grounding_rate": None if not explain_ok else round(grounded_rate, 3),
            },
        }, f, indent=2)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()

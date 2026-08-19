"""
scripts/run_golden_split_eval.py — Golden-set RAG evaluation via a real,
reproducible 80/20 held-out split (no clinician-authored gold dataset exists
for this project — flagged repeatedly in session history, offered, never
provided). This builds the next best thing from real data instead of a
synthetic fixture.

Population: every drug that has BOTH real FDA label text (data/datasets/
clean_ddi_dataset.csv — the actual openFDA source, loaded through the SAME
data_preprocessing.load_and_clean_data() used when the corpus was originally
ingested, so drug-name normalization is guaranteed to match evidence_chunks
exactly) AND real Cohere embeddings already in evidence_chunks (currently
800 of ~2,481 unique drugs in the source CSV — the other ~1,681 were never
embedded, so evaluating against them would just restate the known coverage
gap, not measure retrieval/generation quality).

Split: sklearn train_test_split(test_size=0.2, random_state=42) over that
~800-drug population, by drug (not by row/chunk — a drug's rows never split
across train and test). Deterministic: re-running this script always
evaluates the same ~160 held-out drugs, so results are actually comparable
run over run, not a fresh random sample each time. The 80% "train" side
isn't used by anything here (nothing in this repo trains on it) — it exists
so this is a real held-out methodology, and so a future rule-approval or
prompt-tuning pass has an obvious set to pull examples from without ever
touching the eval set.

Two faithfulness numbers are reported per drug, both via the same
services.llm_eval.score_faithfulness() lexical-overlap heuristic (still a
v1 heuristic — see that module's own caveat, not a validated measure):
  - retrieval_faithfulness: answer vs. what answer_ddi() itself retrieved
    (self-consistency — did the model stick to its own retrieved context?)
  - golden_faithfulness:    answer vs. the drug's REAL held-out label text
    (accuracy — did retrieval find/use the right information at all?)
A drug can score high on the first and low on the second (fluent, grounded
in *something*, but not the actually-relevant passage) — that gap is the
whole point of comparing against a real external source instead of only
the pipeline's own output.

Run:
    python scripts/run_golden_split_eval.py             # full 20% test split (~160 drugs, ~35 min, $0)
    python scripts/run_golden_split_eval.py --limit 10   # smoke test first
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

from sklearn.model_selection import train_test_split
from sqlalchemy import text as sql_text

from data_preprocessing import load_and_clean_data
from database import get_session
from services.llm_eval import score_faithfulness
from services.rag_pipeline import answer_ddi

logging.basicConfig(level=logging.WARNING)  # quiet CRAG's own INFO logs for a clean report

OUT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "golden_split_eval_results.json"
# config.DATA_CSV's default ("./data/clean_ddi_dataset.csv") predates the
# data/datasets/ reorganization and is stale — scripts/ingest_evidence.py
# already works around this by hardcoding the real path; matching that
# pattern here rather than relying on the stale default.
CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "clean_ddi_dataset.csv"
RANDOM_STATE = 42
TEST_SIZE = 0.2

# Cohere's trial key is documented (docs/SESSION_HANDOFF.md §3) at roughly
# 5 calls/min for Embed specifically — tighter than Groq's 30/min free tier.
# answer_ddi() makes one Cohere embed call per drug (embedding the query) plus
# up to 2 Groq generations (main answer + CRAG rewrite on a low-relevance
# grade). Pacing to the tighter of the two constraints.
SECONDS_BETWEEN_DRUGS = 13

_GROQ_ERROR_PREFIXES = ("GROQ_API_KEY not configured", "Generation timed out", "Generation error:")


def _is_api_error(text: str) -> bool:
    return any(text.startswith(p) for p in _GROQ_ERROR_PREFIXES)


def _embedded_drug_names() -> set:
    with get_session() as session:
        rows = session.execute(sql_text("SELECT DISTINCT generic_name FROM evidence_chunks")).fetchall()
    return {r[0] for r in rows}


def build_golden_split(test_size: float = TEST_SIZE, random_state: int = RANDOM_STATE):
    """
    Returns (train_drugs, test_drugs, golden_text_by_drug) — golden_text_by_drug
    only covers test_drugs (that's all this script needs), built by
    concatenating every unique non-empty drug_interactions/warnings value
    across all of that drug's rows in the source CSV (openFDA has many
    near-duplicate label submissions per drug across manufacturers/NDCs —
    e.g. gabapentin alone has 382 rows — so this reflects the real range of
    what could have been embedded for that drug, not just one submission).
    """
    df = load_and_clean_data(str(CSV_PATH))
    embedded = _embedded_drug_names()
    df = df[df["final_generic_name"].isin(embedded)]

    golden_text_by_drug = {}
    for drug, group in df.groupby("final_generic_name"):
        parts = []
        for col in ("drug_interactions", "warnings"):
            if col not in group.columns:
                continue
            for val in group[col].dropna().unique():
                val = str(val).strip()
                if val and val not in parts:
                    parts.append(val)
        golden_text_by_drug[drug] = "\n".join(parts)

    all_drugs = sorted(golden_text_by_drug.keys())
    train_drugs, test_drugs = train_test_split(all_drugs, test_size=test_size, random_state=random_state)
    return train_drugs, test_drugs, golden_text_by_drug


def eval_drug(drug: str, golden_text: str) -> dict:
    start = time.time()
    result = answer_ddi(drug_name=drug, top_k=5)
    latency = time.time() - start

    api_error = _is_api_error(result["answer"])
    sources_text = [s["text"] for s in result.get("sources", [])]

    retrieval_faithfulness = None
    golden_faithfulness = None
    if not api_error:
        retrieval_faithfulness = score_faithfulness(result["answer"], sources_text) if sources_text else 0.0
        golden_faithfulness = score_faithfulness(result["answer"], [golden_text]) if golden_text else None

    return {
        "drug": drug,
        "crag_status": result.get("crag_status"),
        "n_sources": len(result.get("sources", [])),
        "has_golden_text": bool(golden_text),
        "retrieval_faithfulness": round(retrieval_faithfulness, 3) if retrieval_faithfulness is not None else None,
        "golden_faithfulness": round(golden_faithfulness, 3) if golden_faithfulness is not None else None,
        "api_error": api_error,
        "latency_s": round(latency, 2),
        "answer_preview": result["answer"][:160],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N test-split drugs (smoke test).")
    args = parser.parse_args()

    print("Building golden split from real data (clean_ddi_dataset.csv ∩ embedded evidence_chunks)...")
    train_drugs, test_drugs, golden_text_by_drug = build_golden_split()
    eval_drugs = test_drugs[: args.limit] if args.limit else test_drugs

    print(f"Population: {len(train_drugs) + len(test_drugs)} drugs with real label text AND real embeddings.")
    print(f"Split: {len(train_drugs)} train (80%) / {len(test_drugs)} test (20%), random_state={RANDOM_STATE}.")
    print(f"Evaluating {len(eval_drugs)} test-split drug(s) against the live RAG pipeline...\n")

    results = []
    for i, drug in enumerate(eval_drugs, 1):
        golden_text = golden_text_by_drug.get(drug, "")
        print(f"[{i}/{len(eval_drugs)}] {drug} ...", end=" ", flush=True)
        try:
            r = eval_drug(drug, golden_text)
            results.append(r)
            flag = " [API ERROR]" if r["api_error"] else ""
            print(f"crag_status={r['crag_status']} retrieval_faithfulness={r['retrieval_faithfulness']} "
                  f"golden_faithfulness={r['golden_faithfulness']}{flag}")
        except Exception as exc:
            print(f"ERROR: {exc}")
            results.append({"drug": drug, "error": str(exc)})
        if i < len(eval_drugs):
            time.sleep(SECONDS_BETWEEN_DRUGS)

    ok = [r for r in results if not r.get("api_error") and not r.get("error")]
    errors = len(results) - len(ok)
    golden_scored = [r for r in ok if r["golden_faithfulness"] is not None]

    n = len(ok)
    avg_retrieval_faith = sum(r["retrieval_faithfulness"] for r in ok) / n if n else float("nan")
    avg_golden_faith = (
        sum(r["golden_faithfulness"] for r in golden_scored) / len(golden_scored)
        if golden_scored else float("nan")
    )
    status_counts = {}
    for r in ok:
        status_counts[r["crag_status"]] = status_counts.get(r["crag_status"], 0) + 1

    print("\n" + "=" * 70)
    print(f"Test-split drugs evaluated: {len(results)}  (API errors: {errors})")
    print(f"crag_status distribution (excl. errors): {status_counts}")
    print(f"avg retrieval_faithfulness (answer vs. its own retrieved chunks): {avg_retrieval_faith:.3f}")
    print(f"avg golden_faithfulness (answer vs. real held-out FDA label text): {avg_golden_faith:.3f}")
    print("A material gap between the two (golden lower) means retrieval is finding fluent-but-off-target evidence.")

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "split": {
                "random_state": RANDOM_STATE, "test_size": TEST_SIZE,
                "train_drug_count": len(train_drugs), "test_drug_count": len(test_drugs),
                "train_drugs": train_drugs, "test_drugs": test_drugs,
            },
            "results": results,
            "summary": {
                "n_evaluated": len(results),
                "api_errors": errors,
                "crag_status_distribution": status_counts,
                "avg_retrieval_faithfulness": None if n == 0 else round(avg_retrieval_faith, 3),
                "avg_golden_faithfulness": None if not golden_scored else round(avg_golden_faith, 3),
            },
        }, f, indent=2)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()

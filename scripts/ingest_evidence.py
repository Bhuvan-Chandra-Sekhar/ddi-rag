"""
scripts/ingest_evidence.py — One-time manual ingestion of a curated slice of
the real openFDA corpus + real DDI pairs into the live Supabase database.

This is NOT the full corpus (66,695 FDA label rows / ~930k chunks per the
project docs) — embedding and inserting that much data is a separate,
much longer-running operational job (real time + real Cohere API cost),
not something to kick off unattended in an interactive session. This
script ingests a curated list of drugs actually used in this project's
test/demo scenarios, for real, so the CRAG pipeline has genuine evidence
to retrieve instead of an empty table.

Run it yourself anytime:
    python scripts/ingest_evidence.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

import pandas as pd

from data_preprocessing import load_and_clean_data
from services.clinical_rules import ingest_pairs_csv
from services.evidence_store import init_evidence_store, upsert_chunks
from services.rag_pipeline import build_chunk_df
from database import get_session

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "clean_ddi_dataset.csv"
PAIRS_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "fully_processed_dataset.csv"

# Drugs used across this project's example scenarios, tests, and demos.
CURATED_DRUGS = [
    "warfarin", "aspirin", "ibuprofen", "amoxicillin",
    "penicillin g potassium", "lisinopril", "metformin hydrochloride", "acetaminophen",
]
ROWS_PER_DRUG = 2   # openFDA has many near-duplicate labels per drug (different manufacturers)


def select_curated_rows(raw_df: pd.DataFrame) -> pd.DataFrame:
    names = raw_df["openfda_generic_name"].astype(str).str.lower().str.strip()
    picked = []
    for target in CURATED_DRUGS:
        exact = raw_df[names == target]
        if not exact.empty:
            picked.append(exact.head(ROWS_PER_DRUG))
            continue
        contains = raw_df[names.str.contains(target, na=False, regex=False)].copy()
        if contains.empty:
            print(f"  WARNING: no rows found for {target!r}")
            continue
        contains["_len"] = names.loc[contains.index].str.len()
        picked.append(contains.sort_values("_len").head(ROWS_PER_DRUG).drop(columns="_len"))
    return pd.concat(picked, ignore_index=True) if picked else pd.DataFrame()


def main():
    print(f"Loading raw CSV: {CSV_PATH}")
    raw_df = pd.read_csv(CSV_PATH)
    print(f"  {len(raw_df)} total FDA label rows available")

    curated_raw = select_curated_rows(raw_df)
    print(f"Selected {len(curated_raw)} rows for curated drugs: {CURATED_DRUGS}")

    print("Running real cleaning pipeline (data_preprocessing.load_and_clean_data logic)...")
    # load_and_clean_data expects a file path; write the curated subset to a
    # temp CSV so the exact same real cleaning code path runs on it.
    tmp_path = Path(__file__).resolve().parent / "_curated_subset.csv"
    curated_raw.to_csv(tmp_path, index=False)
    clean_df = load_and_clean_data(str(tmp_path))
    tmp_path.unlink(missing_ok=True)

    print("Building chunks (services.rag_pipeline.build_chunk_df)...")
    chunk_df = build_chunk_df(clean_df)
    print(f"  {len(chunk_df)} chunks built")

    print("Initializing evidence store (pgvector extension + table)...")
    init_evidence_store()

    print("Embedding + upserting chunks into evidence_chunks (real Cohere calls)...")
    n = upsert_chunks(chunk_df)
    print(f"  Upserted {n} chunks")

    print(f"\nLoading DDI pairs CSV: {PAIRS_CSV_PATH}")
    pairs_df = pd.read_csv(PAIRS_CSV_PATH)
    lower_targets = [d.split()[0] for d in CURATED_DRUGS]  # match on first word (ingredient root)
    pattern = "|".join(lower_targets)  # vectorized regex match — .apply() over 188k rows was the slow part
    mask = (
        pairs_df["Drug 1"].astype(str).str.lower().str.contains(pattern, regex=True, na=False)
        | pairs_df["Drug 2"].astype(str).str.lower().str.contains(pattern, regex=True, na=False)
    )
    curated_pairs = pairs_df[mask]
    print(f"  {len(curated_pairs)} pairs involve a curated drug (out of {len(pairs_df)} total)")

    tmp_pairs_path = Path(__file__).resolve().parent / "_curated_pairs.csv"
    curated_pairs.to_csv(tmp_pairs_path, index=False)

    with get_session() as session:
        stats = ingest_pairs_csv(session, str(tmp_pairs_path), source_dataset="fully_processed_dataset.csv (curated subset)")
    tmp_pairs_path.unlink(missing_ok=True)
    print(f"  Rule ingestion: {stats}")

    print("\nDone. All ingested rules are DRAFT (unreviewed) — see services/clinical_rules.py's "
          "docstring for why: no automated ingestion is allowed to mark a rule clinically approved.")


if __name__ == "__main__":
    main()

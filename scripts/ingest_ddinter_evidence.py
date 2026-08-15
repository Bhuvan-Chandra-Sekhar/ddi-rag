"""
scripts/ingest_ddinter_evidence.py — Expand the evidence_chunks corpus to
cover the drugs the newly-ingested DDInter rules actually reference,
instead of just the original 8 curated drugs.

Scope, computed for real against the live database and the local openFDA
source before this script was written (not guessed):
    - clinical_rules has 1,939 unique drug names sourced from DDInter.
    - 798 of those exist verbatim as an openfda_generic_name in
      data/datasets/clean_ddi_dataset.csv (the rest use different naming
      conventions this script does not attempt to resolve automatically —
      same class of gap as the aspirin/penicillin naming mismatch found
      earlier this session, left for a future pass).
    - 9 of those 798 are already embedded (the original curated set).
    - This script embeds the remaining ~793 drugs.

Estimated ~11,900 chunks / ~125 batched Cohere calls (96 texts/call) —
comfortably inside the free trial's 1,000-calls/month cap, unlike the
full 66,695-drug corpus (~9,700+ calls, would need the paid tier).

Run it yourself anytime:
    python scripts/ingest_ddinter_evidence.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
from sqlalchemy import text as sql_text

from data_preprocessing import load_and_clean_data
from services.evidence_store import init_evidence_store, upsert_chunks
from services.rag_pipeline import build_chunk_df
from database import get_session

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "clean_ddi_dataset.csv"
ROWS_PER_DRUG = 2   # openFDA has many near-duplicate labels per drug (different manufacturers)


def target_drug_names() -> list:
    """Drug names referenced by DDInter-sourced rules that exactly match an
    openfda_generic_name and aren't already embedded — computed live
    against the current database state, not hardcoded."""
    with get_session() as session:
        ddinter_drugs = set()
        for row in session.execute(sql_text(
            "SELECT DISTINCT ingredient_a FROM clinical_rules WHERE source_dataset='ddinter_2.0'"
        )).fetchall():
            ddinter_drugs.add(row[0])
        for row in session.execute(sql_text(
            "SELECT DISTINCT ingredient_b FROM clinical_rules WHERE source_dataset='ddinter_2.0'"
        )).fetchall():
            ddinter_drugs.add(row[0])

        already_embedded = {
            row[0] for row in session.execute(sql_text("SELECT DISTINCT generic_name FROM evidence_chunks")).fetchall()
        }

    fda_names = set(
        pd.read_csv(CSV_PATH, usecols=["openfda_generic_name"])["openfda_generic_name"]
        .dropna().str.strip().str.lower().unique()
    )
    return sorted((ddinter_drugs & fda_names) - already_embedded)


def select_rows(raw_df: pd.DataFrame, targets: list) -> pd.DataFrame:
    names = raw_df["openfda_generic_name"].astype(str).str.lower().str.strip()
    picked = []
    missing = 0
    for target in targets:
        exact = raw_df[names == target]
        if exact.empty:
            missing += 1
            continue
        picked.append(exact.head(ROWS_PER_DRUG))
    if missing:
        print(f"  WARNING: {missing} target names had no exact-match row at ingestion time (unexpected).")
    return pd.concat(picked, ignore_index=True) if picked else pd.DataFrame()


def main():
    print("Computing target drug list from live clinical_rules + local openFDA source...")
    targets = target_drug_names()
    print(f"  {len(targets)} drugs to embed")

    print(f"Loading raw CSV: {CSV_PATH}")
    raw_df = pd.read_csv(CSV_PATH)

    selected_raw = select_rows(raw_df, targets)
    print(f"Selected {len(selected_raw)} FDA label rows for {len(targets)} target drugs")

    print("Running real cleaning pipeline (data_preprocessing.load_and_clean_data)...")
    tmp_path = Path(__file__).resolve().parent / "_ddinter_evidence_subset.csv"
    selected_raw.to_csv(tmp_path, index=False)
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


if __name__ == "__main__":
    main()

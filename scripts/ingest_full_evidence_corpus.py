"""
scripts/ingest_full_evidence_corpus.py — Expand evidence_chunks to cover
every distinct drug in the local openFDA source, not just the ones DDInter
rules happen to reference (scripts/ingest_ddinter_evidence.py did that
narrower pass already).

Scope, computed live against the local CSV and the live database before
this script was written (not guessed):
    - data/datasets/clean_ddi_dataset.csv has 66,695 rows but only 2,481
      truly distinct drug names (openFDA has many near-duplicate label
      submissions per drug across manufacturers/NDCs).
    - 800 of those 2,481 are already embedded (the original curated set +
      the DDInter-referenced expansion).
    - This script embeds the remaining 1,684 — the entire rest of the
      dataset's real, distinct drug population.

This is the "dedupe to unique drugs first" approach discussed this
session: embedding all 66,695 raw rows verbatim would mean ~9,700+ Cohere
calls (exceeds the free trial, ~$15-20 on the paid tier). Deduping to
distinct drug names and capping at ROWS_PER_DRUG raw label rows per drug
(same cap ingest_ddinter_evidence.py already uses — keeps genuinely
different manufacturer phrasing without embedding dozens of near-identical
copies) puts this at an estimated ~2,549 raw rows / ~23K chunks / ~240
batched Cohere calls (96 texts/call) — comfortably inside the free
trial's 1,000-calls/month cap, unlike the naive full-row approach.

Safe to interrupt and re-run: each batch commits individually
(services.evidence_store.upsert_chunks), upserts are idempotent
(ON CONFLICT DO UPDATE), and the target list is recomputed live from
whatever's already in evidence_chunks — a partial prior run just means
fewer drugs left to do on the next pass.

Run it yourself anytime:
    python scripts/ingest_full_evidence_corpus.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
from sqlalchemy import text as sql_text

from data_preprocessing import load_and_clean_data
from database import get_session
from services.evidence_store import init_evidence_store, upsert_chunks
from services.rag_pipeline import build_chunk_df

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "clean_ddi_dataset.csv"
ROWS_PER_DRUG = 2   # same cap ingest_ddinter_evidence.py uses — real manufacturer variation without near-duplicate bloat


def target_drug_names() -> list:
    """Every distinct openfda_generic_name in the source CSV that isn't
    already embedded — the whole dataset's real drug population, not
    scoped to any particular rule source."""
    with get_session() as session:
        already_embedded = {
            row[0] for row in session.execute(sql_text("SELECT DISTINCT generic_name FROM evidence_chunks")).fetchall()
        }
    fda_names = set(
        pd.read_csv(CSV_PATH, usecols=["openfda_generic_name"])["openfda_generic_name"]
        .dropna().str.strip().str.lower().unique()
    )
    return sorted(fda_names - already_embedded)


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
    print("Computing target drug list: every distinct CSV drug name not yet embedded...")
    targets = target_drug_names()
    print(f"  {len(targets)} drugs to embed")
    if not targets:
        print("Nothing to do — every distinct drug in the source CSV is already embedded.")
        return

    print(f"Loading raw CSV: {CSV_PATH}")
    raw_df = pd.read_csv(CSV_PATH)

    selected_raw = select_rows(raw_df, targets)
    print(f"Selected {len(selected_raw)} FDA label rows for {len(targets)} target drugs")

    print("Running real cleaning pipeline (data_preprocessing.load_and_clean_data)...")
    tmp_path = Path(__file__).resolve().parent / "_full_corpus_evidence_subset.csv"
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

"""
scripts/ingest_ddinter_rules.py — Ingest the full cleaned DDInter dataset
(scripts/clean_ddinter_dataset.py's output) into the live clinical_rules
table via services/clinical_rules.py:ingest_ddinter_csv().

Scope: the FULL 160,235-row cleaned file, not just the 8 originally-curated
drugs — a deliberate choice (evidence_chunks still only covers those 8, so
most of these rows won't have grounded LLM explanations available yet, but
the deterministic severity lookup works for any pair in the file).

Every row lands as DRAFT, same governance contract as every other rule in
this table — nothing here is auto-approved, and DRAFT rows still produce
type=UNKNOWN findings regardless of the real severity stored on them.
Existing pair_keys (from fully_processed_dataset.csv) are left untouched.

Run it yourself anytime:
    python scripts/ingest_ddinter_rules.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

from database import get_session
from services.clinical_rules import ingest_ddinter_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "ddinter" / "ddinter_cleaned.csv"


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"{CSV_PATH} not found — run scripts/clean_ddinter_dataset.py first."
        )

    with get_session() as session:
        result = ingest_ddinter_csv(session, str(CSV_PATH))

    print(f"Inserted: {result['inserted']}")
    print(f"Skipped (pair_key already existed): {result['skipped_existing']}")
    print(f"Skipped (invalid row): {result['skipped_invalid']}")


if __name__ == "__main__":
    main()

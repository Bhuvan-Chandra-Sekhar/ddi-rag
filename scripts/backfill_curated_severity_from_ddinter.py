"""
scripts/backfill_curated_severity_from_ddinter.py — Fix a real severity-
shadowing bug: every one of the 1,824 pairs from the original curated
dataset (fully_processed_dataset.csv) was ingested with severity hardcoded
to UNKNOWN (ingest_pairs_csv() never captured real severity — that dataset
didn't have a clean severity column at the time). When DDInter 2.0 was
ingested later, ingest_ddinter_csv() correctly "fills gaps only" and never
overwrites an existing pair_key — but that means these 1,824 pairs kept
their placeholder UNKNOWN severity forever, even for pairs DDInter has a
real, published severity rating for. Confirmed live: 609 of the 1,824 have
a real (non-"unknown") DDInter rating available, including 118 rated
MAJOR — one of them is sulfamethoxazole/trimethoprim (Bactrim) + warfarin,
a well-documented major bleeding-risk interaction that a patient checking
it in the app saw reported as "unknown" purely because of this shadowing
artifact, not because the data doesn't exist.

This script updates ONLY the `severity` column on those 609 rows, to
DDInter's real published rating. It does NOT touch `status` or
`review_status` — every one of these rows stays DRAFT/unreviewed exactly
as before; nothing here approves anything or grants new clinical
authority. It corrects a known-wrong placeholder value to the best real
data available, the same correction ingest_ddinter_csv() already makes
for every pair that didn't happen to already exist. clinical_effect text
is left untouched — the curated dataset's human-authored description
("warfarin may increase the anticoagulant activities of X") is generally
better prose than DDInter's synthesized placeholder for pairs that have
no real mechanism text in its bulk export, so there's no reason to
downgrade it.

Run it yourself anytime (idempotent — re-running just re-applies the same
values, changing nothing on rows already backfilled):
    python scripts/backfill_curated_severity_from_ddinter.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

import pandas as pd
from sqlalchemy import text as sql_text

from database import get_session
from enums import Severity

DDINTER_CSV = Path(__file__).resolve().parent.parent / "data" / "datasets" / "ddinter" / "ddinter_cleaned.csv"
CURATED_SOURCE = "fully_processed_dataset.csv (curated subset)"


def main():
    print(f"Loading DDInter cleaned dataset: {DDINTER_CSV}")
    ddinter = pd.read_csv(DDINTER_CSV, usecols=["alias_pair_key", "severity"]).dropna(subset=["alias_pair_key"])
    ddinter_severity = dict(zip(ddinter["alias_pair_key"], ddinter["severity"]))
    print(f"  {len(ddinter_severity)} DDInter pair_key -> severity mappings loaded")

    with get_session() as session:
        curated_rows = session.execute(sql_text(
            "SELECT pair_key, severity FROM clinical_rules "
            "WHERE source_dataset = :src AND severity = 'UNKNOWN'"
        ), {"src": CURATED_SOURCE}).fetchall()
        print(f"  {len(curated_rows)} curated-subset rows currently at placeholder UNKNOWN severity")

        updates = []
        for pair_key, _ in curated_rows:
            real_severity = ddinter_severity.get(pair_key)
            if real_severity and real_severity != "unknown":
                updates.append((pair_key, real_severity))

        print(f"  {len(updates)} of those have a real DDInter severity to backfill")
        if not updates:
            print("Nothing to do.")
            return

        for pair_key, severity_str in updates:
            session.execute(sql_text(
                "UPDATE clinical_rules SET severity = :sev, "
                "source_description = source_description || ' [severity backfilled from DDInter 2.0]' "
                "WHERE pair_key = :pk AND source_dataset = :src"
            ), {"sev": Severity(severity_str).value.upper(), "pk": pair_key, "src": CURATED_SOURCE})
        session.commit()

        from collections import Counter
        counts = Counter(sev for _, sev in updates)
        print(f"  Updated {len(updates)} rows. Severity breakdown: {dict(counts)}")


if __name__ == "__main__":
    main()

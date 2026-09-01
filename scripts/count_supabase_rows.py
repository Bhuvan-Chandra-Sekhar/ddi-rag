"""
scripts/count_supabase_rows.py — List every table in the live Supabase
Postgres database (public schema) with its row count.

Enumerates tables dynamically via information_schema rather than hardcoding
the model list, so it stays accurate as tables are added/removed. Also
reports the total across all tables, and separately calls out
clinical_rules (by status) and evidence_chunks, since those two are the
project's real "how much data do we actually have" numbers.

Run:
    python scripts/count_supabase_rows.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

from sqlalchemy import text as sql_text

from database import get_session


def main() -> None:
    with get_session() as session:
        tables = [
            row[0]
            for row in session.execute(
                sql_text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' ORDER BY tablename"
                )
            ).fetchall()
        ]

        if not tables:
            print("No tables found in the public schema.")
            return

        print(f"{len(tables)} table(s) in public schema:\n")
        counts = {}
        for t in tables:
            # Table names come from pg_tables (system catalog), not user
            # input, so this f-string is safe — sql_text() alone can't
            # parameterize an identifier position anyway.
            count = session.execute(sql_text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            counts[t] = count
            print(f"  {t:<32} {count:>10,}")

        total = sum(counts.values())
        print(f"\n{'TOTAL rows across all tables':<32} {total:>10,}")

        # Extra breakdown for the two tables that actually drive real DDI
        # answers, since "row count" alone doesn't show what's usable.
        if "clinical_rules" in counts:
            print("\nclinical_rules by status:")
            for row in session.execute(
                sql_text("SELECT status, COUNT(*) FROM clinical_rules GROUP BY status ORDER BY status")
            ).fetchall():
                print(f"  {row[0]:<15} {row[1]:>10,}")

        if "evidence_chunks" in counts:
            distinct_drugs = session.execute(
                sql_text("SELECT COUNT(DISTINCT generic_name) FROM evidence_chunks")
            ).scalar()
            print(f"\nevidence_chunks: {counts['evidence_chunks']:,} chunks across {distinct_drugs:,} distinct drugs")


if __name__ == "__main__":
    main()

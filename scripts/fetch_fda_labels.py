"""
scripts/fetch_fda_labels.py — Phase 1 of the FDA-label DDI mining pipeline:
fetch every known drug's live openFDA label text, no extraction yet.

This replaces the old scripts/mine_ddi_pairs_from_fda_labels.py, which
called Groq once per drug inside the fetch loop itself -- that made the
whole pipeline bottlenecked by Groq's rate limits (multi-hour runtime for
2,481 drugs) even though openFDA itself is generous (~240 req/min,
120,000/day with the key in config.OPENFDA_API_KEY). Splitting fetch from
extraction means this phase is bounded only by openFDA's own limits: well
under an hour for the full drug list. Extraction is a separate, pure-Python
phase -- see mine_ddi_pairs_aho_corasick.py.

Stores raw drug_interactions text (or "" when a drug has no live label or
an empty section) keyed by drug name in one JSON file. An empty string is
still a completed result, not a gap -- so resuming this script never
re-fetches a drug it already has an answer for, successful or not.

Resilience: the file is rewritten every BATCH_SIZE drugs (not only at the
very end), so a crash mid-run loses at most one batch's worth of fetches,
matching the batch-checkpoint pattern the old script established after a
real incident where a single long-held state was lost entirely on a crash.

Run:
    python scripts/fetch_fda_labels.py --limit 10   # smoke test
    python scripts/fetch_fda_labels.py               # full run
    python scripts/fetch_fda_labels.py --drugs digoxin,warfarin
    python scripts/fetch_fda_labels.py --fresh        # ignore saved progress
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

import pandas as pd
import requests

from config import OPENFDA_API_KEY, OPENFDA_BASE_URL
from services.rag_pipeline import safe_str

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
log = logging.getLogger("ddi.fetch_fda_labels")

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "clean_ddi_dataset.csv"
TEXTS_PATH = Path(__file__).resolve().parent.parent / "outputs" / "fda_label_texts.json"
OPENFDA_TIMEOUT = 10
BATCH_SIZE = 50
# openFDA's real cap (confirmed live) is ~240 req/min either way, keyed or
# not -- 0.3s between calls is ~200/min, a comfortable margin, and still
# finishes the full 2,481-drug list in well under 15 minutes.
SLEEP_SECONDS = 0.3


def _all_target_drugs() -> list:
    return sorted(
        pd.read_csv(CSV_PATH, usecols=["openfda_generic_name"])["openfda_generic_name"]
        .dropna().str.strip().str.lower().unique()
    )


def fetch_live_label_interactions(drug_name: str) -> str:
    """Live openFDA lookup — returns the complete drug_interactions text,
    or '' on any failure (no result, network error, malformed response).
    Fails closed: a missing label for one drug must not stop the run."""
    params = {"search": f'openfda.generic_name:"{drug_name}"', "limit": 1}
    if OPENFDA_API_KEY:
        params["api_key"] = OPENFDA_API_KEY
    try:
        r = requests.get(OPENFDA_BASE_URL, params=params, timeout=OPENFDA_TIMEOUT)
        if r.status_code != 200:
            return ""
        results = r.json().get("results") or []
        if not results:
            return ""
        return safe_str((results[0].get("drug_interactions") or [""])[0])
    except Exception:
        log.warning("openFDA fetch failed for %r", drug_name, exc_info=True)
        return ""


def _load_texts() -> dict:
    if TEXTS_PATH.exists():
        return json.loads(TEXTS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_texts(texts: dict) -> None:
    TEXTS_PATH.parent.mkdir(exist_ok=True)
    TEXTS_PATH.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Fetch only the first N drugs (smoke test).")
    parser.add_argument("--drugs", type=str, default=None, help="Comma-separated exact drug names to fetch instead of the full list.")
    parser.add_argument("--fresh", action="store_true", help="Ignore any saved progress and start over from the beginning.")
    args = parser.parse_args()

    print(f"openFDA API key configured: {bool(OPENFDA_API_KEY)} "
          f"({'120,000' if OPENFDA_API_KEY else '1,000'} requests/day cap)")

    all_targets = [d.strip().lower() for d in args.drugs.split(",")] if args.drugs else _all_target_drugs()
    texts = {} if args.fresh else _load_texts()
    if texts:
        print(f"Resuming: {len(texts)} drugs already fetched in a prior run (see {TEXTS_PATH.name}).")
    targets = [d for d in all_targets if d not in texts]
    if args.limit:
        targets = targets[: args.limit]
    print(f"Fetching {len(targets)} of {len(all_targets)} drugs this run...\n")
    if not targets:
        print("Nothing left to do. Next: python scripts/mine_ddi_pairs_aho_corasick.py")
        return

    found = empty = 0
    for i, drug in enumerate(targets, 1):
        text = fetch_live_label_interactions(drug)
        texts[drug] = text
        if text:
            found += 1
            print(f"[{i}/{len(targets)}] {drug} ... {len(text)} chars")
        else:
            empty += 1
            print(f"[{i}/{len(targets)}] {drug} ... no label / empty section")
        if i % BATCH_SIZE == 0 or i == len(targets):
            _save_texts(texts)
            print(f"  -- checkpoint saved, {len(texts)}/{len(all_targets)} drugs fetched overall --")
        if i < len(targets):
            time.sleep(SLEEP_SECONDS)

    print("\n" + "=" * 70)
    print(f"Drugs fetched this run: {len(targets)}")
    print(f"Labels with drug_interactions text: {found}")
    print(f"No label / empty section: {empty}")
    print(f"Total stored: {len(texts)}/{len(all_targets)}")
    print("Run --fresh to ignore saved progress and start over; otherwise re-running resumes automatically.")
    print("Next: python scripts/mine_ddi_pairs_aho_corasick.py")


if __name__ == "__main__":
    main()

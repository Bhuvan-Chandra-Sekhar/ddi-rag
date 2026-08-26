"""
scripts/mine_ddi_pairs_aho_corasick.py — Phase 2 of the FDA-label DDI mining
pipeline: extract candidate interacting-drug pairs from already-fetched
label text, deterministically, with no LLM call at all.

Why this replaces Groq extraction: the old scripts/mine_ddi_pairs_from_
fda_labels.py asked Groq to find every OTHER drug named in a label's free-
text drug_interactions section and quote a short excerpt. That's really
just multi-pattern string matching -- and this codebase already has a
production-grade one: ddi_rag/aho_corasick.py, used by app.py's
parse_prescription() to find every known drug name in a text in a single
O(text_length + matches) pass. Reusing it here means: no LLM cost, no rate
limits, no paraphrased/hallucination-prone excerpts (this extracts the
LITERAL sentence around each match instead), and a phase that runs in
seconds-to-low-minutes for the whole corpus instead of hours.

Governance is identical to every other ingestion path in this codebase:
rows are inserted as status=DRAFT, severity=UNKNOWN, never overwriting an
existing pair_key -- gap-filling only. source_dataset is a distinct,
honest tag ("fda_label_aho_corasick_match") so a reviewer can always tell
this candidate came from deterministic string matching against a live FDA
label, a different (and differently fallible -- see below) confidence
class than a curated database's own severity rating, and also distinct
from the retired Groq-extraction path's own tag. Nothing here is ever
auto-approved.

What Aho-Corasick catches that Groq doesn't, and vice versa: this is a
literal substring matcher with word-boundary filtering, not a language
model -- it cannot tell "no interaction with X" from "interacts with X"
the way a reader (or an LLM) can, so a small amount of false-positive noise
(negated mentions, comparison mentions, drug-class caveats naming an
example drug) is an expected, honest tradeoff for zero LLM cost and
auditable-by-construction excerpts. Every row still starts as an
unreviewed DRAFT candidate, same as before -- a human always adjudicates.

Prerequisite: run scripts/fetch_fda_labels.py first (this script reads its
output, outputs/fda_label_texts.json, and does no HTTP calls of its own).

Run:
    python scripts/mine_ddi_pairs_aho_corasick.py --limit 10   # smoke test
    python scripts/mine_ddi_pairs_aho_corasick.py               # full run
    python scripts/mine_ddi_pairs_aho_corasick.py --fresh        # ignore saved progress
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

import pandas as pd
from sqlalchemy import text as sql_text

from aho_corasick import AhoCorasick, is_word_boundary_match
from database import get_session
from enums import FindingType, RuleStatus, Severity
from models import ClinicalRule

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "datasets" / "clean_ddi_dataset.csv"
TEXTS_PATH = Path(__file__).resolve().parent.parent / "outputs" / "fda_label_texts.json"
PROGRESS_PATH = Path(__file__).resolve().parent.parent / "outputs" / "fda_aho_corasick_progress.json"
SOURCE_DATASET = "fda_label_aho_corasick_match"
RULE_VERSION = "fda-label-aho-corasick-v1"
# No network calls in this phase -- a much larger batch than the old
# Groq-paced script's BATCH_SIZE=20 is safe; this only bounds how much work
# a mid-run crash could lose, not any external rate limit.
BATCH_SIZE = 100
EXCERPT_WINDOW_CHARS = 300
EXCERPT_MAX_CHARS = 800


def _all_target_drugs() -> list:
    return sorted(
        pd.read_csv(CSV_PATH, usecols=["openfda_generic_name"])["openfda_generic_name"]
        .dropna().str.strip().str.lower().unique()
    )


def _load_texts() -> dict:
    if not TEXTS_PATH.exists():
        return {}
    return json.loads(TEXTS_PATH.read_text(encoding="utf-8"))


def _load_progress() -> set:
    if PROGRESS_PATH.exists():
        return set(json.loads(PROGRESS_PATH.read_text(encoding="utf-8")))
    return set()


def _save_progress(done: set) -> None:
    PROGRESS_PATH.parent.mkdir(exist_ok=True)
    PROGRESS_PATH.write_text(json.dumps(sorted(done)), encoding="utf-8")


def _pair_key(a: str, b: str) -> str:
    left, right = sorted([a.strip().lower(), b.strip().lower()])
    return f"{left}||{right}"


def _extract_excerpt(text: str, start: int, end: int) -> str:
    """The literal sentence containing the match, not a paraphrase -- falls
    back to a bounded character window when no clean sentence boundary is
    found nearby (label text sometimes uses semicolon lists or fragments
    without periods)."""
    lo = max(0, start - EXCERPT_WINDOW_CHARS)
    hi = min(len(text), end + EXCERPT_WINDOW_CHARS)
    left_boundary = text.rfind(". ", lo, start)
    sentence_start = left_boundary + 2 if left_boundary != -1 else lo
    right_boundary = text.find(". ", end, hi)
    sentence_end = right_boundary + 1 if right_boundary != -1 else hi
    excerpt = text[sentence_start:sentence_end].strip()
    return excerpt[:EXCERPT_MAX_CHARS]


def _process_one(session, source_drug: str, text: str, automaton: AhoCorasick,
                  existing_keys: set, seen_this_run: set) -> dict:
    """Returns {"matched_drugs", "new_count"} — never raises; a malformed
    text for one drug must not take down the whole batch."""
    if not text:
        return {"matched_drugs": 0, "new_count": 0}
    lowered = text.lower()
    matches = automaton.find_all(lowered)

    seen_patterns_this_drug = set()
    new_count = 0
    for m in matches:
        if m.pattern == source_drug:
            continue
        if m.pattern in seen_patterns_this_drug:
            continue
        if not is_word_boundary_match(lowered, m.start, m.end):
            continue
        seen_patterns_this_drug.add(m.pattern)

        key = _pair_key(source_drug, m.pattern)
        if key in existing_keys or key in seen_this_run:
            continue
        seen_this_run.add(key)

        excerpt = _extract_excerpt(text, m.start, m.end)
        left, right = sorted([source_drug, m.pattern])
        session.add(ClinicalRule(
            rule_type=FindingType.DDI, pair_key=key,
            ingredient_a=left, ingredient_b=right,
            clinical_effect=excerpt,
            severity=Severity.UNKNOWN,
            source_description=(
                f"Literal match: {m.pattern!r} found by name in {source_drug}'s "
                "live FDA label drug_interactions section (deterministic "
                "Aho-Corasick match, no LLM)."
            ),
            source_dataset=SOURCE_DATASET,
            status=RuleStatus.DRAFT,
            rule_version=RULE_VERSION,
        ))
        new_count += 1

    return {"matched_drugs": len(seen_patterns_this_drug), "new_count": new_count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N fetched drugs (smoke test).")
    parser.add_argument("--fresh", action="store_true", help="Ignore any saved progress and start over from the beginning.")
    args = parser.parse_args()

    texts = _load_texts()
    if not texts:
        print(f"No fetched label text found at {TEXTS_PATH} — run scripts/fetch_fda_labels.py first.")
        return

    all_targets = _all_target_drugs()
    print(f"Building Aho-Corasick automaton from {len(all_targets)} known drug names...")
    automaton = AhoCorasick(all_targets)

    done = set() if args.fresh else _load_progress()
    if done:
        print(f"Resuming: {len(done)} drugs already processed in a prior run (see {PROGRESS_PATH.name}).")
    targets = [d for d in texts if d not in done]
    if args.limit:
        targets = targets[: args.limit]
    print(f"Processing {len(targets)} of {len(texts)} fetched drugs this run...\n")
    if not targets:
        print("Nothing left to do.")
        return

    with get_session() as session:
        existing_keys = {row[0] for row in session.execute(sql_text("SELECT pair_key FROM clinical_rules")).fetchall()}
    print(f"{len(existing_keys)} existing pair_keys loaded — never overwritten, only gaps filled.\n")

    seen_this_run = set()
    inserted = no_text = 0
    total_matched_drugs = 0

    for batch_start in range(0, len(targets), BATCH_SIZE):
        batch = targets[batch_start: batch_start + BATCH_SIZE]
        with get_session() as session:
            for j, drug in enumerate(batch):
                i = batch_start + j + 1
                text = texts.get(drug, "")
                if not text:
                    no_text += 1
                    print(f"[{i}/{len(targets)}] {drug} ... no label text")
                else:
                    result = _process_one(session, drug, text, automaton, existing_keys, seen_this_run)
                    inserted += result["new_count"]
                    total_matched_drugs += result["matched_drugs"]
                    print(f"[{i}/{len(targets)}] {drug} ... {result['matched_drugs']} drug(s) matched, {result['new_count']} new pair(s)")
                done.add(drug)
            session.commit()
        existing_keys |= seen_this_run
        _save_progress(done)
        print(f"  -- batch committed, {len(done)}/{len(texts)} drugs done overall --")

    print("\n" + "=" * 70)
    print(f"Drugs processed this run: {len(targets)}")
    print(f"No label text (skipped): {no_text}")
    print(f"Total drug mentions matched (all occurrences, incl. already-known pairs): {total_matched_drugs}")
    print(f"New candidate pairs inserted: {inserted}")
    print("Run --fresh to ignore saved progress and start over; otherwise re-running resumes automatically.")


if __name__ == "__main__":
    main()

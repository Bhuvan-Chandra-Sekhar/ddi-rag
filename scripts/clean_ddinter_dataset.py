"""
scripts/clean_ddinter_dataset.py — Clean and combine the 8 raw DDInter 2.0
category CSVs (data/datasets/ddinter/ddinter_downloads_code_*.csv) into one
ready-to-ingest dataset, the same role data_preprocessing.py's
load_and_clean_data() plays for the openFDA corpus (see that file's
docstring) — load, normalize, deduplicate, print before/after shape and
null counts, save.

This script only produces data/datasets/ddinter/ddinter_cleaned.csv. It
does NOT write to clinical_rules or touch the live database — ingesting
the cleaned file is a separate, later decision (services/clinical_rules.py
already has ingest_pairs_csv() for that; a DDInter-shaped variant would
reuse the same DRAFT-only, never-auto-approved contract).

Run:
    python scripts/clean_ddinter_dataset.py

Judgment calls made here (no one was available to ask — flagged for
review, not silently baked in):

1. Deduplication: the same interaction pair is listed once per drug's own
   category file, so ~28% of raw rows are exact duplicates across files.
   Verified before deduping that no pair has conflicting Level values
   across its duplicate rows (0 conflicts found) — safe to keep the first
   occurrence and drop the rest, not a "pick the worse one" situation.
2. Severity mapping: DDInter's 4 levels (Major/Moderate/Minor/Unknown) are
   mapped to this project's Severity enum as major/caution/informational/
   unknown. Nothing maps to CRITICAL — DDInter has no equivalent tier, and
   per the architecture doc's own rule, nothing from bulk ingestion should
   be trusted at any severity without clinical review regardless (these
   rows are for the same DRAFT-until-approved path the existing 1,824
   rules already use).
3. No mechanism/description text exists in this bulk export (unlike
   fully_processed_dataset.csv's Cleaned_Description). A clearly-labeled
   synthesized placeholder sentence is generated instead — never
   presented as if it were real prescribing text.
4. Naming crosswalk for the 8 originally-curated drugs: DDInter uses INN
   names, so "aspirin" and "penicillin" don't literally appear (see
   session history — this was the original gap that motivated pulling
   DDInter at all). A small, hand-verified alias map adds the common name
   as an extra queryable pair_key alongside the original DDInter name for
   ONLY these 8 drugs — nothing broader/automatic, to avoid silently
   merging distinct drugs. One deliberately conservative choice:
   "benzylpenicillin" (Penicillin G) is aliased to "penicillin";
   "phenoxymethylpenicillin" (Penicillin V) is left unaliased rather than
   folded into the same label, since merging two distinct penicillin
   forms under one interaction profile would be a real clinical-accuracy
   risk, not just a naming convenience. Revisit if you want both to count
   as "penicillin".
"""

import glob
import re
from pathlib import Path

import pandas as pd

_DDINTER_DIR = Path(__file__).resolve().parent.parent / "data" / "datasets" / "ddinter"
_OUT_PATH = _DDINTER_DIR / "ddinter_cleaned.csv"
_COVERAGE_OUT_PATH = _DDINTER_DIR / "ddinter_curated_drug_coverage.csv"

# DDInter Level -> this project's enums.Severity value.
_LEVEL_TO_SEVERITY = {
    "Major": "major",
    "Moderate": "caution",
    "Minor": "informational",
    "Unknown": "unknown",
}

# Hand-verified common-name aliases for the 8 drugs this project already
# curates evidence/rules for (see judgment call #4 above). Keys are the
# DDInter name exactly as it appears in the raw files, lowercased.
_CURATED_ALIASES = {
    "acetylsalicylic acid": "aspirin",
    "benzylpenicillin": "penicillin",
}

CURATED_DRUGS = [
    "warfarin", "aspirin", "ibuprofen", "amoxicillin",
    "penicillin", "lisinopril", "metformin", "acetaminophen",
]

_WHITESPACE_RE = re.compile(r"\s+")


def _norm(name: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(name).strip()).lower()


def _pair_key(a: str, b: str) -> str:
    """Identical convention to services/clinical_rules.py's _pair_key()."""
    left, right = sorted([a, b])
    return f"{left}||{right}"


def load_raw() -> pd.DataFrame:
    files = sorted(glob.glob(str(_DDINTER_DIR / "ddinter_downloads_code_*.csv")))
    if not files:
        raise FileNotFoundError(f"No ddinter_downloads_code_*.csv files found in {_DDINTER_DIR}")
    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(files)} category files — raw combined shape: {df.shape}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    print(f"Nulls per column before cleaning:\n{df.isna().sum()}\n")

    df = df.copy()
    df["drug_a_norm"] = df["Drug_A"].map(_norm)
    df["drug_b_norm"] = df["Drug_B"].map(_norm)

    self_pairs = (df["drug_a_norm"] == df["drug_b_norm"]).sum()
    df = df[df["drug_a_norm"] != df["drug_b_norm"]].reset_index(drop=True)
    print(f"Dropped {self_pairs} self-pair rows (Drug_A == Drug_B).")

    df["pair_key"] = [
        _pair_key(a, b) for a, b in zip(df["drug_a_norm"], df["drug_b_norm"])
    ]

    before = len(df)
    df = df.drop_duplicates(subset=["pair_key", "Level"]).reset_index(drop=True)
    print(f"Dropped {before - len(df)} exact duplicate pair+level rows "
          f"(same interaction listed under both drugs' category files).")

    conflict_counts = df.groupby("pair_key")["Level"].nunique()
    conflicting_keys = conflict_counts[conflict_counts > 1]
    if len(conflicting_keys):
        print(f"WARNING: {len(conflicting_keys)} pair_keys still have "
              f"conflicting Level values after dedup — not auto-resolved, "
              f"left as separate rows for manual review.")
    else:
        print("No pair_keys have conflicting Level values — dedup was safe.")

    df["severity"] = df["Level"].map(_LEVEL_TO_SEVERITY)
    unmapped = df["severity"].isna().sum()
    if unmapped:
        print(f"WARNING: {unmapped} rows had an unrecognized Level value — dropping them.")
        df = df.dropna(subset=["severity"]).reset_index(drop=True)

    df["Cleaned_Description"] = (
        "[synthesized, not source text] " + df["Drug_A"] + " and " + df["Drug_B"]
        + " have a " + df["Level"].str.lower() + "-severity interaction per DDInter "
        + "(no mechanism description available in this bulk export)."
    )

    alias_count = 0
    for ddinter_name, common_name in _CURATED_ALIASES.items():
        mask_a = df["drug_a_norm"] == ddinter_name
        mask_b = df["drug_b_norm"] == ddinter_name
        alias_count += mask_a.sum() + mask_b.sum()
        df.loc[mask_a, "drug_a_common_alias"] = common_name
        df.loc[mask_b, "drug_b_common_alias"] = common_name
    print(f"Applied curated-drug common-name alias to {alias_count} name occurrences "
          f"({list(_CURATED_ALIASES.items())}).")

    # .where(notna, fallback) rather than `alias or norm` — NaN is truthy in
    # Python, so `alias or norm` would silently pick NaN over the fallback.
    drug_a_for_key = df["drug_a_common_alias"].where(df["drug_a_common_alias"].notna(), df["drug_a_norm"])
    drug_b_for_key = df["drug_b_common_alias"].where(df["drug_b_common_alias"].notna(), df["drug_b_norm"])
    df["alias_pair_key"] = [
        _pair_key(a, b) for a, b in zip(drug_a_for_key, drug_b_for_key)
    ]

    out = df.rename(columns={
        "Drug_A": "drug_a", "Drug_B": "drug_b", "Level": "severity_level_raw",
        "DDInterID_A": "ddinter_id_a", "DDInterID_B": "ddinter_id_b",
    })[[
        "drug_a", "drug_b", "drug_a_norm", "drug_b_norm", "pair_key",
        "drug_a_common_alias", "drug_b_common_alias", "alias_pair_key",
        "severity_level_raw", "severity", "Cleaned_Description",
        "ddinter_id_a", "ddinter_id_b",
    ]]

    print(f"\nClean dataset — final shape: {out.shape}")
    print(f"Remaining nulls:\n{out.isna().sum()[out.isna().sum() > 0]}")
    print(f"\nSeverity distribution:\n{out['severity'].value_counts()}")
    return out


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """Confirm the original 'no blanks' goal: every one of the 8 curated
    drugs now resolves to real rows, matching on either its own name or
    its alias_pair_key."""
    rows = []
    for drug in CURATED_DRUGS:
        mask = (
            (df["drug_a_norm"] == drug) | (df["drug_b_norm"] == drug)
            | (df["drug_a_common_alias"] == drug) | (df["drug_b_common_alias"] == drug)
        )
        subset = df[mask]
        rows.append({
            "drug": drug,
            "total_pairs": len(subset),
            "major": (subset["severity"] == "major").sum(),
            "caution": (subset["severity"] == "caution").sum(),
            "informational": (subset["severity"] == "informational").sum(),
            "unknown": (subset["severity"] == "unknown").sum(),
        })
    report = pd.DataFrame(rows)
    print(f"\nCoverage of the 8 originally-curated drugs:\n{report.to_string(index=False)}")
    return report


if __name__ == "__main__":
    raw = load_raw()
    cleaned = clean(raw)
    cleaned.to_csv(_OUT_PATH, index=False)
    print(f"\nWrote {_OUT_PATH} ({len(cleaned)} rows).")

    report = coverage_report(cleaned)
    report.to_csv(_COVERAGE_OUT_PATH, index=False)
    print(f"Wrote {_COVERAGE_OUT_PATH}.")

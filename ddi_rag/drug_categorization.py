"""
drug_categorization.py — Drug-name → route and product-type mapping.

Drug lists are loaded from data/drug_lists/drug_routes.csv at import time,
not hardcoded in source. To add or update drugs, edit the CSV file.

Public API:
    lookup_route(drug_name)   -> (route: str | None, method: str)
    categorize_drug(name)     -> category: str | None
    apply_route_column(df)    -> df with openfda_route filled
    apply_product_type(df)    -> df with openfda_product_type filled
"""

import re
import csv
import logging
from pathlib import Path

import pandas as pd
from difflib import get_close_matches
from config import FUZZY_CUTOFF, MIN_ROOT_LEN

log = logging.getLogger("ddi.categorization")

# ── Load route map from CSV ───────────────────────────────────────────────────

_CSV_PATH = Path(__file__).parent.parent / "data" / "drug_lists" / "drug_routes.csv"

def _load_route_map() -> dict:
    if not _CSV_PATH.exists():
        log.warning("drug_routes.csv not found at %s — route lookup disabled.", _CSV_PATH)
        return {}
    route_map = {}
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["drug_name"].strip().lower()
            if name:
                route_map[name] = row["route"].strip()
    log.info("Loaded %d drug routes from %s", len(route_map), _CSV_PATH)
    return route_map

route_map: dict = _load_route_map()

# ── Salt-suffix normalization ─────────────────────────────────────────────────
_SALT_SUFFIXES = [
    r"\bhydrochloride\b", r"\bhcl\b", r"\bsulfate\b", r"\bsodium\b",
    r"\bpotassium\b", r"\bcalcium\b", r"\bacetate\b", r"\bmaleate\b",
    r"\bfumarate\b", r"\bsuccinate\b", r"\bbesylate\b", r"\btartrate\b",
    r"\bmesylate\b", r"\bphosphate\b", r"\bgluconate\b", r"\bbromide\b",
    r"\bbitartrate\b", r"\bmedoxomil\b", r"\bmagnesium\b", r"\bmonobasic\b",
    r"\bdibasic\b", r"\bsaccharate\b", r"\baspartate\b",
]


def _normalize(name: str) -> str:
    if pd.isna(name):
        return ""
    name = str(name).lower().strip()
    for p in _SALT_SUFFIXES:
        name = re.sub(p, "", name)
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


# Pre-build normalized reference
_normalized_ref: dict = {}
for _drug, _route in route_map.items():
    _nk = _normalize(_drug)
    if _nk not in _normalized_ref:
        _normalized_ref[_nk] = _route

_ref_keys = list(_normalized_ref.keys())


def lookup_route(drug_name) -> tuple:
    """
    Try 4 layers to map a drug name to a route of administration.

    Returns:
        (route: str | None, method: str)
    """
    if pd.isna(drug_name) or str(drug_name).strip() == "":
        return None, "empty"

    raw = str(drug_name).lower().strip()

    # Layer 1 — Exact match
    if raw in route_map:
        return route_map[raw], "exact"

    # Layer 2 — Normalized match (removes salt suffixes)
    norm = _normalize(raw)
    if norm in _normalized_ref:
        return _normalized_ref[norm], "normalized"

    # Layer 3 — First-word (root) match
    words = norm.split()
    root  = words[0] if words else ""
    if len(root) >= MIN_ROOT_LEN:
        candidates = [
            (rk, r) for rk, r in _normalized_ref.items()
            if rk.split() and rk.split()[0] == root
        ]
        if len(candidates) == 1:
            return candidates[0][1], "root_match"
        elif len(candidates) > 1:
            routes = list(set(r for _, r in candidates))
            if len(routes) == 1:
                return routes[0], "root_match_safe"
            return "needs_review", f"ambiguous_root:{root}"

    # Layer 4 — Fuzzy fallback
    matches = get_close_matches(norm, _ref_keys, n=1, cutoff=FUZZY_CUTOFF)
    if matches:
        return _normalized_ref[matches[0]], "fuzzy"

    return "needs_review", "unmatched"


def apply_route_column(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing openfda_route values using lookup_route()."""
    if "openfda_route" not in df.columns:
        df["openfda_route"] = None

    mask = df["openfda_route"].isna()
    results = df.loc[mask, "final_generic_name"].apply(
        lambda x: lookup_route(x)[0]
    )
    df.loc[mask, "openfda_route"] = results
    log.info(
        "Route fill: %d rows processed. Remaining NaN: %d",
        mask.sum(), df["openfda_route"].isna().sum()
    )
    return df


# ── Product-type categorisation ───────────────────────────────────────────────
cellular_therapy: set = {
    "tisagenlecleucel", "lisocabtagene maraleucel", "idecabtagene vicleucel",
    "ciltacabtagene autoleucel", "afamitresgene autoleucel",
    "betibeglogene autotemcel", "atidarsagene autotemcel",
    "elivaldogene autotemcel", "lovotibeglogene autotemcel",
    "onasemnogene abeparvovec-xioi", "onasemnogene abeparvovec-brve",
    "delandistrogene moxeparvovec-rokl", "valoctocogene roxaparvovec-rvox",
    "exagamglogene autotemcel",
}

human_otc_drugs: set = {
    "acetaminophen", "ibuprofen", "naproxen", "naproxen sodium", "aspirin",
    "cetirizine", "loratadine", "fexofenadine", "diphenhydramine hydrochloride",
    "famotidine", "omeprazole", "esomeprazole magnesium", "lansoprazole",
    "loperamide", "docusate", "senna", "melatonin",
}

_all_drugs = set(route_map.keys())
human_prescription_drugs: set = _all_drugs - cellular_therapy - human_otc_drugs

_cat_map = (
    {d: "cellular_therapy"          for d in cellular_therapy}
    | {d: "human_otc_drug"          for d in human_otc_drugs}
    | {d: "human_prescription_drug" for d in human_prescription_drugs}
)


def categorize_drug(drug_name) -> str | None:
    """Classify a drug into: cellular_therapy, human_otc_drug, human_prescription_drug, or None."""
    if pd.isna(drug_name):
        return None
    name = str(drug_name).strip().lower()
    if name in _cat_map:
        return _cat_map[name]
    close = get_close_matches(name, _cat_map.keys(), n=1, cutoff=0.85)
    return _cat_map[close[0]] if close else None


def apply_product_type(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing openfda_product_type values using categorize_drug()."""
    if "openfda_product_type" in df.columns:
        df["openfda_product_type"] = df["openfda_product_type"].str.replace(
            " ", "_", regex=False
        )

    mask = df["openfda_product_type"].isna()
    df.loc[mask, "openfda_product_type"] = (
        df.loc[mask, "final_generic_name"]
        .apply(lambda x: categorize_drug(x) if pd.notna(x) else "no data from<fda>")
        .fillna("no data from<fda>")
    )
    return df

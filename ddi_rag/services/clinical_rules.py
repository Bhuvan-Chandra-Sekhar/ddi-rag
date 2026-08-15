"""
services/clinical_rules.py — Deterministic clinical safety engine
(architecture doc, section 5 + roadmap Phase 3).

No LLM is involved anywhere in this module. Every function here is a pure,
testable, reproducible mapping from inputs to structured findings shaped
like the doc's Finding contract (section 5.2): type, severity,
clinical_effect, recommended_action, evidence_refs, patient_factors,
missing_factors, review_status.

Severity policy:
    - DDI pair findings only carry a clinically meaningful severity once a
      qualified reviewer has moved the backing ClinicalRule from DRAFT to
      APPROVED (see ingest_pairs_csv / RuleStatus). A DRAFT rule still
      produces a finding — type UNKNOWN, review_status PENDING — because an
      unreviewed match is exactly the "missing/conflicting evidence"
      condition the doc says must never be labeled safe.
    - Duplicate-ingredient and drug-allergy matches are structural (set
      membership, not a mined severity claim), so they get a fixed
      conservative severity by rule class. This document intentionally does
      not invent DDI-specific severity thresholds — that requires clinical
      governance sign-off (section 13.1).
"""

import csv
import logging
from typing import Dict, List, Optional, Sequence

from enums import FindingType, ReviewStatus, RuleStatus, Severity
from models import ClinicalRule

log = logging.getLogger("ddi.clinical_rules")

RULE_VERSION = "v1-draft-unreviewed"


def _pair_key(a: str, b: str) -> str:
    left, right = sorted([a.strip().lower(), b.strip().lower()])
    return f"{left}||{right}"


def _unique_unordered_pairs(names: Sequence[str]):
    normalized = sorted({n.strip().lower() for n in names if n and n.strip()})
    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            yield normalized[i], normalized[j]


# ── CSV ingestion (candidate rules — never auto-approved) ───────────────────

def ingest_pairs_csv(
    session,
    csv_path: str,
    source_dataset: str = "fully_processed_dataset.csv",
    limit: Optional[int] = None,
) -> Dict[str, int]:
    """
    Load a raw drug-pair dataset into versioned DRAFT ClinicalRule rows.
    Rows are clinically inert until a reviewer approves them — this
    function never sets status=APPROVED. Junk rows ("Unknown_Drug",
    "No_description") are skipped. Existing pair_keys are left untouched
    (re-running ingestion does not duplicate or silently overwrite rules).
    """
    inserted = skipped_junk = skipped_existing = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                break

            drug_a = (row.get("Drug 1") or "").strip()
            drug_b = (row.get("Drug 2") or "").strip()
            description = (row.get("Cleaned_Description") or row.get("Interaction Description") or "").strip()

            if (
                not drug_a or not drug_b
                or drug_a.lower().startswith("unknown_drug")
                or drug_b.lower().startswith("unknown_drug")
                or not description
                or description.lower() in ("no_description", "nodescription")
            ):
                skipped_junk += 1
                continue

            key = _pair_key(drug_a, drug_b)
            if session.query(ClinicalRule).filter_by(pair_key=key).first():
                skipped_existing += 1
                continue

            session.add(ClinicalRule(
                rule_type=FindingType.DDI,
                pair_key=key,
                ingredient_a=drug_a.lower(),
                ingredient_b=drug_b.lower(),
                clinical_effect=description,
                severity=Severity.UNKNOWN,
                source_description=(row.get("Interaction Description") or "").strip(),
                source_dataset=source_dataset,
                status=RuleStatus.DRAFT,
                rule_version=RULE_VERSION,
            ))
            inserted += 1

    session.flush()
    log.info(
        "Ingested %d draft rules from %s (skipped %d junk, %d already present).",
        inserted, source_dataset, skipped_junk, skipped_existing,
    )
    return {"inserted": inserted, "skipped_junk": skipped_junk, "skipped_existing": skipped_existing}


DDINTER_RULE_VERSION = "ddinter-2.0-v1"


def ingest_ddinter_csv(
    session,
    csv_path: str,
    source_dataset: str = "ddinter_2.0",
    flush_every: int = 5000,
    progress_every: int = 20000,
) -> Dict[str, int]:
    """
    Load scripts/clean_ddinter_dataset.py's cleaned output into DRAFT
    ClinicalRule rows. Unlike ingest_pairs_csv(), the real DDInter severity
    is preserved on the row (not hardcoded to UNKNOWN) — but it still has
    no clinical authority until a reviewer moves status to APPROVED;
    evaluate_ddi_pairs() only trusts rule.severity for APPROVED rows, so a
    DRAFT row from this ingestion produces the same type=UNKNOWN,
    review_status=PENDING finding as any other unreviewed rule.

    Existing pair_keys are left untouched — this only fills gaps the
    current clinical_rules table doesn't already cover, never overwrites
    a rule that came from a different source.

    Performance note: this dataset is ~160K rows, so existing pair_keys are
    loaded into an in-memory set ONCE up front rather than queried per row
    (a per-row SELECT round-trip against a remote Supabase connection is
    what made the first attempt at this run for 5+ minutes without
    finishing — the same "per-row DB round trips" cost flagged in the
    project handoff as the real constraint on large ingests, not API cost).
    """
    import csv as csv_module

    existing_keys = {
        row[0] for row in session.query(ClinicalRule.pair_key).all()
    }
    log.info("Loaded %d existing pair_keys for dedup.", len(existing_keys))

    inserted = skipped_existing = skipped_invalid = 0
    seen_in_file: set = set()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        for i, row in enumerate(reader, 1):
            key = (row.get("alias_pair_key") or "").strip()
            drug_a = (row.get("drug_a_common_alias") or row.get("drug_a_norm") or "").strip()
            drug_b = (row.get("drug_b_common_alias") or row.get("drug_b_norm") or "").strip()
            # The CSV's severity column already holds the final mapped value
            # (scripts/clean_ddinter_dataset.py did major/caution/informational/
            # unknown) — look it up directly by Severity's enum *value*, don't
            # re-run it through DDInter's raw Level names.
            try:
                severity = Severity((row.get("severity") or "").strip().lower())
            except ValueError:
                severity = None

            if not key or not drug_a or not drug_b or severity is None:
                skipped_invalid += 1
                continue

            if key in existing_keys or key in seen_in_file:
                skipped_existing += 1
                continue
            seen_in_file.add(key)

            session.add(ClinicalRule(
                rule_type=FindingType.DDI,
                pair_key=key,
                ingredient_a=drug_a,
                ingredient_b=drug_b,
                clinical_effect=row.get("Cleaned_Description", ""),
                severity=severity,
                source_description=f"DDInter Level: {row.get('severity_level_raw', '')}",
                source_dataset=source_dataset,
                status=RuleStatus.DRAFT,
                rule_version=DDINTER_RULE_VERSION,
            ))
            inserted += 1

            if inserted % flush_every == 0:
                session.flush()
            if i % progress_every == 0:
                log.info("Processed %d rows — %d inserted, %d skipped so far.", i, inserted, skipped_existing)

    session.flush()
    log.info(
        "Ingested %d draft rules from %s (skipped %d already present, %d invalid rows).",
        inserted, source_dataset, skipped_existing, skipped_invalid,
    )
    return {"inserted": inserted, "skipped_existing": skipped_existing, "skipped_invalid": skipped_invalid}


# ── Deterministic rule evaluation ────────────────────────────────────────────

def evaluate_duplicate_ingredients(ingredient_names: Sequence[str]) -> List[dict]:
    """Flag when the same active ingredient appears more than once."""
    seen: Dict[str, int] = {}
    for name in ingredient_names:
        key = name.strip().lower()
        if key:
            seen[key] = seen.get(key, 0) + 1

    findings = []
    for ingredient, count in seen.items():
        if count > 1:
            findings.append({
                "type": FindingType.DUPLICATE,
                "severity": Severity.CAUTION,
                "clinical_effect": f"'{ingredient}' appears {count} times across active medications.",
                "recommended_action": "Pharmacist review: confirm duplicate therapy is intentional.",
                "evidence_refs": [{"rule": "duplicate_ingredient", "rule_version": RULE_VERSION}],
                "patient_factors": {"ingredient": ingredient, "occurrence_count": count},
                "missing_factors": [],
                "review_status": ReviewStatus.PENDING,
            })
    return findings


def evaluate_drug_allergy(
    ingredient_names: Sequence[str],
    allergy_names: Sequence[str],
) -> List[dict]:
    """Flag when a prescribed ingredient matches a recorded patient allergy."""
    allergy_set = {a.strip().lower() for a in allergy_names if a and a.strip()}
    findings = []
    for ingredient in ingredient_names:
        key = ingredient.strip().lower()
        if key and key in allergy_set:
            findings.append({
                "type": FindingType.ALLERGY,
                "severity": Severity.CRITICAL,
                "clinical_effect": f"Patient has a recorded allergy to '{key}'.",
                "recommended_action": "Urgent escalation — do not dispense without prescriber confirmation.",
                "evidence_refs": [{"rule": "drug_allergy_match", "rule_version": RULE_VERSION}],
                "patient_factors": {"ingredient": key},
                "missing_factors": [],
                "review_status": ReviewStatus.PENDING,
            })
    return findings


def evaluate_ddi_pairs(session, ingredient_names: Sequence[str]) -> List[dict]:
    """
    Look up every unordered ingredient pair against the ClinicalRule table.
    An APPROVED rule produces a finding carrying its reviewed severity. A
    DRAFT rule still produces a finding (type UNKNOWN, review_status
    PENDING) — an unreviewed match is missing/conflicting evidence, not a
    cleared pair. Pairs with no matching rule produce no finding: absence of
    a finding is not a safety claim.
    """
    findings = []
    for a, b in _unique_unordered_pairs(ingredient_names):
        key = _pair_key(a, b)
        rule = session.query(ClinicalRule).filter_by(pair_key=key).first()
        if rule is None:
            continue

        if rule.status == RuleStatus.APPROVED:
            findings.append({
                "type": FindingType.DDI,
                "severity": rule.severity,
                "clinical_effect": rule.clinical_effect,
                "recommended_action": "Follow hospital-approved action for this severity level.",
                "evidence_refs": [{"rule_id": rule.id, "rule_version": rule.rule_version,
                                    "source_dataset": rule.source_dataset}],
                "patient_factors": {"ingredient_a": a, "ingredient_b": b},
                "missing_factors": [],
                "review_status": ReviewStatus.PENDING,
            })
        elif rule.status == RuleStatus.DRAFT:
            findings.append({
                "type": FindingType.UNKNOWN,
                "severity": Severity.UNKNOWN,
                "clinical_effect": rule.clinical_effect,
                "recommended_action": "Manual review required — candidate interaction not yet clinically approved.",
                "evidence_refs": [{"rule_id": rule.id, "rule_version": rule.rule_version,
                                    "source_dataset": rule.source_dataset, "status": "draft"}],
                "patient_factors": {"ingredient_a": a, "ingredient_b": b},
                "missing_factors": ["clinical_review"],
                "review_status": ReviewStatus.PENDING,
            })
        # REJECTED rules produce no finding.
    return findings


def evaluate_case(
    session,
    ingredient_names: Sequence[str],
    allergy_names: Sequence[str] = (),
) -> List[dict]:
    """Run every deterministic rule class and return the combined finding list."""
    findings: List[dict] = []
    findings.extend(evaluate_duplicate_ingredients(ingredient_names))
    findings.extend(evaluate_drug_allergy(ingredient_names, allergy_names))
    findings.extend(evaluate_ddi_pairs(session, ingredient_names))
    return findings

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
from datetime import datetime, timezone
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

    Batched to a single query regardless of how many ingredients are on
    the medication list — this used to run one `pair_key` lookup per pair
    (a query per pair means a query per C(n,2) combination), which scales
    quadratically with medication count against a table now holding
    161K+ rows. All pair_keys are computed first, then looked up in one
    `IN (...)` query.
    """
    pairs = list(_unique_unordered_pairs(ingredient_names))
    if not pairs:
        return []

    keys = [_pair_key(a, b) for a, b in pairs]
    rules_by_key = {
        rule.pair_key: rule
        for rule in session.query(ClinicalRule).filter(ClinicalRule.pair_key.in_(keys))
    }

    findings = []
    for (a, b), key in zip(pairs, keys):
        rule = rules_by_key.get(key)
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
                # reported_severity mirrors severity here (APPROVED means
                # severity is already authoritative) — present on every DDI
                # finding uniformly so callers can read patient_factors
                # without branching on review status (see DRAFT below).
                "patient_factors": {"ingredient_a": a, "ingredient_b": b, "reported_severity": rule.severity.value},
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
                # The finding's own severity above MUST stay UNKNOWN — no
                # reviewer has confirmed this rule, so it carries no clinical
                # authority (see module docstring). But the source dataset's
                # own severity rating (e.g. DDInter's "major") is real
                # information that was previously discarded here entirely.
                # Carrying it in patient_factors (not as the finding's
                # severity/review_status) lets a caller say "our data
                # suggests X" without ever claiming X is confirmed.
                "patient_factors": {"ingredient_a": a, "ingredient_b": b, "reported_severity": rule.severity.value},
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


def ddi_coverage_report(session, ingredient_names: Sequence[str]) -> dict:
    """
    What the knowledge base actually knows about every unordered pair among
    ingredient_names — independent of evaluate_ddi_pairs()'s finding list,
    which only ever returns rows FOR pairs that already have a matching
    ClinicalRule. "No finding" on its own is ambiguous: it could mean
    "checked, no matching rule exists at all" (a real coverage gap in the
    data) or "checked, a rule exists but review_status doesn't call for a
    finding" — this function makes the first case visible, which
    evaluate_ddi_pairs() structurally cannot represent (a pair with no
    rule never appears in its output at all). This is a NEW function, not
    a change to evaluate_ddi_pairs()/evaluate_case()'s own return shape —
    those stay exactly as they were so nothing that already depends on
    them (5 tests, 3 call sites) has to change.

    A second, separate query from evaluate_ddi_pairs()'s own lookup — kept
    intentionally isolated rather than merged, so this stays a pure
    reporting addition with zero risk to the existing rule-evaluation path.
    """
    pairs = list(_unique_unordered_pairs(ingredient_names))
    if not pairs:
        return {
            "pairs_checked": 0, "pairs_with_rule": 0, "pairs_with_no_rule": 0,
            "pairs_approved": 0, "pairs_unreviewed": 0, "pairs_rejected": 0,
            "unmatched_pairs": [],
        }

    keys = [_pair_key(a, b) for a, b in pairs]
    rules_by_key = {
        rule.pair_key: rule
        for rule in session.query(ClinicalRule).filter(ClinicalRule.pair_key.in_(keys))
    }

    unmatched, approved, unreviewed, rejected = [], 0, 0, 0
    for (a, b), key in zip(pairs, keys):
        rule = rules_by_key.get(key)
        if rule is None:
            unmatched.append({"ingredient_a": a, "ingredient_b": b})
        elif rule.status == RuleStatus.APPROVED:
            approved += 1
        elif rule.status == RuleStatus.DRAFT:
            unreviewed += 1
        elif rule.status == RuleStatus.REJECTED:
            rejected += 1

    return {
        "pairs_checked": len(pairs),
        "pairs_with_rule": len(pairs) - len(unmatched),
        "pairs_with_no_rule": len(unmatched),
        "pairs_approved": approved,
        "pairs_unreviewed": unreviewed,
        "pairs_rejected": rejected,
        "unmatched_pairs": unmatched,
    }


def review_rule(
    session,
    rule_id: str,
    decision: RuleStatus,
    reviewer_user_id: str,
    severity_override: Optional[Severity] = None,
) -> ClinicalRule:
    """
    Promote a DRAFT ClinicalRule to APPROVED or REJECTED — the one action
    that gives a mined/imported rule real clinical authority. This is the
    knowledge-governance workflow that was previously entirely absent:
    RuleStatus.APPROVED was set only in test fixtures anywhere in this
    repo before this function existed; no endpoint or script had ever
    promoted a real rule.

    decision must be APPROVED or REJECTED, never DRAFT (there's no
    legitimate reason to move a rule backward into DRAFT through this
    path). severity_override lets the reviewer adjust the rule's severity
    at approval time (confirm the mined value as-is, or correct it) —
    only meaningful when decision is APPROVED; ignored otherwise since a
    rejected rule's severity is moot.

    Deliberately re-review-able: approving/rejecting an already-decided
    rule just updates reviewer_user_id/reviewed_at again (audit event
    still records every change) rather than refusing — a reviewer finding
    a past decision wrong needs a way to correct it, not a permanent lock.
    """
    if decision not in (RuleStatus.APPROVED, RuleStatus.REJECTED):
        raise ValueError(f"decision must be APPROVED or REJECTED, got {decision}")

    rule = session.get(ClinicalRule, rule_id)
    if not rule:
        raise ValueError(f"no ClinicalRule with id {rule_id}")

    rule.status = decision
    rule.reviewer_user_id = reviewer_user_id
    rule.reviewed_at = datetime.now(timezone.utc)
    if decision == RuleStatus.APPROVED and severity_override is not None:
        rule.severity = severity_override

    session.flush()
    return rule


def pending_rules(session, limit: int = 50, offset: int = 0) -> List[ClinicalRule]:
    """DRAFT rules awaiting review, oldest first — the review queue for the
    knowledge-administration workflow. Oldest-first (not newest) so a
    rule doesn't sit unreviewed indefinitely just because newer ones keep
    arriving ahead of it."""
    return (
        session.query(ClinicalRule)
        .filter(ClinicalRule.status == RuleStatus.DRAFT)
        .order_by(ClinicalRule.created_at)
        .offset(offset).limit(limit)
        .all()
    )

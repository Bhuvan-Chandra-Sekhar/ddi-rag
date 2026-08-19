"""
Phase 3 exit gate: every finding is deterministic, testable, versioned,
cited, and reproducible — no LLM involved in determining a finding.
"""

import csv as csv_module

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from enums import FindingType, ReviewStatus, RuleStatus, Severity
from models import ClinicalRule
from services.clinical_rules import (
    evaluate_case, evaluate_ddi_pairs, evaluate_drug_allergy,
    evaluate_duplicate_ingredients, ingest_pairs_csv,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_duplicate_ingredient_detected():
    findings = evaluate_duplicate_ingredients(["Warfarin", "warfarin", "Aspirin"])
    assert len(findings) == 1
    assert findings[0]["type"] == FindingType.DUPLICATE
    assert findings[0]["patient_factors"]["occurrence_count"] == 2


def test_no_duplicate_when_all_unique():
    assert evaluate_duplicate_ingredients(["Warfarin", "Aspirin"]) == []


def test_drug_allergy_match_is_critical():
    findings = evaluate_drug_allergy(["Penicillin", "Ibuprofen"], allergy_names=["penicillin"])
    assert len(findings) == 1
    assert findings[0]["type"] == FindingType.ALLERGY
    assert findings[0]["severity"] == Severity.CRITICAL


def test_no_allergy_match_produces_no_finding():
    assert evaluate_drug_allergy(["Ibuprofen"], allergy_names=["penicillin"]) == []


def test_ddi_pair_lookup_is_order_independent(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="aspirin||warfarin",
        ingredient_a="aspirin", ingredient_b="warfarin",
        clinical_effect="increases bleeding risk", severity=Severity.MAJOR,
        status=RuleStatus.APPROVED, rule_version="v1",
    ))
    session.flush()

    forward = evaluate_ddi_pairs(session, ["aspirin", "warfarin"])
    backward = evaluate_ddi_pairs(session, ["warfarin", "aspirin"])

    assert len(forward) == 1 == len(backward)
    assert forward[0]["severity"] == backward[0]["severity"] == Severity.MAJOR
    assert forward[0]["patient_factors"]["reported_severity"] == "major"


def test_draft_rule_produces_unknown_pending_finding_not_a_cleared_pair(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugx||drugy",
        ingredient_a="drugx", ingredient_b="drugy",
        clinical_effect="drugx may increase drugy levels", severity=Severity.UNKNOWN,
        status=RuleStatus.DRAFT, rule_version="v1-draft-unreviewed",
    ))
    session.flush()

    findings = evaluate_ddi_pairs(session, ["drugx", "drugy"])

    assert len(findings) == 1
    assert findings[0]["type"] == FindingType.UNKNOWN
    assert findings[0]["review_status"] == ReviewStatus.PENDING
    assert "clinical_review" in findings[0]["missing_factors"]
    # The finding's own severity stays UNKNOWN (no reviewer has confirmed
    # this rule), but the source dataset's real severity rating must still
    # be reachable — otherwise every unreviewed interaction looks identical
    # regardless of how well-documented the underlying data actually is.
    assert findings[0]["severity"] == Severity.UNKNOWN
    assert findings[0]["patient_factors"]["reported_severity"] == "unknown"


def test_draft_finding_dict_constructs_a_real_finding_row(session):
    """reported_severity lives inside patient_factors (a JSON column), not
    as a top-level dict key — this is what makes that safe: professional_workflow.py's
    run_case_analysis() does `Finding(case_id=case.id, **fd)` directly from
    this dict, and Finding has no reported_severity column. A top-level key
    would raise TypeError there; patient_factors already accepts arbitrary
    JSON so this must not."""
    from models import Finding

    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugp||drugq",
        ingredient_a="drugp", ingredient_b="drugq",
        clinical_effect="candidate interaction", severity=Severity.CRITICAL,
        status=RuleStatus.DRAFT, rule_version="v1-draft-unreviewed",
    ))
    session.flush()

    fd = evaluate_ddi_pairs(session, ["drugp", "drugq"])[0]
    finding = Finding(case_id="fake-case-id", **fd)  # must not raise TypeError
    assert finding.patient_factors["reported_severity"] == "critical"
    assert finding.severity == Severity.UNKNOWN


def test_no_matching_rule_produces_no_finding(session):
    assert evaluate_ddi_pairs(session, ["drugq", "drugz"]) == []


def test_rejected_rule_produces_no_finding(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugm||drugn",
        ingredient_a="drugm", ingredient_b="drugn",
        clinical_effect="spurious correlation", severity=Severity.UNKNOWN,
        status=RuleStatus.REJECTED, rule_version="v1",
    ))
    session.flush()
    assert evaluate_ddi_pairs(session, ["drugm", "drugn"]) == []


def test_ingest_pairs_csv_skips_junk_and_never_auto_approves(session, tmp_path):
    csv_path = tmp_path / "pairs.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv_module.writer(f)
        writer.writerow(["Drug 1", "Drug 2", "Interaction Description", "Cleaned_Description"])
        writer.writerow(["Trioxsalen", "Verteporfin", "Trioxsalen may increase photosensitizing.",
                          "trioxsalen may increase photosensitizing"])
        writer.writerow(["Unknown_Drug", "Unknown_Drug", "No_description", "nodescription"])

    stats = ingest_pairs_csv(session, str(csv_path), source_dataset="test.csv")

    assert stats == {"inserted": 1, "skipped_junk": 1, "skipped_existing": 0}
    rule = session.query(ClinicalRule).one()
    assert rule.status == RuleStatus.DRAFT
    assert rule.pair_key == "trioxsalen||verteporfin"

    # Re-ingesting the same file must not duplicate the rule.
    stats2 = ingest_pairs_csv(session, str(csv_path), source_dataset="test.csv")
    assert stats2["inserted"] == 0
    assert stats2["skipped_existing"] == 1
    assert session.query(ClinicalRule).count() == 1


def test_evaluate_case_combines_all_rule_classes(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="aspirin||warfarin",
        ingredient_a="aspirin", ingredient_b="warfarin",
        clinical_effect="increases bleeding risk", severity=Severity.MAJOR,
        status=RuleStatus.APPROVED, rule_version="v1",
    ))
    session.flush()

    findings = evaluate_case(
        session,
        ingredient_names=["aspirin", "warfarin", "aspirin"],
        allergy_names=["warfarin"],
    )
    types = {f["type"] for f in findings}
    assert types == {FindingType.DUPLICATE, FindingType.ALLERGY, FindingType.DDI}

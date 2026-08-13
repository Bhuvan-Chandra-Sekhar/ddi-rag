"""
Clinical regression eval suite (architecture doc section 13 "Clinical
regression" + 13.1 "Safety evaluation rules").

This suite validates that the deterministic rule engine is faithful to its
OWN rule table on a fixed, known gold set — it is a prerequisite for
clinical validation, not a substitute for it. Sensitivity/false-negative
rate are reported separately per severity, never as one aggregate number,
per section 13.1. No pass/fail threshold is asserted here beyond "the
mechanism matches its own known ground truth" — choosing an acceptable
real-world sensitivity threshold is explicitly reserved for clinical
governance sign-off, not this codebase.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from enums import Severity
from models import ClinicalRule
from services.clinical_rules import evaluate_case
from services.eval_metrics import aggregate, score_case

from eval_fixtures.gold_cases import GOLD_CASES


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _run_gold_case(session, case: dict) -> dict:
    for rule in case["seed_rules"]:
        session.add(ClinicalRule(**rule))
    session.flush()
    return evaluate_case(session, case["ingredients"], case["allergies"])


@pytest.mark.parametrize("case", GOLD_CASES, ids=[c["name"] for c in GOLD_CASES])
def test_gold_case_matches_expected_findings(session, case):
    actual = _run_gold_case(session, case)
    metrics = score_case(case["expected_findings"], actual)

    for severity, m in metrics.items():
        assert m.false_negative == 0, (
            f"{case['name']}: missed an expected {severity.value} finding "
            "(false negative) — this must never happen silently."
        )
        assert m.false_positive == 0, (
            f"{case['name']}: produced a finding not in the gold set "
            f"(false positive) for severity {severity.value}."
        )


def test_suite_level_sensitivity_reported_per_severity_not_aggregated(session):
    """Section 13.1: report sensitivity/false-negative rate separately per
    severity — this test proves the metrics module keeps severities apart
    rather than collapsing them into one score."""
    all_metrics = []
    for case in GOLD_CASES:
        s = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=s)
        sess = sessionmaker(bind=s)()
        actual = _run_gold_case(sess, case)
        all_metrics.append(score_case(case["expected_findings"], actual))
        sess.close()

    suite = aggregate(all_metrics)

    # Critical and major findings in the gold set must show up as their own
    # keys with their own sensitivity — not folded into a single number.
    assert Severity.CRITICAL in suite
    assert Severity.MAJOR in suite
    assert suite[Severity.CRITICAL].sensitivity == 1.0
    assert suite[Severity.MAJOR].sensitivity == 1.0
    assert suite[Severity.CRITICAL] is not suite[Severity.MAJOR]


def test_audit_no_finding_case_for_silent_misses(session):
    """Section 13.1: 'Audit samples of cases with no finding to detect
    silent misses.' The true-negative gold case must produce zero findings
    — not because nothing ran, but because nothing matched."""
    case = next(c for c in GOLD_CASES if c["name"] == "true_negative_safe_combination")
    actual = _run_gold_case(session, case)
    assert actual == []

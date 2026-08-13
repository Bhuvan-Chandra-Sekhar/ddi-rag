"""
services/eval_metrics.py — Clinical regression evaluation metrics
(architecture doc section 13.1).

Per the doc: report sensitivity and false-negative rate SEPARATELY per
severity for critical/major findings — aggregate accuracy is explicitly
called out as insufficient, and must not be used as a stand-in. This
module computes metrics only; it does not choose pass/fail thresholds —
that is reserved for clinical governance sign-off (section 13.1: "Release
thresholds must be selected and signed off by qualified clinical
leadership; this document intentionally does not invent them.").
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from enums import Severity


def _finding_key(finding: dict) -> Tuple:
    """Identity used to match a gold-expected finding to an actual one —
    by rule type + the ingredient(s) it concerns, not by wording."""
    factors = finding.get("patient_factors") or {}
    if "ingredient_a" in factors and "ingredient_b" in factors:
        pair = tuple(sorted([factors["ingredient_a"], factors["ingredient_b"]]))
        return (finding["type"], pair)
    if "ingredient" in factors:
        return (finding["type"], factors["ingredient"])
    return (finding["type"], None)


@dataclass
class SeverityMetrics:
    true_positive: int = 0
    false_negative: int = 0
    false_positive: int = 0

    @property
    def sensitivity(self) -> float:
        total = self.true_positive + self.false_negative
        return self.true_positive / total if total else float("nan")

    @property
    def false_negative_rate(self) -> float:
        total = self.true_positive + self.false_negative
        return self.false_negative / total if total else float("nan")

    @property
    def positive_predictive_value(self) -> float:
        total = self.true_positive + self.false_positive
        return self.true_positive / total if total else float("nan")


def score_case(expected_findings: List[dict], actual_findings: List[dict]) -> Dict[Severity, SeverityMetrics]:
    """Compare one gold case's expected findings against the rule engine's
    actual findings, per severity."""
    expected_by_key = {_finding_key(f): f for f in expected_findings}
    actual_by_key = {_finding_key(f): f for f in actual_findings}

    metrics: Dict[Severity, SeverityMetrics] = {}

    def _get(sev):
        return metrics.setdefault(sev, SeverityMetrics())

    for key, exp in expected_by_key.items():
        m = _get(exp["severity"])
        if key in actual_by_key:
            m.true_positive += 1
        else:
            m.false_negative += 1

    for key, act in actual_by_key.items():
        if key not in expected_by_key:
            _get(act["severity"]).false_positive += 1

    return metrics


def aggregate(case_metrics: List[Dict[Severity, SeverityMetrics]]) -> Dict[Severity, SeverityMetrics]:
    """Sum per-case metrics into suite-level metrics, one entry per severity."""
    total: Dict[Severity, SeverityMetrics] = {}
    for case in case_metrics:
        for sev, m in case.items():
            agg = total.setdefault(sev, SeverityMetrics())
            agg.true_positive += m.true_positive
            agg.false_negative += m.false_negative
            agg.false_positive += m.false_positive
    return total

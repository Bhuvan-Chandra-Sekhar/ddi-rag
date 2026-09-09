"""
Tests for the three gaps found in a product-architecture review and fixed
in the same change:

    1. Role enforcement — organization membership alone used to be the
       entire authorization check on every clinical-workflow route
       (app.py, routes_clinical.py); a `patient`-role account could call
       pharmacist/prescriber-only actions. Now authz.py's
       authorized_case()/require_role() gate every action by role too.
    2. DDI coverage reporting — evaluate_ddi_pairs()/evaluate_case() only
       ever returned findings for pairs that already had a matching rule;
       a pair with NO rule at all was structurally invisible. New
       ddi_coverage_report() (services/clinical_rules.py) surfaces it.
    3. Rule-governance workflow — RuleStatus.APPROVED was previously set
       only in test fixtures anywhere in this repo; no code path had ever
       promoted a real rule. New review_rule()/pending_rules() plus the
       /v1/clinical-rules/* routes are the first real path.

Scenarios below were written from what each feature is SUPPOSED to do,
before re-reading the implementation, specifically so this doesn't just
restate the code back to itself.
"""

import uuid

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import flask_app
from database import Base, get_session, init_db
from enums import (
    FindingType, PrescriptionStatus, ReviewStatus, RuleStatus,
    SafetyCaseState, Severity, UserRole,
)
from models import (
    ClinicalProfileSnapshot, ClinicalRule, Finding, Medication, Organization,
    Patient, Prescription, User,
)
from services.clinical_rules import (
    ddi_coverage_report, evaluate_ddi_pairs, pending_rules, review_rule,
)
from services.safety_case import create_case, transition_case


# ── Coverage report — service layer ─────────────────────────────────────────

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


def test_pair_with_no_rule_at_all_is_reported_as_a_coverage_gap(session):
    report = ddi_coverage_report(session, ["drugx", "drugy"])
    assert report["pairs_checked"] == 1
    assert report["pairs_with_no_rule"] == 1
    assert report["pairs_with_rule"] == 0
    assert report["unmatched_pairs"] == [{"ingredient_a": "drugx", "ingredient_b": "drugy"}]


def test_pair_with_approved_rule_counts_as_approved_not_unmatched(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="aspirin||warfarin",
        ingredient_a="aspirin", ingredient_b="warfarin",
        severity=Severity.MAJOR, status=RuleStatus.APPROVED, rule_version="v1",
    ))
    session.flush()
    report = ddi_coverage_report(session, ["aspirin", "warfarin"])
    assert report["pairs_approved"] == 1
    assert report["pairs_with_no_rule"] == 0
    assert report["unmatched_pairs"] == []


def test_pair_with_draft_rule_counts_as_unreviewed(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="ibuprofen||lithium",
        ingredient_a="ibuprofen", ingredient_b="lithium",
        severity=Severity.CAUTION, status=RuleStatus.DRAFT, rule_version="v1",
    ))
    session.flush()
    report = ddi_coverage_report(session, ["ibuprofen", "lithium"])
    assert report["pairs_unreviewed"] == 1
    assert report["pairs_with_no_rule"] == 0


def test_rejected_rule_counts_as_having_a_rule_but_not_approved_or_unreviewed(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugp||drugq",
        ingredient_a="drugp", ingredient_b="drugq",
        severity=Severity.UNKNOWN, status=RuleStatus.REJECTED, rule_version="v1",
    ))
    session.flush()
    report = ddi_coverage_report(session, ["drugp", "drugq"])
    assert report["pairs_with_rule"] == 1
    assert report["pairs_approved"] == 0
    assert report["pairs_unreviewed"] == 0
    assert report["pairs_with_no_rule"] == 0


def test_mixed_three_drug_case_buckets_each_pair_correctly(session):
    # A-B: no rule. A-C: approved. B-C: draft.
    session.add_all([
        ClinicalRule(rule_type=FindingType.DDI, pair_key="druga||drugc",
                      ingredient_a="druga", ingredient_b="drugc",
                      severity=Severity.MAJOR, status=RuleStatus.APPROVED, rule_version="v1"),
        ClinicalRule(rule_type=FindingType.DDI, pair_key="drugb||drugc",
                      ingredient_a="drugb", ingredient_b="drugc",
                      severity=Severity.CAUTION, status=RuleStatus.DRAFT, rule_version="v1"),
    ])
    session.flush()
    report = ddi_coverage_report(session, ["druga", "drugb", "drugc"])
    assert report["pairs_checked"] == 3
    assert report["pairs_approved"] == 1
    assert report["pairs_unreviewed"] == 1
    assert report["pairs_with_no_rule"] == 1
    assert report["unmatched_pairs"] == [{"ingredient_a": "druga", "ingredient_b": "drugb"}]


def test_single_ingredient_has_no_pairs_and_does_not_raise(session):
    report = ddi_coverage_report(session, ["onlyonedrug"])
    assert report == {
        "pairs_checked": 0, "pairs_with_rule": 0, "pairs_with_no_rule": 0,
        "pairs_approved": 0, "pairs_unreviewed": 0, "pairs_rejected": 0,
        "unmatched_pairs": [],
    }


def test_empty_ingredient_list_does_not_raise(session):
    report = ddi_coverage_report(session, [])
    assert report["pairs_checked"] == 0


def test_same_pair_different_case_and_order_counts_once(session):
    session.add(ClinicalRule(
        rule_type=FindingType.DDI, pair_key="aspirin||warfarin",
        ingredient_a="aspirin", ingredient_b="warfarin",
        severity=Severity.MAJOR, status=RuleStatus.APPROVED, rule_version="v1",
    ))
    session.flush()
    report = ddi_coverage_report(session, ["Warfarin", "ASPIRIN"])
    assert report["pairs_checked"] == 1
    assert report["pairs_approved"] == 1


# ── Rule review workflow — service layer ────────────────────────────────────

@pytest.fixture
def draft_rule(session):
    rule = ClinicalRule(
        rule_type=FindingType.DDI, pair_key="drugm||drugn",
        ingredient_a="drugm", ingredient_b="drugn",
        clinical_effect="candidate interaction", severity=Severity.CAUTION,
        status=RuleStatus.DRAFT, rule_version="v1", source_dataset="test",
    )
    session.add(rule)
    session.flush()
    return rule


def test_approving_a_draft_rule_sets_status_reviewer_and_timestamp(session, draft_rule):
    reviewer_id = str(uuid.uuid4())
    reviewed = review_rule(session, draft_rule.id, RuleStatus.APPROVED, reviewer_user_id=reviewer_id)
    assert reviewed.status == RuleStatus.APPROVED
    assert reviewed.reviewer_user_id == reviewer_id
    assert reviewed.reviewed_at is not None


def test_severity_override_actually_changes_severity_on_approve(session, draft_rule):
    assert draft_rule.severity == Severity.CAUTION
    reviewed = review_rule(
        session, draft_rule.id, RuleStatus.APPROVED,
        reviewer_user_id="rev1", severity_override=Severity.CRITICAL,
    )
    assert reviewed.severity == Severity.CRITICAL


def test_approving_without_override_preserves_the_mined_severity(session, draft_rule):
    reviewed = review_rule(session, draft_rule.id, RuleStatus.APPROVED, reviewer_user_id="rev1")
    assert reviewed.severity == Severity.CAUTION  # unchanged from the fixture's original value


def test_rejecting_ignores_any_severity_override_passed_alongside(session, draft_rule):
    reviewed = review_rule(
        session, draft_rule.id, RuleStatus.REJECTED,
        reviewer_user_id="rev1", severity_override=Severity.CRITICAL,
    )
    assert reviewed.status == RuleStatus.REJECTED
    # A rejected rule's severity is moot — override must be ignored, not applied.
    assert reviewed.severity == Severity.CAUTION


def test_decision_cannot_be_draft(session, draft_rule):
    with pytest.raises(ValueError):
        review_rule(session, draft_rule.id, RuleStatus.DRAFT, reviewer_user_id="rev1")


def test_reviewing_a_nonexistent_rule_raises(session):
    with pytest.raises(ValueError):
        review_rule(session, str(uuid.uuid4()), RuleStatus.APPROVED, reviewer_user_id="rev1")


def test_a_rule_can_be_re_reviewed_and_the_decision_corrected(session, draft_rule):
    review_rule(session, draft_rule.id, RuleStatus.APPROVED, reviewer_user_id="rev1")
    corrected = review_rule(session, draft_rule.id, RuleStatus.REJECTED, reviewer_user_id="rev2")
    assert corrected.status == RuleStatus.REJECTED
    assert corrected.reviewer_user_id == "rev2"


def test_approved_rule_is_immediately_visible_to_evaluate_ddi_pairs_in_the_same_session(session, draft_rule):
    # Real integration, not just isolated state on the ORM object.
    review_rule(
        session, draft_rule.id, RuleStatus.APPROVED,
        reviewer_user_id="rev1", severity_override=Severity.CRITICAL,
    )
    findings = evaluate_ddi_pairs(session, ["drugm", "drugn"])
    assert len(findings) == 1
    assert findings[0]["type"] == FindingType.DDI
    assert findings[0]["severity"] == Severity.CRITICAL


def test_pending_rules_excludes_a_rule_the_moment_it_is_reviewed(session, draft_rule):
    assert draft_rule.id in {r.id for r in pending_rules(session)}
    review_rule(session, draft_rule.id, RuleStatus.APPROVED, reviewer_user_id="rev1")
    assert draft_rule.id not in {r.id for r in pending_rules(session)}


def test_pending_rules_orders_oldest_first_and_paginates(session):
    import time
    ids_in_creation_order = []
    for i in range(3):
        r = ClinicalRule(
            rule_type=FindingType.DDI, pair_key=f"pa{i}||pb{i}",
            ingredient_a=f"pa{i}", ingredient_b=f"pb{i}",
            severity=Severity.UNKNOWN, status=RuleStatus.DRAFT, rule_version="v1",
        )
        session.add(r)
        session.flush()
        ids_in_creation_order.append(r.id)
        time.sleep(0.01)  # created_at has second-ish resolution in some backends

    all_pending = pending_rules(session, limit=50)
    assert [r.id for r in all_pending] == ids_in_creation_order

    page = pending_rules(session, limit=2, offset=1)
    assert [r.id for r in page] == ids_in_creation_order[1:3]


# ── Role enforcement — real HTTP routes via the Flask test client ──────────

def _seed_full_scenario():
    """One org with a pharmacist, a prescriber, a patient-role account, a
    case awaiting pharmacist review, and a DRAFT clinical rule — enough to
    exercise every role-gated route in one place."""
    init_db()
    with get_session() as session:
        org = Organization(name="Authz Test Hospital")
        session.add(org)
        session.flush()

        suffix = uuid.uuid4().hex[:8]
        pharmacist = User(organization_id=org.id, email=f"authz-pharm-{suffix}@example.com",
                           password_hash="x", role=UserRole.PHARMACIST)
        prescriber = User(organization_id=org.id, email=f"authz-doc-{suffix}@example.com",
                           password_hash="x", role=UserRole.PRESCRIBER)
        patient_account = User(organization_id=org.id, email=f"authz-patient-{suffix}@example.com",
                                password_hash="x", role=UserRole.PATIENT)
        safety_officer = User(organization_id=org.id, email=f"authz-so-{suffix}@example.com",
                               password_hash="x", role=UserRole.SAFETY_OFFICER)
        session.add_all([pharmacist, prescriber, patient_account, safety_officer])
        session.flush()

        patient = Patient(organization_id=org.id, first_name="Authz", last_name="Test")
        medication = Medication(display_name="authz-test-drug")
        session.add_all([patient, medication])
        session.flush()
        # Link patient_account to this Patient row so /v1/my/cases has
        # something real to find for the "patient can see their own
        # cases" scenario.
        patient.user_id = patient_account.id

        prescription = Prescription(
            organization_id=org.id, patient_id=patient.id, prescriber_id=prescriber.id,
            medication_id=medication.id, status=PrescriptionStatus.ACTIVE,
        )
        snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
        session.add_all([prescription, snapshot])
        session.flush()

        case = create_case(session, org.id, prescription, snapshot)
        transition_case(session, case, SafetyCaseState.AWAITING_ANALYSIS)
        finding = Finding(
            case_id=case.id, type=FindingType.DDI, severity=Severity.MAJOR,
            clinical_effect="authz test interaction", review_status=ReviewStatus.PENDING,
        )
        session.add(finding)
        session.flush()
        transition_case(session, case, SafetyCaseState.AWAITING_PHARMACIST_REVIEW)

        rule = ClinicalRule(
            rule_type=FindingType.DDI, pair_key="authzdrugp||authzdrugq",
            ingredient_a="authzdrugp", ingredient_b="authzdrugq",
            severity=Severity.CAUTION, status=RuleStatus.DRAFT, rule_version="v1",
        )
        session.add(rule)
        session.flush()

        ids = {
            "org_id": org.id, "pharmacist_id": pharmacist.id, "prescriber_id": prescriber.id,
            "patient_user_id": patient_account.id, "safety_officer_id": safety_officer.id,
            "case_id": case.id, "finding_id": finding.id, "rule_id": rule.id,
        }

    with flask_app.app_context():
        tokens = {
            f"{name}_token": create_access_token(identity=ids[f"{name}_id" if name != "patient" else "patient_user_id"])
            for name in ("pharmacist", "prescriber", "patient", "safety_officer")
        }
    return {**ids, **tokens}


def test_patient_cannot_assess_findings_even_in_their_own_org():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/safety-cases/{ids['case_id']}/findings/assess",
        json={"decisions": {ids["finding_id"]: "accepted"}},
        headers={"Authorization": f"Bearer {ids['patient_token']}"},
    )
    assert resp.status_code == 403


def test_patient_cannot_dispense():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/safety-cases/{ids['case_id']}/dispense",
        json={"status": "dispensed"},
        headers={"Authorization": f"Bearer {ids['patient_token']}"},
    )
    assert resp.status_code == 403


def test_prescriber_cannot_dispense():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/safety-cases/{ids['case_id']}/dispense",
        json={"status": "dispensed"},
        headers={"Authorization": f"Bearer {ids['prescriber_token']}"},
    )
    assert resp.status_code == 403


def test_pharmacist_cannot_respond_to_a_prescriber_intervention():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    pharm_auth = {"Authorization": f"Bearer {ids['pharmacist_token']}"}

    create_resp = client.post(
        "/v1/interventions",
        json={"case_id": ids["case_id"], "target_prescriber_id": ids["prescriber_id"],
              "finding_id": ids["finding_id"], "urgency": "major",
              "question_or_recommendation": "Continue or hold?"},
        headers=pharm_auth,
    )
    assert create_resp.status_code == 201
    intervention_id = create_resp.get_json()["intervention_id"]

    resp = client.post(
        f"/v1/interventions/{intervention_id}/response",
        json={"decision": "stop"},
        headers=pharm_auth,  # pharmacist trying to answer their own intervention
    )
    assert resp.status_code == 403


def test_prescriber_can_respond_to_their_own_org_intervention():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    pharm_auth = {"Authorization": f"Bearer {ids['pharmacist_token']}"}
    doc_auth = {"Authorization": f"Bearer {ids['prescriber_token']}"}

    create_resp = client.post(
        "/v1/interventions",
        json={"case_id": ids["case_id"], "target_prescriber_id": ids["prescriber_id"],
              "finding_id": ids["finding_id"], "urgency": "major",
              "question_or_recommendation": "Continue or hold?"},
        headers=pharm_auth,
    )
    intervention_id = create_resp.get_json()["intervention_id"]

    resp = client.post(
        f"/v1/interventions/{intervention_id}/response",
        json={"decision": "stop"},
        headers=doc_auth,
    )
    assert resp.status_code == 200


def test_cross_org_pharmacist_gets_404_not_403_regardless_of_role():
    org_a = _seed_full_scenario()
    org_b = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.get(
        f"/v1/safety-cases/{org_a['case_id']}",
        headers={"Authorization": f"Bearer {org_b['pharmacist_token']}"},
    )
    # Wrong org AND (if role mattered here) a role that would pass —
    # existence must not leak, so this is 404, never 403.
    assert resp.status_code == 404


def test_patient_cannot_see_the_pharmacist_queue():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.get(
        "/v1/safety-cases/queue",
        headers={"Authorization": f"Bearer {ids['patient_token']}"},
    )
    assert resp.status_code == 403


def test_patient_can_see_their_own_cases():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.get(
        "/v1/my/cases",
        headers={"Authorization": f"Bearer {ids['patient_token']}"},
    )
    assert resp.status_code == 200
    assert any(c["case_id"] == ids["case_id"] for c in resp.get_json()["cases"])


def test_pharmacist_cannot_use_the_patient_only_my_cases_route():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.get(
        "/v1/my/cases",
        headers={"Authorization": f"Bearer {ids['pharmacist_token']}"},
    )
    # Role gate must fire before the "no patient record" fallback —
    # a pharmacist has no Patient row either, but the reason must be
    # "wrong role" (403), not "no record" (404).
    assert resp.status_code == 403


def test_safety_officer_can_assess_findings():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/safety-cases/{ids['case_id']}/findings/assess",
        json={"decisions": {ids["finding_id"]: "accepted"}},
        headers={"Authorization": f"Bearer {ids['safety_officer_token']}"},
    )
    assert resp.status_code == 200


def test_prescriber_cannot_review_clinical_rules():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/clinical-rules/{ids['rule_id']}/review",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {ids['prescriber_token']}"},
    )
    assert resp.status_code == 403


def test_pharmacist_can_review_clinical_rules_end_to_end():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    pharm_auth = {"Authorization": f"Bearer {ids['pharmacist_token']}"}

    pending_resp = client.get("/v1/clinical-rules/pending", headers=pharm_auth)
    assert pending_resp.status_code == 200
    assert any(r["id"] == ids["rule_id"] for r in pending_resp.get_json()["rules"])

    review_resp = client.post(
        f"/v1/clinical-rules/{ids['rule_id']}/review",
        json={"decision": "approved", "severity": "critical"},
        headers=pharm_auth,
    )
    assert review_resp.status_code == 200
    body = review_resp.get_json()
    assert body["status"] == "approved"
    assert body["severity"] == "critical"

    # Now excluded from the pending queue.
    pending_after = client.get("/v1/clinical-rules/pending", headers=pharm_auth)
    assert ids["rule_id"] not in {r["id"] for r in pending_after.get_json()["rules"]}


def test_review_endpoint_rejects_an_invalid_decision_value():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.post(
        f"/v1/clinical-rules/{ids['rule_id']}/review",
        json={"decision": "maybe"},
        headers={"Authorization": f"Bearer {ids['pharmacist_token']}"},
    )
    assert resp.status_code == 400


def test_no_token_at_all_gets_401_not_403():
    ids = _seed_full_scenario()
    client = flask_app.test_client()
    resp = client.get(f"/v1/safety-cases/{ids['case_id']}")
    assert resp.status_code == 401

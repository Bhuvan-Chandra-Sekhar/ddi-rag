"""
Runs the REAL Flask app for the Playwright suite, against an isolated,
freshly seeded SQLite database that is deleted and rebuilt on every start.

What is real: routing, JWT issue/verification, authorization, password
hashing, the deterministic rule engine, the database, the built React
bundle served from ddi_rag/static/patient-app.

What is faked, and why: only the calls that would leave the machine --
RxNorm identity lookup, the Cohere/Groq explanation, and the Cohere-backed
FDA label search. A test run must be hermetic and must never spend API
quota or touch the production database.

Safety rails: DATABASE_URL is forced to a throwaway file BEFORE the app is
imported (config.py's .env loading never overrides an existing variable),
and the process refuses to start if the resolved URL is anything else.

The /__e2e__/* routes exist only in this launcher, never in the product.
"""

import json
import os
import re
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = int(os.environ.get("E2E_PORT", "5057"))
DB_PATH = Path(tempfile.gettempdir()) / f"medtrust_e2e_{PORT}.db"

for suffix in ("", "-journal", "-wal", "-shm"):
    Path(f"{DB_PATH}{suffix}").unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "e2e-only-signing-key-never-used-anywhere-else-123456"
os.environ["ALLOWED_ORIGINS"] = f"http://127.0.0.1:{PORT},http://localhost:{PORT}"
os.environ["COHERE_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
for flag in ("KILL_SWITCH_SELF_CHECK", "KILL_SWITCH_EXPLAIN"):
    os.environ[flag] = "false"

sys.path.insert(0, str(ROOT / "ddi_rag"))

from config import DATABASE_URL  # noqa: E402

if not (DATABASE_URL.startswith("sqlite") and f"medtrust_e2e_{PORT}" in DATABASE_URL):
    sys.exit(f"Refusing to start: DATABASE_URL is not the throwaway e2e database ({DATABASE_URL!r}).")

from flask import request  # noqa: E402
from flask_jwt_extended import create_access_token  # noqa: E402

import app as app_module  # noqa: E402
import routes.public as public_routes  # noqa: E402
from core.auth import hash_password, register_user  # noqa: E402
from core.rate_limit import limiter  # noqa: E402
from database import get_session, init_db  # noqa: E402
from enums import (  # noqa: E402
    DeliveryChannel, FindingType, PrescriptionStatus, RuleStatus, SafetyCaseState, Severity, UserRole,
)
from models import (  # noqa: E402
    ClinicalProfileSnapshot, ClinicalRule, Medication, Organization, Patient, Prescription, User,
)
from services.evidence import ExplanationUnavailable  # noqa: E402
from services.professional_workflow import run_case_analysis, send_patient_communication  # noqa: E402
from services.safety_case import create_case, transition_case  # noqa: E402

flask_app = app_module.flask_app
accounts = json.loads((HERE / "test-accounts.json").read_text(encoding="utf-8"))

# Every request in a suite run comes from one address; per-IP throttling
# is covered by the pytest suite and would only make these runs flaky.
limiter.enabled = False

# ── The only fakes: calls that would leave the machine ─────────────────────

KNOWN_DRUGS = {
    "aspirin", "warfarin", "ibuprofen", "lisinopril", "penicillin",
    "sildenafil", "nitroglycerin", "metformin", "paracetamol",
}
STATE = {"explain_down": False}


def fake_identity(name):
    n = name.strip().lower()
    known = n in KNOWN_DRUGS
    return {
        "rxcui": f"e2e-{n}" if known else None,
        "ingredients": [n],
        "matched_exactly": known,
        "identity_confirmed": known,
        "resolution_method": "e2e_fixture" if known else "unresolved",
    }


def fake_explain(**kwargs):
    if STATE["explain_down"]:
        raise ExplanationUnavailable("e2e: explanation service switched off")
    return {
        "explanation": f"E2E explanation for a {kwargs['severity']} {kwargs['finding_type']} finding.",
        "citations": [{"generic_name": kwargs.get("drug_name") or "aspirin",
                       "section": "drug_interactions", "text": "E2E source excerpt."}],
        "evidence_hash": "e2e", "model_version": "e2e", "prompt_version": "e2e",
    }


def fake_parse_prescription(text):
    return [w for w in re.findall(r"[a-z]+", text.lower()) if w in KNOWN_DRUGS]


def fake_answer_ddi(drug_name=None, top_k=5):
    return {"answer": f"**Label summary** for {drug_name}: E2E fixture text.", "sources": []}


public_routes.resolve_medication_identity = fake_identity
public_routes.explain_finding = fake_explain
app_module.parse_prescription = fake_parse_prescription
app_module.answer_ddi = fake_answer_ddi

# ── Seed data ───────────────────────────────────────────────────────────────

init_db()


def _rule(a, b, severity, status):
    first, second = sorted([a, b])
    return ClinicalRule(
        rule_type=FindingType.DDI, pair_key=f"{first}||{second}", ingredient_a=first, ingredient_b=second,
        clinical_effect=f"E2E: {first} with {second} interacts.", severity=severity, status=status,
        rule_version="e2e-v1",
    )


def _seed_case(session, org_id, patient, prescriber_id, medication, ingredients):
    med = Medication(display_name=medication)
    session.add(med)
    session.flush()
    prescription = Prescription(
        organization_id=org_id, patient_id=patient.id, prescriber_id=prescriber_id,
        medication_id=med.id, status=PrescriptionStatus.ACTIVE,
    )
    snapshot = ClinicalProfileSnapshot(patient_id=patient.id)
    session.add_all([prescription, snapshot])
    session.flush()
    case = create_case(session, org_id, prescription, snapshot)
    run_case_analysis(session, case, ingredient_names=ingredients, allergy_names=[])
    return case


with get_session() as session:
    org = Organization(name=accounts["organization"])
    session.add_all([org, Organization(name=accounts["otherOrganization"])])
    session.flush()
    org_id = org.id

    pharmacist = User(
        organization_id=org_id, email=accounts["pharmacist"]["email"],
        password_hash=hash_password(accounts["pharmacist"]["password"]),
        role=UserRole.PHARMACIST, full_name=accounts["pharmacist"]["fullName"],
    )
    session.add(pharmacist)
    session.add_all([
        _rule("aspirin", "warfarin", Severity.MAJOR, RuleStatus.APPROVED),
        _rule("nitroglycerin", "sildenafil", Severity.CRITICAL, RuleStatus.APPROVED),
        _rule("ibuprofen", "lisinopril", Severity.MAJOR, RuleStatus.DRAFT),
    ])
    session.flush()
    pharmacist_id = pharmacist.id

registered = register_user(
    email=accounts["patient"]["email"], password=accounts["patient"]["password"], organization_id=org_id,
    full_name=accounts["patient"]["fullName"],
    first_name=accounts["patient"]["firstName"], last_name=accounts["patient"]["lastName"],
)

with get_session() as session:
    patient = session.get(Patient, registered["patient_id"])

    # Awaiting review, with an UNREVIEWED (draft-rule) interaction behind it.
    _seed_case(session, org_id, patient, pharmacist_id, "Lisinopril", ["ibuprofen", "lisinopril"])

    # Reviewed and released, with a message from the pharmacist.
    released = _seed_case(session, org_id, patient, pharmacist_id, "Aspirin", ["aspirin", "warfarin"])
    transition_case(session, released, SafetyCaseState.READY_TO_DISPENSE)
    send_patient_communication(
        session, released, approved_explanation="E2E: your pharmacist reviewed this and released it.",
        delivery_channel=DeliveryChannel.PORTAL,
    )

    # On hold, with nothing flagged.
    held = _seed_case(session, org_id, patient, pharmacist_id, "Metformin", ["metformin"])
    transition_case(session, held, SafetyCaseState.HELD_OR_CANCELLED)

    patient_user_id = patient.user_id

# ── Test-only controls (not part of the product) ────────────────────────────


@flask_app.route("/__e2e__/reset", methods=["POST"])
def e2e_reset():
    public_routes.KILL_SWITCH_SELF_CHECK = False
    public_routes.KILL_SWITCH_EXPLAIN = False
    STATE["explain_down"] = False
    return {"ok": True}


@flask_app.route("/__e2e__/kill-switch", methods=["POST"])
def e2e_kill_switch():
    body = request.get_json(force=True)
    attribute = {"self_check": "KILL_SWITCH_SELF_CHECK", "explain": "KILL_SWITCH_EXPLAIN"}[body["feature"]]
    setattr(public_routes, attribute, bool(body["on"]))
    return {"ok": True}


@flask_app.route("/__e2e__/explain-outage", methods=["POST"])
def e2e_explain_outage():
    STATE["explain_down"] = bool(request.get_json(force=True)["on"])
    return {"ok": True}


@flask_app.route("/__e2e__/expired-token")
def e2e_expired_token():
    return {"token": create_access_token(identity=patient_user_id, expires_delta=timedelta(seconds=-30))}


if __name__ == "__main__":
    print(f"e2e server on http://127.0.0.1:{PORT}  (database: {DB_PATH})", flush=True)
    flask_app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False, debug=False)

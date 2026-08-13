# DDI-RAG — Medication Safety Coordination Platform

A clinical drug-drug interaction (DDI) safety platform. Prescriptions are
checked against a deterministic clinical rule engine, findings are routed
through a pharmacist → prescriber workflow, and an LLM (Groq) is used only
to *explain* findings in plain language — never to decide them.

**Core safety principle enforced throughout the code:** the LLM never
determines clinical facts (whether an interaction exists, its severity, or
what to do about it). A deterministic rule engine decides; the LLM only
explains what's already decided, and is structurally prevented from
changing it. "Unknown" is never treated as "safe" — a missing or
unreviewed rule produces an explicit `unknown / pending review` result,
not silence.

Full session-by-session build history, architecture decisions, and known
gaps: [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md).

---

## Architecture

| Layer | Technology | Notes |
|---|---|---|
| API | Flask + flask-jwt-extended | `ddi_rag/app.py` |
| Auth | JWT (HS256) + bcrypt (cost 12) | `ddi_rag/auth.py` |
| Domain database | PostgreSQL (Supabase) | 17 tables — organizations, users, patients, prescriptions, safety cases, findings, audit events, etc. SQLite is used for local dev/tests only. |
| Vector store | PostgreSQL + `pgvector` (same database) | `ddi_rag/services/evidence_store.py` |
| Embeddings | Cohere (`embed-english-v3.0`) | hosted API, no local model |
| LLM generation | Groq (`llama-3.1-8b-instant`) | hosted API, no local model |
| Medication identity | RxNorm (NLM, free, no key) | identity/RxCUI resolution only — never used for interaction data (RxNav's interaction endpoints were discontinued by NLM in Jan 2024) |
| Frontend | Plain HTML + Tailwind (CDN) | `ddi_rag/static/patient/index.html` — patient-facing only, no build step |

No local ML dependencies (no `torch`, no `sentence-transformers`) — both
embeddings and generation are hosted API calls, chosen to keep local
resource requirements minimal.

### Request flow

1. A prescription + patient context comes in.
2. `services/medication_identity.py` resolves the drug name to an RxCUI via
   RxNorm. Ambiguous matches are never silently confirmed — they're flagged
   for pharmacist review.
3. `services/clinical_rules.py` runs deterministic checks (drug-drug,
   drug-allergy, duplicate therapy) against the patient's medication list.
   This step never calls an LLM. A match against an *unreviewed* rule
   produces an `unknown` finding, not a clinical verdict.
4. Once a finding is frozen, `services/evidence_store.py` retrieves
   supporting FDA label text (Cohere embedding + pgvector similarity
   search), and `services/evidence.py` asks Groq to explain the finding in
   plain language — the explanation cannot alter the finding's type,
   severity, or recommended action (enforced structurally, not just by
   prompt).
5. `services/professional_workflow.py` drives the case through the
   pharmacist queue → prescriber intervention → dispense → patient
   communication lifecycle, with a full audit trail
   (`services/audit.py` — every step is append-only).

---

## Repository structure

```
ddi_rag/
├── app.py                    Flask API — /api/auth, /api/query, /v1/safety-cases,
│                              /v1/interventions, /v1/my/cases, /v1/organizations,
│                              serves the patient frontend at /patient
├── auth.py                   JWT + bcrypt; patient registration auto-creates a Patient record
├── config.py                 All environment variables / tunable constants
├── database.py                SQLAlchemy engine/session for the domain models
├── models.py                  17 domain tables
├── enums.py                   UserRole, SafetyCaseState, Severity, FindingType, RuleStatus, etc.
├── mcp_server.py               Claude Desktop/Cursor MCP interface — NOT the hospital API boundary
├── data_preprocessing.py       Real FDA text cleaning (load_and_clean_data, clean_text)
├── drug_categorization.py      Drug → route/type fuzzy lookup, CSV-sourced
├── fda_sync.py                 Nightly openFDA sync — currently disabled, see Known limitations
├── services/
│   ├── audit.py                  Append-only audit event recording
│   ├── safety_case.py            SafetyCase state machine, closed-case immutability
│   ├── medication_identity.py    RxNorm-based identity resolution
│   ├── clinical_rules.py         Deterministic rule engine (no LLM)
│   ├── evidence_store.py         Cohere + pgvector evidence retrieval
│   ├── rag_pipeline.py           CRAG orchestration (retrieve → grade → correct → generate)
│   ├── evidence.py               Constrained explanation generation
│   ├── professional_workflow.py  Case analysis → queue → intervention → dispense → patient comms
│   ├── eval_metrics.py           Clinical regression metrics (per-severity, never aggregated)
│   └── llm_eval.py               Faithfulness scoring + citation grounding
└── static/patient/index.html   Patient-facing frontend

scripts/
├── check_connections.py       Verify Database/RxNorm/Groq/Cohere/pgvector are reachable
└── ingest_evidence.py         One-time ingestion of a curated real data slice

tests/          67 tests — unit + integration, all mocked externally except where noted
docs/           SESSION_HANDOFF.md — full build history and context
```

---

## Setup

```bash
cd ddi_rag
python -m venv venv
venv\Scripts\activate      # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
```

Copy `.env.example` to `.env` **in the repository root** (not inside
`ddi_rag/`) and fill in real values:

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key — used for all LLM generation (explanations, query rewriting). Get one at console.groq.com. |
| `GROQ_MODEL` | No (has default) | Defaults to `llama-3.1-8b-instant`. |
| `COHERE_API_KEY` | Yes | Cohere API key — used for all embeddings (evidence indexing + query search). Get one at dashboard.cohere.com. |
| `COHERE_EMBED_MODEL` | No (has default) | Defaults to `embed-english-v3.0` (1024-dim). |
| `DATABASE_URL` | Yes | A **PostgreSQL** connection string with the `pgvector` extension enabled (e.g. a free Supabase project — run `create extension if not exists vector;` once in its SQL editor). SQLite is only used automatically by the test suite; the app itself needs real Postgres for the evidence store to work. |
| `JWT_SECRET_KEY` | Yes | Random string, 32+ characters. Signs all issued JWTs — the app refuses to start if this is missing or too short. Rotating it invalidates every previously-issued token. |
| `PORT` | No (has default) | Defaults to `5000`. |
| `DDI_DATA_CSV` | No (has default) | Path to the openFDA CSV used by ingestion scripts. |

`ddi_rag/config.py` reads only the root `.env` — there should not be a
second one under `ddi_rag/`. **Never commit `.env`** — only `.env.example`
(with empty placeholder values) belongs in git.

### Verify everything is connected

```bash
python scripts/check_connections.py
```

Checks Database, RxNorm, Groq, Cohere, and the pgvector extension/table —
prints pass/fail for each without ever printing secret values.

---

## Running the API

```bash
cd ddi_rag
python app.py
```

Creates the database tables (if missing) and starts the Flask API on
`http://0.0.0.0:5000` (`PORT` env var to change it).

```bash
curl http://localhost:5000/api/health
```

The patient-facing frontend is served at `http://localhost:5000/patient`.

## Running tests

```bash
python -m pytest tests/
```

67 tests, ~10-20 seconds. All external services (Groq, Cohere, RxNorm,
Postgres/pgvector) are mocked in tests — the suite needs no real
credentials or network access to run.

## Ingesting real evidence data

```bash
python scripts/ingest_evidence.py
```

Runs the real preprocessing pipeline on a curated slice of the openFDA
dataset (not the full corpus — see the script for the drug list and why
it's scoped down), embeds it via Cohere, and stores it in pgvector. Also
ingests a matching slice of DDI pairs as unreviewed (`DRAFT`) clinical
rules — nothing is auto-approved as clinically valid.

---

## Design principles (enforced in code, not just documented)

- **The LLM never determines clinical facts.** `services/clinical_rules.py`
  contains zero LLM calls. Severity, type, and recommended action are
  decided deterministically before any explanation is generated.
- **Unknown is never "safe."** A rule that hasn't been clinically reviewed
  produces an explicit `unknown` finding requiring manual review — not
  silence, and not a false "no concerns."
- **Explanations can't rewrite findings.** `services/evidence.py`'s
  `explain_finding()` structurally can only return explanation text,
  citations, and version metadata — it has no return path for severity or
  action.
- **Tenant isolation is enforced and tested** — an organization cannot see
  or act on another organization's cases.
- **Everything is audited.** `services/audit.py` is the only path to an
  `AuditEvent` row; rows are append-only.
- **Ambiguous medication identity is never silently resolved.** An
  approximate RxNorm match is flagged for pharmacist confirmation rather
  than trusted automatically.

## Known limitations

- **Only 3 of the architecture spec's rule categories are implemented**
  (drug-drug interactions, drug-allergy, duplicate therapy). Drug-condition,
  dose/route, age, pregnancy, kidney/liver function, and monitoring rules
  are not yet built.
- **No Alembic migrations** — schema bootstraps via
  `Base.metadata.create_all()`. Fine for a fresh database; not safe for
  schema evolution against populated data.
- **`fda_sync.py`'s nightly sync is disabled** (`NotImplementedError`) — it
  targeted a since-removed ChromaDB index and was never reimplemented
  against pgvector. The openFDA fetch/parse helpers in that file are still
  valid and reusable.
- **No RBAC beyond a basic role field, no MFA, no encryption-at-rest, no
  rate limiting.**
- **Only a curated slice of the openFDA corpus has been ingested** (~138
  chunks / 8 drugs, not the full ~66,000-drug dataset) — see
  `scripts/ingest_evidence.py`.
- **No clinical validation has occurred.** All data used and referenced in
  testing is synthetic. This system has not been reviewed by qualified
  clinical staff and is not approved for use with real patients.
- **Only a patient-facing frontend exists** — no pharmacist/clinical-web
  application yet.

See [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md) for the full list
of deviations from the original architecture spec, real bugs found and
fixed during development, and suggested next steps.

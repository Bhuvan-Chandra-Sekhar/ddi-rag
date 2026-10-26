# Architecture

How this repo is actually laid out and how a request flows through it —
written so the next person (or session) doesn't have to re-derive it the
way this one did.

## Backend (`ddi_rag/`)

```
ddi_rag/
  app.py            — Flask app factory + top-level routes (health, auth,
                       /api/query, the professional-workflow endpoints that
                       predate the blueprint split)
  config.py         — the only place environment variables are read; every
                       other module imports constants from here
  database.py       — SQLAlchemy engine/session (get_session(), init_db())
  models.py         — ORM models
  enums.py          — shared enums (UserRole, Severity, RuleStatus, ...)

  routes/           — Flask blueprints (the HTTP layer — request in,
                       service call, response out; no clinical logic lives
                       here)
    clinical.py     — clinical_bp: patients, prescriptions, safety cases,
                       the pharmacist/prescriber console, rule review
    public.py       — public_bp: unauthenticated guest self-check/explain

  core/             — cross-cutting request-path concerns, shared by both
                       app.py and routes/
    auth.py         — register/authenticate, JWT config, password hashing
    authz.py        — tenant isolation + role enforcement (authorized_case,
                       require_role)
    rate_limit.py   — the shared Flask-Limiter instance

  services/         — business logic. This is where clinical facts get
                       decided; routes/ and app.py only orchestrate calls
                       into here.
    clinical_rules.py      — deterministic DDI rule evaluation, rule
                              governance (DRAFT/APPROVED/REJECTED/RETIRED)
    evidence.py            — LLM-generated explanations (never determines
                              severity/action — see its own docstring)
    evidence_store.py      — Postgres/pgvector evidence chunk storage
    medication_identity.py — RxNorm-backed drug-name resolution
    professional_workflow.py — safety-case assessment/intervention routing
    safety_case.py          — SafetyCase state machine
    audit.py                — append-only AuditEvent writes
    rag_pipeline.py          — chunking/retrieval helpers, safe_str()

  pipeline/         — data-ingestion-side modules, not on the request path
                       (used by scripts/, not by live routes except where
                       noted)
    prescription_parsing.py — free-text drug-name detection for
                               /api/query's detected_drugs (IS used live)
    fda_sync.py              — openFDA sync (currently disabled, see its
                               own docstring)
    data_preprocessing.py    — openFDA dataset cleaning
    aho_corasick.py          — the multi-pattern string matcher
                               prescription_parsing.py is built on

  mcp_server.py     — standalone MCP tool server for Claude Desktop; a
                       separate interface, not part of the Flask app and
                       not imported by it

  static/           — pre-built SPA bundles Flask serves directly
    patient-app/    — the current patient portal (Vite build output —
                       see "Deploy path" below)
    clinical/       — the pharmacist/prescriber console (hand-written HTML,
                       no build step, no source elsewhere in this repo)
```

### Import style

Every module in `ddi_rag/` imports its siblings by bare name relative to
`ddi_rag/` itself (e.g. `from core.auth import ...`, `from config import
...`), not as `ddi_rag.whatever`. This works because both the production
entrypoint and the test suite put `ddi_rag/` directly on `sys.path`:
- `render.yaml`'s `gunicorn --chdir ddi_rag app:flask_app` changes into
  `ddi_rag/` before importing `app`.
- `app.py` itself also does `sys.path.insert(0, <its own directory>)`.
- `tests/conftest.py` does the same insert for the test suite.

Keep new intra-package imports consistent with this (`from core.x import
y`, `from routes.x import y`, `from pipeline.x import y`) rather than
switching to `ddi_rag.*` imports partway through — mixing the two styles
in one process is how you get the same module loaded twice under two
different names.

### Request flow

A typical authenticated clinical request: `routes/clinical.py` (HTTP
layer: parse request, call `core.authz.authorized_case()`/`require_role()`
for tenant+role checks) → a function in `services/` (the actual clinical
logic — e.g. `services.clinical_rules.evaluate_ddi_pairs()`) → `models.py`
rows via `database.get_session()`. The route never decides a clinical
fact itself; it only shapes the request/response and enforces who's
allowed to ask.

Errors: `app.py`'s app-wide `@flask_app.errorhandler(Exception)` is the
last line of defense — it logs the full exception server-side and returns
a generic `{"error": "internal_error", "message": "..."}` to the client,
never the raw exception text (see `docs/HAZARD_REGISTER.md` H17/H25).
Expected, named failure modes (bad input, a closed case, an explanation
outage) are caught at the route and return a specific `{"error": "<code>"}`
or `{"error": "<code>", "message": "<safe text>"}` with an appropriate
4xx/503 — see `docs/API.md`.

## Frontend (`frontend-patient/`)

```
frontend-patient/src/
  App.jsx           — top-level view switch only; reads state via
                       useAppState(), renders whichever screen is active
  state/
    AppStateContext.jsx — owns view/session/in-progress-check state and
                           the handlers that mutate it (extracted out of
                           App.jsx's body)
  api.js            — the only place that calls fetch() — token/session
                       storage, the api() wrapper, markdown-lite rendering
  screens/          — one per view (Home, Checker, Scanning, Results,
                       Auth, Dashboard) — presentational, receive explicit
                       props from App.jsx rather than reaching into the
                       context themselves (no actual multi-level prop
                       drilling exists today, so screens stay easy to
                       test/reuse in isolation)
  components/       — shared pieces used by more than one screen
```

Config: there's no separate frontend env-var file — `api.js` calls
`window.location.origin`, since the patient app and the API it calls are
always served by the same Flask process (see "Deploy path" below). There's
nothing to externalize here; a different API origin would need a real
env var, but that's not the deployed shape today.

## Deploy path (`render.yaml`)

```
buildCommand:  npm --prefix frontend-patient run build
startCommand:  gunicorn --chdir ddi_rag app:flask_app
healthCheckPath: /api/health
```

The build step runs Vite against `frontend-patient/`, whose
`vite.config.js` `outDir` points at `ddi_rag/static/patient-app/` — that
output is also committed to git (unusual for a build artifact, but
intentional: it lets a Python-only deployment environment serve the
React app without running `npm` at all, as a fallback). `app.py`'s
`/patient` route serves `static/patient-app/index.html` if it exists,
falling back to the older `static/patient/` bundle otherwise (that
fallback bundle was removed in this reorg as superseded — see
`docs/HAZARD_REGISTER.md`'s change history via git log if you need it
back).

`ddi_rag/` and `frontend-patient/` are deploy-path-sensitive — both
names are referenced directly in `render.yaml`. Any future restructuring
that renames either directory must update `render.yaml` in the same
change, not after.

`/api/health` (not `/api/health/deep`) is Render's own restart trigger —
it must never depend on the database, or a transient DB blip causes an
unnecessary process restart. See `docs/INCIDENT_RUNBOOK.md`.

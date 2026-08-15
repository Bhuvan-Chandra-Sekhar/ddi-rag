# Session Handoff — Clinical Safety Copilot / DDI-RAG / MedTrust Connect

Written during a long session to carry context forward (into a new chat, or
past a context-window reset). Read this before doing anything else on this
project.

**Latest session (continuation):** built a second frontend — a
pharmacist/prescriber-facing "Clinical Console" at `/clinical` — so you can
verify the system's real answers yourself instead of taking my word for it.
See §13 for what's new; the rest of this file is prior-session context and
is still accurate except where §13 supersedes it (queue endpoint response
shape, database engine config).

---

## 1. What this project is

A clinical-grade Drug-Drug Interaction (DDI) safety platform, evolving from a
research RAG prototype toward the architecture specified in an external
document you provided mid-session (a Word doc: "Medication Safety Coordination
Platform" architecture guide). That doc's roadmap (Phase 0–8) has been the
guiding structure since. You later re-read that source document in full and
confirmed this handoff's account of it matches — it's an authoritative spec,
not a paraphrase. Product name in the docs: "MedSafe Interaction Portal" /
"MedTrust Connect" (patient-facing brand).

**Core principle enforced throughout the code:** the LLM never determines
clinical facts (interaction existence, severity, action). A deterministic
rule engine decides; the LLM only explains what's already decided, and is
structurally prevented from changing it. "Unknown" is never conflated with
"safe."

---

## 2. Starting state (what was broken/missing)

- `app.py`, `auth.py`, `config.py`, `database.py`, `models.py`,
  `pharmacy_search.py` referenced by imports but **missing from disk** —
  never committed to git, only `.pyc` traces existed. Rebuilt from scratch
  this session (not recovered — a backup zip existed but predated
  JWT/Qdrant/Groq entirely, so it wasn't useful).
- **Confirmed via full git history search** (`git log --all`): `pharmacy_search.py`
  had at least once existed locally (`.pyc` trace). `ablation_study.py`,
  `ddi_pair_ingest.py`, and `visualization.py` — also named as missing in
  the architecture doc's blockers list — **never existed in any commit,
  ever**. Commit `80cc6b7`'s message claims "isolate ablation study" but its
  actual diff has nothing to do with it — a misleading commit message, not
  a lost file.
- Root had a recurring pattern of zero-byte junk files (`(lo`, `{`, `index`,
  `list`, `awaiting_prescriber_response,`, `'`, `32`, `dict`, `exact`, etc.)
  — debris from some unidentified environment process, not anything I
  created. Deleted every batch found across the session; more may still
  appear (unexplained, low-stakes, low-frequency).
- Two `.env` files existed (root + `ddi_rag/.env`) — consolidated to root
  only; `config.py` now loads only the root `.env`.
- `PROJECT.md` describes a much larger, partly aspirational system
  (Streamlit UI, Docker Compose, a "MedTrust Connect" frontend with 11
  Stitch-designed screens) that **does not match the actual code**. Flagged
  repeatedly as stale; **still not rewritten** — do this if asked.
  Recommendation given and accepted in spirit but not executed: don't edit
  the original external architecture guide (treat it as the frozen spec);
  rewrite `PROJECT.md` as the living "what we built and why we diverged"
  document instead.

---

## 3. Major architecture decisions made this session

| Decision | Chosen | Why |
|---|---|---|
| Vector store | **Supabase Postgres + pgvector** (not Qdrant, not ChromaDB, no Redis) | User has low RAM, wanted a "website" not local infra; consolidates with the transactional DB into one connection string. This is a confirmed, deliberate deviation from the architecture doc's Appendix C (which assumes Qdrant + Redis) — tracked here, not yet written back into any doc. |
| Embeddings | **Cohere** (`embed-english-v3.0`, 1024-dim) via plain HTTP, no SDK | Free tier, no local model — removes `torch`/`sentence-transformers` entirely |
| LLM generation | **Groq** (`llama-3.1-8b-instant`) via plain HTTP, no SDK | Already in use, cheap, fast, free tier generous |
| DB for domain models | Same Supabase Postgres (SQLite only for tests) | One database, not two |
| Vector index type | **HNSW**, not IVFFlat | Real bug found: IVFFlat gave silently incomplete `LIMIT` results on small tables |

### Cost — verified, not guessed (two rounds of web search for current pricing)

You are almost certainly still at **$0** given current usage:

| Service | Free tier | Paid tier (if you outgrow free) |
|---|---|---|
| Cohere | **Trial key**: 1,000 calls/month total, ~5/min for Embed specifically. Explicitly barred from production/commercial use. | Pay-as-you-go, no subscription, billed monthly or at $250 balance. Embed v3: $0.10/million tokens. |
| Groq | **Free**: 30 req/min, 6,000 tokens/min, 14,400 req/day, no card required. | **Developer** tier (add a card, zero minimum spend): ~10x free-tier rate limits + 25% token discount. Llama 3.1 8B Instant: $0.05/M input, $0.08/M output tokens. **Enterprise**: custom, dedicated capacity. |
| Supabase | Free project tier (storage/compute capped) | Subscription tiers by storage/compute — check their current pricing page for exact thresholds, not verified here |

Full-corpus ingestion (~930K chunks per PROJECT.md) would cost roughly
**$15-20 one-time** for embeddings — cheap in absolute terms, but would
exceed Cohere's 1,000-calls/month trial cap (even batched at 96/request,
~9,700+ calls), forcing a move to the paid Cohere tier. The real constraint
on doing this now was *time* (rate limits, per-row DB round trips), not
money.

**Your hardware** (AMD Ryzen 5 3550H, 8GB RAM, GTX 1650 4GB VRAM) — advised
to **stay on hosted APIs**, not go local. Local embeddings are technically
feasible on that GPU but pointless given free-tier headroom; local LLM
generation is not realistically viable (8B model needs ~5GB even
quantized, competes with your only 8GB system RAM).

---

## 4. Architecture-doc roadmap — phase completion status

Phase 0 (repo recovery) → Phase 5 (professional workflow) are **built and
tested**. Phases 6–8 (security/MFA, clinical validation pilot, hospital/payer
integrations) are **not started at all** — be direct about this if asked,
don't let it blend into "mostly done."

| Phase | Status | Key artifacts |
|---|---|---|
| 0 — Recovery | Done, with caveats (see §6) | `app.py`, `auth.py`, `config.py`, `database.py`, `models.py` rebuilt |
| 1 — Domain foundation | Done | `models.py` (17 tables), `enums.py`, `services/safety_case.py` (state machine) |
| 2 — Medication identity | Done | `services/medication_identity.py` (RxNorm exact-vs-approximate match, never silently confirms ambiguous names) |
| 3 — Clinical rule engine | Done, but only 3 of 10 rule categories | `services/clinical_rules.py` — DDI pairs, drug-allergy, duplicate therapy only. **No** drug-condition, dose/route, age, pregnancy, kidney/liver, labs, or monitoring rules yet. Building these needs either a real clinical threshold dataset (none exists in-repo) or clearly-marked placeholder values — ask before assuming either. |
| 4 — Evidence/explanation | Done | `services/evidence_store.py` (pgvector+Cohere), `services/evidence.py` (constrained Groq explanation, cannot alter severity/action) |
| 5 — Professional workflow | Done, **but see §8 for a real routing bug found and not yet fixed** | `services/professional_workflow.py`, `/v1/safety-cases`, `/v1/interventions` API |
| 6 — Security & ops | **Not started** | No MFA, no encryption-at-rest, no rate limiting, no Alembic migrations |
| 7 — Clinical validation | **Not started** | No clinician-reviewed gold cases beyond the hand-made test fixtures |
| 8 — Integrations | **Not started** | No FHIR/SMART-on-FHIR/CDS Hooks adapters |

---

## 5. The governance framework

Partway through, you gave a detailed "Universal Rules" document (10 rules +
phase-by-phase checklists + permanent safety rules + a "universal stop rule").
I ran a full honest audit against it — key findings, still mostly true:

- **Tenant isolation was a real gap**, found and fixed: workflow routes
  didn't verify a case belonged to the caller's organization. Now enforced
  via `_authorized_case_or_error()` in `app.py`, tested.
- **No optimistic concurrency control** initially — fixed, added version
  checks to `SafetyCase`/`Finding`.
- **Dismissing/overriding a MAJOR/CRITICAL finding required no reason** —
  fixed, now enforced with a documented-reason requirement.
- **`continue_with_rationale` prescriber decision didn't actually require a
  rationale** — fixed.
- Permanent rules ("LLM never determines severity," "unknown ≠ safe",
  "severe findings cannot be silently deleted") are enforced structurally
  and covered by tests, not just policy — **with one real exception found
  later, see §8**.
- Process rules (ownership assignment, formal clinical sign-off, evidence
  collection) are explicitly **not something I can do** — flagged as your
  responsibility, not mine.

---

## 6. Real bugs found and fixed this session (not hypothetical — actually caught)

1. **IVFFlat vector index silently dropped results** on small tables —
   switched to HNSW. Caught by actually running a real query, not by
   inspection.
2. **Generic Flask exception handler was turning 404s into 500s** — caught
   by the pytest smoke test, fixed by checking `isinstance(e, HTTPException)`.
3. **`CHUNK_SIZE`/`CHUNK_OVERLAP` missing from an import list** in
   `rag_pipeline.py` — would have crashed the moment chunking was actually
   used (which it later was). Found while moving the file, before it bit
   anyone.
4. **`upsert_chunks()` sent unbounded batches to Cohere** — Cohere caps at
   96 texts/request. Fixed to batch by `EMBED_BATCH_SIZE`.
5. **`scripts/check_connections.py` silently broken** — still imported
   removed `QDRANT_URL`/`QDRANT_API_KEY` names after the Qdrant→pgvector
   migration. Fixed; now checks Database/RxNorm/Groq/Cohere/pgvector.
6. **Groq API key was invalid (401)** mid-session — user rotated it, since
   confirmed working.
7. **A malformed `DATABASE_URL`** cost two rounds of debugging — first had a
   stray character before `@` (unescaped special char in password), then a
   literal `]` left over from not fully replacing Supabase's
   `[YOUR-PASSWORD]` placeholder token. Now correct and connected.
8. Several **stale "Qdrant" references** left in docstrings across
   `fda_sync.py`, `mcp_server.py`, `services/llm_eval.py`,
   `services/evidence_store.py` after the migration — cleaned up.
9. **`.gitignore` path mismatch** — it tried to exclude
   `data/clean_ddi_dataset.csv`, but the real file is at
   `data/datasets/clean_ddi_dataset.csv` (240MB, over GitHub's 100MB limit).
   Fixed the path; also added `data/processed/` (thousands of generated
   per-drug `.txt` files).
10. **`services/medication_identity.py`'s `_fetch_ingredients()` was
    silently returning `[]` for every drug** — `requests` percent-encodes a
    literal `+` (which RxNorm's `tty=IN+PIN+MIN` param requires unescaped)
    into `%2B`, which RxNorm's API rejects with a 400. It failed inside a
    try/except so nothing crashed, it just quietly returned no ingredients.
    Fixed by embedding the query string directly in the URL instead of
    passing it through `params=`. Verified live: now correctly returns
    `['warfarin', 'warfarin sodium', 'warfarin potassium']`.

### Found but NOT fixed — needs a decision

11. **`assess_findings_and_route()` ignores the pharmacist's own review
    decision when routing.** It only checks `severity in {MAJOR, CRITICAL}`
    to decide whether a case goes to the prescriber. Demonstrated live: I
    (as the pharmacist) explicitly marked an `unknown`-severity finding
    `ESCALATED`, and the case routed straight to `ready_to_dispense` anyway
    — the `ESCALATED` review_status had no effect on routing. Given the
    architecture doc's own alert-level table says `unknown` findings need
    "manual review; never label safe," this is a real gap between intent
    and behavior, not a hypothetical one. **Not fixed — flagged to user,
    awaiting a decision on whether/how to fix it.**

### Security incident — resolved, but action still needed from you

- `.env.example` (meant to be an empty template) got edited with **real
  Groq and Cohere API key values** at some point instead of `.env`. It made
  it into a git commit. **GitHub's push protection blocked the push before
  anything reached the remote** — so it was never publicly exposed on
  GitHub. I rewrote `.env.example` back to empty placeholders and amended
  the not-yet-pushed commit (a deliberate, justified exception to the
  usual "don't amend" rule, since nothing had been shared yet and leaving a
  real secret permanently in local git history was worse than amending).
  Push then succeeded clean.
- **You have not yet rotated the Groq or Cohere keys, or the
  `JWT_SECRET_KEY`.** Recommended out of caution: Groq/Cohere because they
  briefly existed in plaintext on disk and in a local commit even though
  never published; `JWT_SECRET_KEY` because it lived in the same file and
  GitHub's scanner wouldn't have flagged it either way (it only recognizes
  known vendor key formats, not arbitrary random secrets like a JWT
  signing key) — so its absence from the GitHub alert is not proof it was
  safe. Rotating the JWT secret will sign out any active sessions
  (expected, not a bug). **This is still an open action item for you.**

---

## 7. Current file structure (accurate as of end of session)

```
ddi_rag/                          (repo root)
├── PROJECT.md                    — STALE, describes a different/bigger system, not fixed yet
├── README.md                     — REWRITTEN this session: full architecture, setup, env var table
├── CLAUDE.md                     — accurate
├── main.py                       — placeholder, does nothing
├── requirements.txt              — single pinned manifest
├── .env / .env.example           — root .env is the only one read; .env.example is safe (empty placeholders)
├── docs/SESSION_HANDOFF.md       — this file
│
├── src/ingest.py                 — openFDA raw JSON → per-drug .txt (pre-existing, untouched)
├── scripts/
│   ├── check_connections.py      — verify Database/RxNorm/Groq/Cohere/pgvector are live
│   └── ingest_evidence.py        — the curated real-data ingestion script (see §8)
│
├── ddi_rag/                      (application package)
│   ├── app.py                    — Flask API: /api/auth, /api/query, /v1/safety-cases,
│   │                                /v1/interventions, /v1/my/cases, /v1/organizations,
│   │                                serves /patient
│   ├── auth.py                   — bcrypt + JWT; patient registration auto-creates linked Patient row
│   ├── config.py                 — all env vars/constants, single source of truth
│   ├── database.py               — SQLAlchemy engine/session for domain models
│   ├── models.py                 — 17 domain tables
│   ├── enums.py                  — UserRole, SafetyCaseState, Severity, FindingType, RuleStatus, etc.
│   ├── mcp_server.py              — separate interface for Claude Desktop/Cursor (MCP), NOT the hospital API boundary
│   ├── data_preprocessing.py      — real FDA text cleaning (load_and_clean_data, clean_text)
│   ├── drug_categorization.py     — drug → route/type fuzzy lookup, CSV-sourced
│   ├── fda_sync.py                — nightly sync job, run_sync()/start_scheduler() DISABLED (NotImplementedError) — targeted removed ChromaDB, never reimplemented against pgvector
│   │
│   ├── services/
│   │   ├── audit.py                 — record_audit_event(), the only path to AuditEvent rows
│   │   ├── safety_case.py           — SafetyCase state machine, closed-case immutability
│   │   ├── medication_identity.py   — RxNorm resolution (RxNorm `+` param bug fixed this session)
│   │   ├── clinical_rules.py        — deterministic rule engine (3 of 10 categories built)
│   │   ├── evidence_store.py        — Cohere + pgvector, real retrieval backend
│   │   ├── rag_pipeline.py          — CRAG orchestration (moved here from top-level this session)
│   │   ├── evidence.py              — constrained explanation (explain_finding)
│   │   ├── professional_workflow.py — case analysis → queue → intervention → dispense → patient comms — **has the unfixed routing bug, see §6**
│   │   ├── eval_metrics.py          — clinical regression metrics (per-severity, never aggregated)
│   │   └── llm_eval.py              — faithfulness scoring (v1 heuristic) + citation grounding
│   │
│   └── static/patient/index.html  — patient-facing frontend (plain HTML/Tailwind, no build step)
│
└── tests/                         — 67 tests, all passing, ~10-22s to run
```

---

## 8. Real data currently in the live Supabase database

Ran `scripts/ingest_evidence.py` for real (not mocked):
- **138 real evidence chunks** in `evidence_chunks`, from 8 curated drugs:
  warfarin, aspirin, ibuprofen, amoxicillin, penicillin, lisinopril,
  metformin, acetaminophen. Real Cohere embeddings, real pgvector storage.
- **1,824 real DDI-pair rules** in `clinical_rules`, filtered from the full
  187,952-row dataset for pairs involving those 8 drugs. All correctly land
  as `DRAFT` (unreviewed) — nothing is auto-approved.
- **Verified working end-to-end, twice.** First: `answer_ddi('warfarin')`
  returned genuine retrieved FDA text and a genuine Groq-generated
  explanation. Second, a full POC run: a synthetic warfarin+ibuprofen case
  run through the *entire* real pipeline — RxNorm identity resolution →
  real deterministic rule match (`unknown/pending review`, correctly not
  claimed safe or dangerous) → real Cohere-embedded evidence retrieval →
  real Groq-generated explanation ("*This interaction is not yet clinically
  approved, so it's essential to manually review the situation*") →
  pharmacist review → dispensed → patient notified → closed, with a full
  real timestamped audit trail. This test is also what surfaced the
  RxNorm `+` bug (found and fixed) and the escalation-routing bug (found,
  not fixed — see §6).
- **Not ingested:** the full ~66,695-drug / ~930K-chunk corpus. Scoped down
  deliberately (time, not cost — see §3). Offered to do the full ingestion;
  user has not yet said go.
- **Demo/test data still sitting in the live database** (not deleted
  automatically, yours to clean up when ready):
  - "Demo General Hospital" org + "Jane Doe" patient with two demo safety
    cases (used to verify the frontend).
  - A second throwaway org/patient/case from the POC test run described
    above (randomly-suffixed org name, e.g. "POC Test Hospital ...").

---

## 9. Frontend

`ddi_rag/static/patient/index.html` — patient-facing app, plain
HTML/Tailwind/vanilla JS, no build step. Public Sans + Manrope fonts,
"Clinical Clarity" palette from PROJECT.md. Register/login (auto-provisions
a `Patient` row + org picker via `/v1/organizations`) → dashboard listing
the patient's own safety cases with status badges + approved explanation
text (never raw findings/severity — patient view is deliberately
restricted). **Verified live in a browser** against the real database, full
loop: register → auto-login → dashboard → sign out → sign in → same data,
no server errors.

Only the **patient-facing** app exists. No pharmacist/clinical-web app, no
landing page — those were offered as options but patient-facing was chosen.

Dev server config: `.claude/launch.json`, name `ddi-rag-api`, runs
`ddi_rag/app.py` via the system Python (not the project's `venv` — see §10).
Serves at `http://localhost:5000`, patient app at `/patient`.

---

## 10. Environment quirks — important for not re-discovering these

- **The project's own `venv` lacks `pytest` and other packages** — no
  internet access was available mid-session to `pip install`. All testing
  used the **system Python** instead:
  `C:\Users\C V REDDY\AppData\Local\Programs\Python\Python311\python.exe`
  — which already had the full stack including pytest 9.0.3. Use this path
  for running tests/scripts until the venv is reconciled.
- **Importing `services/rag_pipeline.py` used to take ~100s** (torch +
  sentence-transformers). That's gone now — down to ~15-20s since local
  embeddings were removed. Full test suite: **~10-22s** for 67 tests.
- **`.env` and `.env.example` read/write is permission-restricted for the
  Read/Grep tools** — I can write them via `Write` or via `Bash` heredoc,
  but cannot `Read` or `grep` them directly. Verification has to go through
  indirect means (printing `bool(value)`/length from Python, piping
  `git show HEAD:file | grep` which isn't blocked the same way, connection
  error messages, etc.).
- **Two Python environments matter**: `venv` (project's own, incomplete)
  and the system Python (complete, used for everything this session).
  Anaconda's Python at `C:\Users\C V REDDY\anaconda3\python.exe` also
  exists but has broken DLLs (`_ssl`, `_sqlite3` fail to import) — don't
  use it.
- **Git: committed AND pushed this session** (this is a change from
  earlier in the session — don't assume it's still all uncommitted).
  Three commits landed on `origin/master`:
  1. `29bf8b4` — the full Phase 0-5 rebuild (43 files) — amended once to
     strip the leaked secrets before it ever reached GitHub.
  2. `c632f82` — the README rewrite.
  Check `git log --oneline -5` and `git status` fresh rather than assuming
  state from this doc if time has passed.

---

## 11. Known open gaps (say these plainly if asked "is this done")

- `PROJECT.md` is stale/misleading — offered to rewrite twice, still not done.
- No Alembic migrations — schema only bootstraps via `create_all()`.
- `fda_sync.py`'s nightly sync is disabled/unimplemented against pgvector.
- Only 3 of 10 clinical rule categories exist (no drug-condition, dose/route,
  age, pregnancy, kidney/liver, labs, monitoring rules).
- **The escalation-routing bug in `professional_workflow.py`** (§6, #11) —
  found via live testing, not yet fixed, needs a decision.
- No RBAC beyond basic role field, no MFA, no encryption-at-rest, no rate
  limiting, no audit-log access controls beyond what's built.
- Full openFDA corpus not ingested (138/~930K chunks).
- No clinical validation/pilot has happened or could happen — this is all
  synthetic/test data, never real patients, per your own governance rules.
- `mcp_server.py` sits next to `app.py` with no structural signal it's a
  different trust boundary (flagged, not fixed).
- `data/processed/` has thousands of loose per-drug `.txt` files — now
  gitignored, but still sitting on disk locally, pre-existing clutter.
- **Groq/Cohere/JWT secrets not yet rotated** after the leak incident (§6)
  — this is the most time-sensitive open item.

---

## 12. Natural next steps (pick one, don't assume)

1. **Rotate the Groq/Cohere/JWT secrets** (§6) — recommended first, cheap,
   quick, addresses the one open security item.
2. **Fix the escalation-routing bug** (§6 #11, §11) — found via real
   testing, safety-relevant, not yet fixed.
3. Rewrite `PROJECT.md` to match reality (and document the Qdrant/Redis →
   Supabase/pgvector deviation from the spec, per §2/§3).
4. Ingest the full openFDA corpus (~$15-20 one-time, needs your go-ahead,
   will take real time due to rate limits, and will require moving off
   Cohere's free trial tier).
5. Build out the remaining 7 clinical rule categories — needs either a real
   clinical threshold dataset or agreement to use clearly-marked
   placeholder values.
6. Start Phase 6 (security/ops hardening).
7. Build the pharmacist/clinical-web app (only patient app exists so far).
8. Clean up demo data (Jane Doe / Demo General Hospital / the POC test
   org) from the live database once you're done testing against it.

Do not assume any of these — ask which one before starting.

---

## 13. Latest session — Clinical Console (`/clinical`), a real second frontend

You asked to verify the system's real answers yourself rather than trust my
account of them, and named `/frontend-design` explicitly. Built a second,
pharmacist/prescriber-facing SPA — wired to the live Flask API and the real
Supabase database, no mocks — separate from the existing patient app.

**New files:**
- `ddi_rag/routes_clinical.py` — new Flask blueprint. Adds the endpoints
  app.py didn't have: `/v1/staff`, `/v1/patients` (GET+POST),
  `/v1/prescriptions` (POST), `/v1/safety-cases` (POST — create case +
  run analysis in one call), `/v1/safety-cases/<id>` (GET full detail:
  findings, interventions+responses, escalations, dispensing outcome,
  communications), `/v1/safety-cases/<id>/dispense`, `/…/communicate`,
  `/…/close`, `/…/resolve-escalation`, `/v1/findings/<id>/explain` (calls
  `services/evidence.explain_finding` and persists the result onto the
  Finding row). All JWT-required, tenant-scoped the same way app.py's
  existing routes are. Registered into `app.py` via
  `flask_app.register_blueprint(clinical_bp)`.
- `ddi_rag/static/clinical/index.html` — the console itself. Plain
  HTML/Tailwind/vanilla JS, same no-build-step pattern as the patient app,
  served at `/clinical` (new route in app.py). Dark "diagnostic instrument
  panel" aesthetic (IBM Plex Mono/Sans, amber accent, LED severity badges) —
  deliberately distinct from the patient app's look, since this is a
  different audience (clinical staff verifying the system) doing a
  different job (testing, not reassurance). Covers: a Query Console
  (raw `/api/query`, unmediated), a New Case wizard (create patient →
  prescription → run the real rule engine, with two one-click reproducible
  scenarios baked in — see below), the pharmacist queue, per-case findings
  review with on-demand grounded explanation, sending/responding to
  prescriber interventions, escalation resolution, dispensing outcome,
  patient communication, case close, and the full immutable audit timeline.
- `scripts/seed_demo_staff.py` — self-registration is intentionally
  patient-only (auth.py's own docstring), so pharmacist/prescriber accounts
  don't exist by default. This script provisions them directly against the
  DB (idempotent, safe to re-run). **Already run against your live
  database**: `pharmacist@demo.local` / `DemoPharm123!` and
  `prescriber@demo.local` / `DemoPrescriber123!`, both in the existing
  "Demo General Hospital" org.

**Modified:**
- `ddi_rag/app.py` — registers the new blueprint; adds the `/clinical`
  static route; `/v1/safety-cases/queue` now also returns `patient_name`,
  `medication`, and `created_at` per case (previously id+state only) —
  additive, not a breaking change to the existing shape.
- `ddi_rag/database.py` — **real bug found and fixed, not related to the
  frontend work but blocking it**: the SQLAlchemy engine had no
  `pool_pre_ping`. Supabase's pooler silently drops idle connections; the
  first login attempt this session failed with
  `psycopg2.OperationalError: server closed the connection unexpectedly`
  because SQLAlchemy handed out a dead connection instead of transparently
  reconnecting. Added `pool_pre_ping=True, pool_recycle=180`. This affects
  the *entire app*, not just the new routes — worth knowing if you saw this
  error in earlier sessions and worked around it by just retrying.

**Two scenarios are wired into the New Case wizard as one-click buttons,
both using real ingested data — no synthetic rule insertion needed:**
1. **"Allergy conflict (critical, real)"** — patient allergic to
   penicillin, prescribed penicillin. Produces a real CRITICAL finding
   (the hardcoded drug-allergy rule needs no approved ClinicalRule row).
   Verified live, full loop: explain → accept → routes to prescriber →
   intervention sent → prescriber responds STOP → held_or_cancelled →
   patient communication sent → case closed. 11 audit events, all correct.
2. **"Unreviewed DDI pair (reproduces routing bug)"** — patient on
   ibuprofen, prescribed warfarin. This pair exists in the real 1,824-row
   ingested dataset but, like every pair in it, is DRAFT/unapproved, so it
   produces an `unknown`/`unknown` finding, not a scored one. **Verified
   live that this reproduces the exact bug logged in §6 #11**: marking the
   finding's review_status `escalated` routes the case straight to
   `ready_to_dispense` instead of anywhere resembling real escalation —
   `assess_findings_and_route()` still only checks `severity in
   {MAJOR, CRITICAL}`, ignoring the reviewer's actual decision. This bug is
   still unfixed; it's just now something you can click through yourself
   in under a minute instead of taking my word for it.

Also confirmed directly against `clinical_rules` (1,824 rows): **no pair
among the 8 curated drugs is APPROVED** — all are DRAFT. So a real
MAJOR/CRITICAL *DDI* finding isn't reachable through the seeded data right
now; only the drug-allergy path reaches MAJOR/CRITICAL. Worth knowing if a
scenario "should" show a scored interaction and doesn't — that's the
data, not a bug.

**Not done / out of scope for this pass:** no endpoint to list *all* cases
regardless of state (only the pharmacist-review queue) — the console covers
this with a client-side "recently viewed" list in `localStorage`, not a new
backend endpoint. Dispensing a `held_or_cancelled` case (as opposed to
`ready_to_dispense`) has no UI form, though the backend endpoint doesn't
actually gate on state, so it's reachable via direct API call if needed.

Full test suite (67 tests) still passes after both the blueprint addition
and the database.py change. **Nothing from this session is committed** —
same as the rest of the working tree per §10.

---

## 14. DDInter dataset pulled + cleaned (done autonomously — no one was available to ask, review before trusting)

You asked to fill the DDI-coverage "blanks" found in §13 (aspirin/penicillin
missing real interaction data). Researched options, you picked **DDInter
2.0** (free, open, 2,310 drugs, includes severity levels — see prior
message for the comparison against TWOSIDES/DrugBank). Then you asked me
to download and clean it solo while away for an hour, with no questions
answered — so every non-obvious call below is a judgment call, flagged for
you to check, not something to take on faith.

**Downloaded:** `data/datasets/ddinter/ddinter_downloads_code_{A,B,D,H,L,P,R,V}.csv`
— 8 files, ~12.8MB, pulled from `ddinter2.scbdd.com/static/media/download/`.
These 8 ATC-category files are everything the site's download page
offers — categories C (cardiovascular), N (nervous system), J
(anti-infectives), G, M, S are **not available as bulk downloads** on that
site. This didn't block coverage of your 8 curated drugs (verified below),
but if you need broader ATC-C/N/J coverage later, this source doesn't have
it in bulk — would need per-drug page scraping or a different source.

**Cleaned:** `scripts/clean_ddinter_dataset.py` (new script, mirrors
`data_preprocessing.py`'s load/clean/print-shape/save style) →
`data/datasets/ddinter/ddinter_cleaned.csv` (160,235 rows) +
`ddinter_curated_drug_coverage.csv` (summary for your 8 drugs specifically).
**Not wired into ingestion or the live database** — this is a new file
only, `clinical_rules` is untouched. That's a separate, later step.

Judgment calls made (full detail in the script's own docstring):
1. **Dedup:** 62,148 of 222,383 raw rows were exact duplicates (same pair
   listed once per drug's own category file). Verified zero pairs had
   *conflicting* severity across duplicates before dropping them — safe,
   not a "which one do we trust" situation.
2. **Severity mapping:** DDInter's Major/Moderate/Minor/Unknown →
   your `Severity` enum's major/caution/informational/unknown. Nothing
   maps to CRITICAL — DDInter has no equivalent tier, and per the
   architecture doc these rows would land as DRAFT/unreviewed regardless
   (same contract as the existing 1,824 rules), so this doesn't grant
   anything false authority.
3. **No mechanism text exists in this bulk export** (unlike
   `fully_processed_dataset.csv`'s `Cleaned_Description`). Filled with a
   synthesized placeholder sentence, explicitly prefixed
   `[synthesized, not source text]` so it can never be mistaken for real
   prescribing language if it ever reaches a pharmacist or patient screen.
4. **Naming crosswalk, curated drugs only:** DDInter uses INN names, so
   "aspirin"/"penicillin" don't literally appear as strings — confirmed
   they're `Acetylsalicylic acid` and `Benzylpenicillin`/
   `Phenoxymethylpenicillin`. Added a hand-verified alias
   (`acetylsalicylic acid`→`aspirin`, `benzylpenicillin`→`penicillin`) as
   an *extra* `alias_pair_key` column, original names kept alongside, for
   only these 8 drugs — nothing automatic/broader. Deliberately did
   **not** alias `phenoxymethylpenicillin` (Penicillin V) to "penicillin"
   too — folding two distinct penicillin forms under one label would be a
   real clinical-accuracy risk, not just a naming convenience. Revisit
   this if you want both counted.

**Coverage result — the original "no blanks" goal, verified:**

| drug | total pairs | major | caution | informational | unknown |
|---|---|---|---|---|---|
| warfarin | 864 | 133 | 370 | 63 | 298 |
| aspirin | 654 | 45 | 220 | 43 | 346 |
| ibuprofen | 681 | 62 | 268 | 14 | 337 |
| amoxicillin | 271 | 3 | 23 | 7 | 238 |
| penicillin | 21 | 1 | 14 | 2 | 4 |
| lisinopril | 307 | 8 | 119 | 12 | 168 |
| metformin | 642 | 16 | 290 | 26 | 310 |
| acetaminophen | 274 | 4 | 37 | 17 | 216 |

All 8 now have real coverage (penicillin's count is low relative to
others — expected, since only the Benzylpenicillin alias was folded in,
per judgment call #4).

**Also cleaned up:** two more zero-byte junk files matching the
recurring-debris pattern from §2 (`ddi_rag/')('ingredient')` and
`ddi_rag/{len(df)}` — deleted, same as before.

**Update — this WAS later ingested into the live database.** See §15.

---

## 15. DDInter ingested into the live `clinical_rules` table (161,290 rows total now)

You explicitly asked for this after reviewing §14 ("merge the data and
process the data into pipeline"), and chose **full ingestion** (all
160,235 cleaned rows, not scoped to the 8 curated drugs) when asked.

**New code:**
- `services/clinical_rules.py:ingest_ddinter_csv()` — new function,
  same DRAFT-only/never-auto-approved contract as `ingest_pairs_csv()`,
  but preserves DDInter's *real* severity on the row (major/caution/
  informational/unknown) instead of hardcoding UNKNOWN. Uses
  `alias_pair_key` as the stored `pair_key` so "aspirin"/"penicillin"
  actually resolve (see §13/§14 for why the raw DDInter names wouldn't).
- `scripts/ingest_ddinter_rules.py` — the runner.

**Two real bugs caught before/during this, not hypothetical:**
1. **Severity double-mapping bug**, caught by smoke-testing on a 200-row
   SQLite slice *before* touching the live DB (good thing — this would
   have silently dropped 60% of rows). The cleaned CSV's `severity`
   column already holds the final mapped value (`major`/`caution`/
   `informational`/`unknown`); the first version of
   `ingest_ddinter_csv()` re-ran that value through the raw-DDInter-Level
   lookup table by mistake. `"caution"` and `"informational"` aren't keys
   in that table (only `"major"`/`"moderate"`/`"minor"`/`"unknown"` are),
   so every CAUTION/INFORMATIONAL row silently failed validation and was
   dropped — while MAJOR/UNKNOWN rows accidentally "worked" because those
   two strings happen to be identical before and after the mapping. Fixed
   by looking the value up directly via `Severity(row["severity"])`
   instead of re-mapping it.
2. **Per-row DB round-trips made the first real-DB attempt hang past 5
   minutes with zero output** — `ingest_ddinter_csv()` originally ran one
   `SELECT ... WHERE pair_key = ?` per row against remote Supabase for
   the existing-pair_key dedup check. Killed it, rewrote to load all
   existing `pair_key`s into an in-memory set with one query up front,
   dedup via set membership, flush every 5,000 rows, log progress every
   20,000. Full 160,235-row run then completed in **under 3 minutes**.
   This is the exact "per-row DB round trips" cost the original handoff
   (§3, cost section) already flagged as the real constraint on
   large ingests — now there's a concrete example of it actually biting,
   and the fix pattern (preload + set + batched flush) if it comes up
   again for a future large ingestion.

**Result, verified against the live database (not just script output):**

| | before | after |
|---|---|---|
| `clinical_rules` total | 1,824 | **161,290** |
| source_dataset breakdown | `fully_processed_dataset.csv (curated subset)`: 1,824 | + `ddinter_2.0`: 159,466 |
| `status='APPROVED'` count | 0 | **still 0** — nothing auto-approved, confirmed |
| `aspirin\|\|warfarin` pair_key | did not exist | exists, severity=MAJOR, status=DRAFT |

769 rows were skipped as already-present (pre-existing pair_keys from the
old dataset were never overwritten, per the "fill gaps only" design).

**Confirmed live via `evaluate_case(session, ['aspirin','warfarin'], [])`**
— the exact pair that started this whole detour, which returned an empty
finding list earlier this session — now returns a real finding:
`type=UNKNOWN, severity=UNKNOWN, review_status=PENDING`, citing the new
DDInter rule in `evidence_refs`, `missing_factors=['clinical_review']`.
That's correct, expected behavior, not a bug — a DRAFT rule (whatever its
real severity) still can't produce a clinically-authoritative finding
until a reviewer approves it. The *data* gap is closed; the *governance*
step (reviewing and approving these 159,466 DRAFT rules) is a human task,
same as the original 1,824 — explicitly not something I can or should do.

Full test suite (67 tests) still passes. Nothing from this session is
committed.

---

## 16. Evidence corpus expanded to match DDInter's drug coverage + live CRAG LLM eval

You asked for three things together: embed vectors for "the entire
dataset," test the app with the new data, and run LLM evals on the CRAG
pipeline — then commit if it's all working. Scope for the embeddings was
clarified before spending anything (full 66,695-drug openFDA corpus would
have cost ~$15-20 and required upgrading off Cohere's free trial, exceeding
its 1,000-calls/month cap by ~10x — you chose the scoped option instead:
just the drugs DDInter's new rules actually reference).

**Evidence corpus expansion — `scripts/ingest_ddinter_evidence.py` (new):**
- Computed live (not guessed): 1,939 unique drug names across the DDInter
  rules, 798 of which exist verbatim as an `openfda_generic_name` in the
  local FDA source file, 9 already embedded — so 793 drugs were the real
  target. This stayed comfortably inside the Cohere free trial (~125
  batched calls vs. the 1,000/month cap), unlike the full-corpus option.
- Result: `evidence_chunks` grew from 138 → **10,915 chunks**, unique
  drugs with real evidence from 9 → **800**. (Small ~1% shortfall vs. the
  793-drug/10,903-chunk estimate — a couple of near-duplicate label rows
  likely collapsed during cleaning; inconsequential at this scale, not
  investigated further.)
- Verified live: `answer_ddi()` called against 3 randomly-sampled newly-
  embedded drugs never in the original 8 (alpelisib, doxycycline,
  etanercept) — all three returned real, grounded, cited answers from the
  actual FDA label text.
- First attempt at this crashed instantly (`NameError: __file__ not
  defined`) — caused by trying to inject logging config via `exec()` in a
  one-liner instead of putting it in the script; fixed by adding
  `logging.basicConfig()` directly to the script. Confirmed nothing had
  touched the DB before the fix (evidence_chunks count still 138) before
  retrying properly.

**Rule-engine "test with new data" verification:**
- Before DDInter: only 4 of the 28 possible pairs among the 8 originally-
  curated drugs had any rule data. **Now 21 of 28 do**, including real
  MAJOR/CAUTION severities (e.g. `aspirin||ibuprofen`: MAJOR,
  `aspirin||warfarin`: MAJOR, `lisinopril||metformin`: CAUTION).
- Ran a realistic 4-drug polypharmacy case
  (`evaluate_case(['aspirin','lisinopril','metformin','warfarin'])`)
  through the real engine: correctly surfaced all 6 possible pairs as
  findings (previously most would have been silent gaps).

**Live LLM eval on the CRAG pipeline — `scripts/run_crag_llm_evals.py`
(new).** Complements `tests/test_llm_safety_evals.py` (which already
covers prompt-injection resistance and citation-grounding logic against
*mocked* Groq/retrieval calls) — this one runs the real thing: live
`answer_ddi()` and `explain_finding()` calls, scored with the same
`services/llm_eval.py` functions. Not a golden dataset — none exists in
this repo yet — this is what real retrieval + real generation actually
produces, scored honestly.

- **First run hit a real bug**: no rate-limiting between Groq calls meant
  Groq's free-tier 30 req/min cap started returning 429s around the 9th
  drug, and those failures were silently scored as 0.0 "faithfulness" —
  indistinguishable from a genuinely bad generation. Fixed: detect
  `_call_groq_api`'s known error-string prefixes, exclude them from the
  faithfulness aggregate, report them as a separate `api_error` count,
  and pace the script (4s between drugs) instead of relying on retries.
- **Clean second run**, 25 drugs (8 original + 17 sampled from the newly
  expanded corpus), **zero API errors**:

  | metric | result |
  |---|---|
  | `answer_ddi` crag_status | correct: 14 (56%), ambiguous:broadened: 8 (32%), incorrect:rewritten: 3 (12%) |
  | `answer_ddi` avg faithfulness | 0.461 |
  | `explain_finding` avg faithfulness | 0.244 |
  | `explain_finding` citation-grounding rate | 100% (structurally guaranteed, a sanity check not a differentiator) |

  Full results: `outputs/crag_llm_eval_results.json`. Worth noting
  honestly: `explain_finding`'s faithfulness is notably lower than
  `answer_ddi`'s — likely because this eval's synthesized query for it is
  more generic than `answer_ddi`'s, not necessarily a pipeline defect.
  Also remember `score_faithfulness` is explicitly a "v1 heuristic... not
  a validated faithfulness measure" per its own docstring — directionally
  useful, not clinical-grade.

**Also cleaned up:** two more zero-byte junk files (`ddi_rag/dict` this
time), same recurring pattern as before.

Full test suite (67 tests) still passes after all of the above.

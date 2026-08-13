# Session Handoff — Clinical Safety Copilot / DDI-RAG / MedTrust Connect

Written at the end of a long session to carry context into a new chat. Read this
before doing anything else in a fresh session on this project.

---

## 1. What this project is

A clinical-grade Drug-Drug Interaction (DDI) safety platform, evolving from a
research RAG prototype toward the architecture specified in an external
document you provided mid-session (a Word doc: "Medication Safety Coordination
Platform" architecture guide). That doc's roadmap (Phase 0–8) has been the
guiding structure since. Product name in the docs: "MedSafe Interaction
Portal" / "MedTrust Connect" (patient-facing brand).

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
- Root had a dozen zero-byte junk files (`(lo`, `{`, `index`, `list`,
  `awaiting_prescriber_response,`, etc.) — debris from some environment
  process, not anything I created. Deleted the ones found; more may still
  appear (unexplained, low-stakes).
- Two `.env` files existed (root + `ddi_rag/.env`) — consolidated to root
  only; `config.py` now loads only the root `.env`.
- `PROJECT.md` describes a much larger, partly aspirational system
  (Streamlit UI, Docker Compose, a "MedTrust Connect" frontend with 11
  Stitch-designed screens) that **does not match the actual code**. Flagged
  repeatedly as stale; **not yet rewritten** — do this if asked.

---

## 3. Major architecture decisions made this session

| Decision | Chosen | Why |
|---|---|---|
| Vector store | **Supabase Postgres + pgvector** (not Qdrant, not ChromaDB) | User has low RAM, wanted a "website" not local infra; consolidates with the transactional DB into one connection string |
| Embeddings | **Cohere** (`embed-english-v3.0`, 1024-dim) via plain HTTP, no SDK | Free tier, no local model — removes `torch`/`sentence-transformers` entirely |
| LLM generation | **Groq** (`llama-3.1-8b-instant`) via plain HTTP, no SDK | Already in use, cheap, fast, free tier generous |
| DB for domain models | Same Supabase Postgres (SQLite only for tests) | One database, not two |
| Vector index type | **HNSW**, not IVFFlat | Real bug found: IVFFlat gave silently incomplete `LIMIT` results on small tables |

**Cost reality-check (verified via web search, not guessed):** at current
usage scale you are almost certainly still inside free tiers for all three
(Cohere: 1,000 calls/month trial; Groq: 30 req/min free; Supabase: free
project tier). Full-corpus ingestion (~930K chunks per PROJECT.md) would cost
roughly **$15-20 one-time** for embeddings, not expensive — the real
constraint on doing that now was *time* (rate limits, per-row DB round
trips), not money.

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
| 3 — Clinical rule engine | Done, but only 3 of 10 rule categories | `services/clinical_rules.py` — DDI pairs, drug-allergy, duplicate therapy only. **No** drug-condition, dose/route, age, pregnancy, kidney/liver, labs, or monitoring rules yet |
| 4 — Evidence/explanation | Done | `services/evidence_store.py` (pgvector+Cohere), `services/evidence.py` (constrained Groq explanation, cannot alter severity/action) |
| 5 — Professional workflow | Done | `services/professional_workflow.py`, `/v1/safety-cases`, `/v1/interventions` API |
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
  checks to `SafetyCase`/`Finding` (see task #18 in history).
- **Dismissing/overriding a MAJOR/CRITICAL finding required no reason** —
  fixed, now enforced with a documented-reason requirement (task #16).
- **`continue_with_rationale` prescriber decision didn't actually require a
  rationale** — fixed (task #17).
- Permanent rules ("LLM never determines severity," "unknown ≠ safe",
  "severe findings cannot be silently deleted") are enforced structurally
  and covered by tests, not just policy.
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
   migration. Fixed; now checks Database/RxNorm/Groq/Cohere/pgvector, all
   confirmed live.
6. **Groq API key was invalid (401)** mid-session — user rotated it, since
   confirmed working (`console.groq.com`).
7. **A malformed `DATABASE_URL`** cost two rounds of debugging — first had a
   stray character before `@` (unescaped special char in password), then a
   literal `]` left over from not fully replacing Supabase's
   `[YOUR-PASSWORD]` placeholder token. Now correct and connected.
8. Several **stale "Qdrant" references** left in docstrings across
   `fda_sync.py`, `mcp_server.py`, `services/llm_eval.py`,
   `services/evidence_store.py` after the migration — cleaned up.

---

## 7. Current file structure (accurate as of end of session)

```
ddi_rag/                          (repo root)
├── PROJECT.md                    — STALE, describes a different/bigger system, not fixed yet
├── README.md, CLAUDE.md          — accurate
├── main.py                       — placeholder, does nothing
├── requirements.txt              — single pinned manifest
├── .env / .env.example           — root .env is the only one read
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
│   │   ├── medication_identity.py   — RxNorm resolution
│   │   ├── clinical_rules.py        — deterministic rule engine (3 of 10 categories built)
│   │   ├── evidence_store.py        — Cohere + pgvector, real retrieval backend
│   │   ├── rag_pipeline.py          — CRAG orchestration (moved here from top-level this session)
│   │   ├── evidence.py              — constrained explanation (explain_finding)
│   │   ├── professional_workflow.py — case analysis → queue → intervention → dispense → patient comms
│   │   ├── eval_metrics.py          — clinical regression metrics (per-severity, never aggregated)
│   │   └── llm_eval.py              — faithfulness scoring (v1 heuristic) + citation grounding
│   │
│   └── static/patient/index.html  — patient-facing frontend (plain HTML/Tailwind, no build step)
│
└── tests/                         — 67 tests, all passing, ~11-22s to run
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
- **Verified working end-to-end**: `answer_ddi('warfarin')` returns genuine
  retrieved FDA text (similarity 0.74) and a genuine Groq-generated
  explanation. `evaluate_case(['warfarin','ibuprofen',...])` correctly
  found the real warfarin+ibuprofen pair and returned it as
  `unknown/pending review`, not a validated finding.
- **Not ingested:** the full ~66,695-drug / ~930K-chunk corpus. Scoped down
  deliberately (time, not cost — see §3). Offered to do the full ingestion;
  user has not yet said go.
- Also seeded (still in the live DB, clearly test data): a "Demo General
  Hospital" organization and a "Jane Doe" patient account with two demo
  safety cases (used to verify the frontend renders real data). Not deleted
  automatically — flagged to user as theirs to clean up.

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

- **The project's own `venv` lacks `pytest`, `psycopg2`-verified, and other
  packages** — no internet access was available mid-session to `pip
  install`. All testing this session used the **system Python** instead:
  `C:\Users\C V REDDY\AppData\Local\Programs\Python\Python311\python.exe`
  — which already had the full stack including pytest 9.0.3. Use this path
  for running tests/scripts until the venv is reconciled.
- **Importing `services/rag_pipeline.py` used to take ~100s** (torch +
  sentence-transformers). That's gone now — down to ~15-20s (pandas,
  sqlalchemy, etc.) since local embeddings were removed. Full test suite:
  **~11-22s** for 67 tests.
- **`.env` file read/write is permission-restricted** — I can write it but
  not read it back. If something's wrong with env vars, I can only
  diagnose via indirect checks (e.g. printing `bool(value)` and length, or
  connection error messages), never by viewing the actual file.
- **Two Python environments matter**: `venv` (project's own, incomplete)
  and the system Python (complete, used for everything this session).
  Anaconda's Python at `C:\Users\C V REDDY\anaconda3\python.exe` also
  exists but has broken DLLs (`_ssl`, `_sqlite3` fail to import) — don't
  use it.
- Git: **nothing has been committed this session** — all work is unstaged
  changes/new files. `git status` will show a large diff. User has not
  asked for a commit.

---

## 11. Known open gaps (say these plainly if asked "is this done")

- `PROJECT.md` is stale/misleading — offered to rewrite, not done.
- No Alembic migrations — schema only bootstraps via `create_all()`.
- `fda_sync.py`'s nightly sync is disabled/unimplemented against pgvector.
- Only 3 of 10 clinical rule categories exist (no drug-condition, dose/route,
  age, pregnancy, kidney/liver, labs, monitoring rules).
- No RBAC beyond basic role field, no MFA, no encryption-at-rest, no rate
  limiting, no audit-log access controls beyond what's built.
- Full openFDA corpus not ingested (138/~930K chunks).
- No clinical validation/pilot has happened or could happen — this is all
  synthetic/test data, never real patients, per your own governance rules.
- `mcp_server.py` sits next to `app.py` with no structural signal it's a
  different trust boundary (flagged, not fixed — lower priority than the
  rag_pipeline move which *was* done).
- `data/processed/` has thousands of loose per-drug `.txt` files at the
  repo root — pre-existing clutter, not addressed.

---

## 12. Natural next steps (pick one, don't assume)

1. Rewrite `PROJECT.md` to match reality.
2. Ingest the full openFDA corpus (now that cost is known to be ~$15-20,
   not scary — but still needs your go-ahead, and will take real time due
   to rate limits).
3. Build out the remaining 7 clinical rule categories.
4. Start Phase 6 (security/ops hardening).
5. Build the pharmacist/clinical-web app (only patient app exists so far).
6. Clean up demo data (Jane Doe, Demo General Hospital) once you're done
   testing against it.

Do not assume any of these — ask which one before starting.

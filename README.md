# ddi-rag

Basic skeleton for a RAG-style project with separate data and notebook directories.

## Data

The cleaned DDI dataset (`clean_ddi_dataset.csv`) is too large for GitHub. Download it from Google Drive and place it in `data/` or `src/` before running the ingest notebook:

**[clean_ddi_dataset.csv](https://drive.google.com/file/d/1pvO8-Un6mTetikGciF2hyPmeTIYIT89H/view?usp=drive_link)**

## Structure

- `data/raw` – place original input data files here.
- `data/processed` – place cleaned/processed artifacts here.
- `src/ingest.ipynb` – for data ingestion logic.
- `src/parse.ipynb` – for parsing/feature extraction logic.
- `main.py` – Python entry point for orchestration.

## Setup

```bash
cd ddi_rag
python -m venv venv
venv\Scripts\activate  # on Windows
pip install -r requirements.txt
```

Copy `.env.example` to `.env` in the repository root and fill in `GROQ_API_KEY`,
`COHERE_API_KEY`, `JWT_SECRET_KEY` (32+ random characters), and `DATABASE_URL`.
`ddi_rag/config.py` reads only the root `.env` — there should not be a second
one under `ddi_rag/`.

`DATABASE_URL` must point at a real **PostgreSQL** database with the
`pgvector` extension enabled (e.g. a free Supabase project — run
`create extension if not exists vector;` once in its SQL editor) — the
evidence store (`services/evidence_store.py`) needs it. The rest of the
domain models (`models.py`) still work fine on SQLite, which is what the
test suite uses.

## Running the API

```bash
cd ddi_rag
python app.py
```

This creates the database tables (if missing) and starts the Flask API on
`http://0.0.0.0:5000` (`PORT` env var to change it). Confirm it's up with:

```bash
curl http://localhost:5000/api/health
```

## Running tests

```bash
python -m pytest tests/
```

## Known limitations (as of the last engineering pass)

- No Alembic migrations yet — the schema bootstraps via `Base.metadata.create_all()`.
  Safe for a fresh SQLite dev database; do not rely on it for schema evolution
  against a populated database.
- `fda_sync.py`'s sync functions are intentionally disabled (`NotImplementedError`) —
  they targeted ChromaDB, which was removed, and the sync path was never
  re-implemented against the current Postgres/pgvector evidence store. The
  openFDA fetch/parse helpers in that file are still valid and reusable.
- RBAC (role-gated actions), MFA, encryption-at-rest, and rate limiting are not
  implemented. Tenant isolation (an org cannot see/act on another org's cases)
  *is* enforced and tested.
- The evidence store (`services/evidence_store.py`) needs a real Postgres+pgvector
  `DATABASE_URL` and a working `COHERE_API_KEY` to actually retrieve/store evidence —
  neither is live in this environment. Everything is unit-tested with those calls
  mocked; end-to-end testing needs real credentials (e.g. a Supabase project).
- No local embedding model anymore (this was `sentence-transformers`/`torch` —
  removed in favor of Cohere's hosted embed API), which also means importing
  `rag_pipeline.py` is now fast (~20s, mostly pandas/sqlalchemy) instead of
  the ~100s it used to take.

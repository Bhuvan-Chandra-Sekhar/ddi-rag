"""
config.py — Central configuration for the DDI-RAG system.
All tunable constants and secrets are loaded here so every other module
imports from a single source of truth.

Secrets come from exactly one .env file: the repository root's .env.
ddi_rag/.env is not loaded — consolidate any values from it into the root
file (see .env.example for the expected keys), then remove it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_CSV   = os.getenv("DDI_DATA_CSV", "./data/clean_ddi_dataset.csv")
CHROMA_DIR = os.getenv("DDI_CHROMA_DIR", "./chroma_ddi_db")   # used by fda_sync.py only

# ── Vector store — Postgres + pgvector (Supabase), see services/evidence_store.py ──
# Uses the same DATABASE_URL as the rest of the app — one database, not a
# separate vector service to lose track of. Requires a real Postgres
# connection with the pgvector extension enabled; SQLite cannot host this.
COLLECTION_NAME  = "fda_drug_labels"
CHUNK_SIZE       = 120   # words per chunk
CHUNK_OVERLAP    = 30    # word overlap between consecutive chunks
EMBED_BATCH_SIZE = 96    # Cohere embed API batch limit is 96 texts/request

# ── Embeddings (Cohere — hosted, no local model/torch needed) ────────────────
COHERE_API_KEY    = os.getenv("COHERE_API_KEY", "")
COHERE_EMBED_MODEL = os.getenv("COHERE_EMBED_MODEL", "embed-english-v3.0")
COHERE_EMBED_DIM   = 1024   # output dimension of embed-english-v3.0
COHERE_TIMEOUT     = 15

# ── LLM (Groq) ────────────────────────────────────────────────────────────────
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
# llama-3.1-8b-instant was decommissioned from Groq's catalog at some point
# after this project was first built — confirmed live via GET /openai/v1/models
# (2026-08-17): it's no longer in the list, and every chat completion against
# it now 404s. openai/gpt-oss-20b is Groq's current closest equivalent (small,
# fast, general-purpose instruct model) — verified working live before this
# default was changed. If Groq's catalog changes again, GET
# https://api.groq.com/openai/v1/models with your key to see what's current.
GROQ_MODEL         = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_TIMEOUT       = 30
GENERATION_MAX_NEW = 512

SYSTEM_PROMPT = (
    "You are a clinical pharmacist specialising in drug-drug interactions. "
    "Using ONLY the FDA label excerpts and structured interaction data below, "
    "explain the interaction risks, contraindications, and warnings. "
    "Do not invent facts. Do not make autonomous prescribing decisions."
)
GENERAL_SYSTEM_PROMPT = (
    "You are a general medical information assistant. Answer clearly and "
    "conservatively, and advise the user to consult a licensed clinician for "
    "personal medical decisions."
)

# ── Flask / API ───────────────────────────────────────────────────────────────
PORT                 = int(os.getenv("PORT", 5000))
MAX_PRESCRIPTION_LEN = 1_000
DEFAULT_TOP_K        = 5
MAX_TOP_K            = 10

# CORS — restrict to actual known origins rather than allowing any site to
# call the API cross-origin. Both frontends (static/patient, static/clinical)
# are served by this SAME Flask app, so legitimate browser traffic is
# same-origin already and doesn't need CORS at all; this only matters for a
# separately-hosted frontend or direct API callers. Comma-separated in
# ALLOWED_ORIGINS if you deploy one; defaults cover the live Render URL and
# local dev.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS",
        "https://ddi-rag.onrender.com,http://localhost:5000,http://127.0.0.1:5000",
    ).split(",") if o.strip()
]

# Rate limiting — /api/query, /api/self-check, /api/explain are reachable
# with no login (self-check/explain by design; query works unauthenticated
# too), so with no per-IP throttle a single bad actor can burn through the
# Cohere/Groq free-tier quota for everyone. In-memory limiter (no Redis
# needed) keyed by remote address — resets on process restart, which is an
# acceptable tradeoff for a single-instance deployment like this one.
RATE_LIMIT_PER_MINUTE = os.getenv("RATE_LIMIT_PER_MINUTE", "20 per minute")
RATE_LIMIT_PER_DAY    = os.getenv("RATE_LIMIT_PER_DAY", "500 per day")

# ── Guest self-check (routes_public.py) — no login required, so these bound
# the worst case cost of a single unauthenticated request (RxNorm lookups
# are sequential/network-bound; each finding explanation is one Cohere +
# one Groq call) ────────────────────────────────────────────────────────────
MAX_SELF_CHECK_ITEMS = 8     # max medications, and separately max allergies
MAX_ITEM_LEN         = 200   # max chars per medication/allergy name
MAX_NOTES_LEN        = 600   # max chars in the free-text "anything else" field

# ── Auth ──────────────────────────────────────────────────────────────────────
JWT_SECRET_KEY        = os.getenv("JWT_SECRET_KEY", "")
JWT_ACCESS_TOKEN_MINS = 1440   # 24 hours
BCRYPT_ROUNDS         = 12

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./drugsafe.db")

# ── RAG columns ───────────────────────────────────────────────────────────────
TEXT_COLS = [
    "drug_interactions",
    "warnings",
    "adverse_reactions",
    "contraindications",
    "clinical_pharmacology",
]

# ── Drug-name fuzzy matching ──────────────────────────────────────────────────
FUZZY_CUTOFF = 0.82
MIN_ROOT_LEN = 6

# ── openFDA sync (fda_sync.py) ────────────────────────────────────────────────
OPENFDA_BASE_URL  = "https://api.fda.gov/drug/label.json"
OPENFDA_PAGE_SIZE = 100
# Free, self-serve key from open.fda.gov/apis/authentication — raises the
# rate limit from 1,000 requests/day (per IP, unauthenticated) to 120,000/day.
# Used by scripts/mine_ddi_pairs_from_fda_labels.py to pull complete label
# text; that script still works without a key, just capped at 1,000/day.
OPENFDA_API_KEY   = os.getenv("OPENFDA_API_KEY", "")
SYNC_HOUR         = 2   # nightly sync at 2 AM UTC

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
GROQ_MODEL         = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
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
SYNC_HOUR         = 2   # nightly sync at 2 AM UTC

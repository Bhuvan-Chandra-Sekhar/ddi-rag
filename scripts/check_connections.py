"""
scripts/check_connections.py — Verify external service connectivity and
credentials without ever printing secret values.

Run it yourself anytime:
    python scripts/check_connections.py

Checks:
    - Database       (DATABASE_URL)                 — can we connect? Postgres?
    - RxNorm (NLM)   (no key needed)                — public API reachable?
    - Groq API       (GROQ_API_KEY)                 — key still valid?
    - Cohere API     (COHERE_API_KEY)                — key still valid, embeddings work?
    - Evidence store (pgvector on DATABASE_URL)      — extension + table present?
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

import requests

from config import COHERE_API_KEY, DATABASE_URL, GROQ_API_KEY, GROQ_MODEL

RESULTS = []


def check(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    status = "UP  " if ok else "DOWN"
    print(f"[{status}] {name} — {detail}")


def check_cohere() -> None:
    if not COHERE_API_KEY:
        check("Cohere API", False, "COHERE_API_KEY not set in .env")
        return
    try:
        from services.evidence_store import embed_texts
        vectors = embed_texts(["connection check"], input_type="search_query")
        check("Cohere API", bool(vectors), f"key valid, embedding dim={len(vectors[0])}" if vectors else "no vectors returned")
    except Exception as exc:
        check("Cohere API", False, f"{type(exc).__name__}: {exc}")


def check_evidence_store() -> None:
    if not DATABASE_URL.startswith("postgres"):
        check("Evidence store (pgvector)", False, "DATABASE_URL is not PostgreSQL — pgvector needs real Postgres")
        return
    try:
        from services.evidence_store import _get_connection
        conn = _get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
                has_ext = cur.fetchone() is not None
                cur.execute("SELECT COUNT(*) FROM evidence_chunks;")
                count = cur.fetchone()[0]
            check("Evidence store (pgvector)", has_ext, f"pgvector extension {'present' if has_ext else 'MISSING'}, {count} chunks stored")
        finally:
            conn.close()
    except Exception as exc:
        check("Evidence store (pgvector)", False, f"{type(exc).__name__}: {exc}")


def check_groq() -> None:
    if not GROQ_API_KEY:
        check("Groq API", False, "GROQ_API_KEY not set in .env")
        return
    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            models = [m["id"] for m in resp.json().get("data", [])]
            have_model = GROQ_MODEL in models
            check("Groq API", True, f"key valid, {len(models)} models visible, "
                                     f"configured model {GROQ_MODEL} {'found' if have_model else 'NOT FOUND'}")
        elif resp.status_code == 401:
            check("Groq API", False, "401 Unauthorized — key is invalid or revoked")
        else:
            check("Groq API", False, f"HTTP {resp.status_code}")
    except Exception as exc:
        check("Groq API", False, f"{type(exc).__name__}: {exc}")


def check_rxnorm() -> None:
    try:
        resp = requests.get(
            "https://rxnav.nlm.nih.gov/REST/rxcui.json",
            params={"name": "warfarin", "search": 1}, timeout=10,
        )
        ok = resp.status_code == 200 and bool(
            resp.json().get("idGroup", {}).get("rxnormId")
        )
        check("RxNorm (NLM)", ok, "resolved 'warfarin' to an RxCUI" if ok else f"HTTP {resp.status_code}")
    except Exception as exc:
        check("RxNorm (NLM)", False, f"{type(exc).__name__}: {exc}")


def check_database() -> None:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        check("Database", True, f"connected ({DATABASE_URL.split('://')[0]})")
    except Exception as exc:
        check("Database", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    print("Checking external connections (no secret values are printed)...\n")
    check_database()
    check_rxnorm()
    check_groq()
    check_cohere()
    check_evidence_store()

    print("\nSummary:")
    for name, ok, _ in RESULTS:
        print(f"  {'✓' if ok else '✗'} {name}")

    if not all(ok for _, ok, _ in RESULTS):
        sys.exit(1)

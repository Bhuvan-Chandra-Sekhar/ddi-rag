"""
services/evidence_store.py — Postgres + pgvector evidence store, Cohere embeddings.

Deliberately kept on its own psycopg2 connection, separate from models.py's
SQLAlchemy Base/engine. pgvector's column type only exists on real Postgres,
while the rest of the domain model is tested against throwaway SQLite
databases — mixing them would make every unit test require a live Postgres
connection just to create tables.

No `cohere` or `pgvector` Python package dependency: Cohere is called over
plain HTTP with `requests` (matching how rag_pipeline.py already calls
Groq), and the vector column is handled with hand-written SQL + a small
literal-formatting helper instead of the `pgvector` SQLAlchemy type.
"""

import logging
from typing import List, Optional

import pandas as pd
import psycopg2
import psycopg2.extras
import requests

from config import (
    COHERE_API_KEY, COHERE_EMBED_DIM, COHERE_EMBED_MODEL, COHERE_TIMEOUT,
    DATABASE_URL, EMBED_BATCH_SIZE,
)

log = logging.getLogger("ddi.evidence_store")

_COHERE_EMBED_URL = "https://api.cohere.com/v2/embed"
_TABLE = "evidence_chunks"


def _to_pgvector_literal(embedding: List[float]) -> str:
    """Format a Python float list as a pgvector literal string, e.g.
    '[0.1,0.2,0.3]' — avoids needing the `pgvector` package's type adapter."""
    return "[" + ",".join(repr(float(v)) for v in embedding) + "]"


def embed_texts(texts: List[str], input_type: str = "search_document") -> List[List[float]]:
    """
    Call Cohere's embed API.

    input_type is "search_document" when embedding corpus text and
    "search_query" when embedding a user query — Cohere embeds these
    differently for retrieval quality, so getting this right matters.
    """
    if not COHERE_API_KEY:
        raise RuntimeError("COHERE_API_KEY is not set.")
    if not texts:
        return []

    headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": COHERE_EMBED_MODEL,
        "texts": texts,
        "input_type": input_type,
        "embedding_types": ["float"],
    }
    response = requests.post(_COHERE_EMBED_URL, headers=headers, json=payload, timeout=COHERE_TIMEOUT)
    response.raise_for_status()
    return response.json()["embeddings"]["float"]


def _get_connection():
    if not DATABASE_URL or not DATABASE_URL.startswith("postgres"):
        raise RuntimeError(
            "DATABASE_URL must be a PostgreSQL connection string (e.g. from "
            "Supabase) for the evidence store — SQLite cannot support pgvector."
        )
    return psycopg2.connect(DATABASE_URL)


def init_evidence_store() -> None:
    """Create the pgvector extension and evidence_chunks table if missing.
    Call once at startup. Postgres only — raises on SQLite."""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    id            TEXT PRIMARY KEY,
                    generic_name  TEXT,
                    brand_name    TEXT,
                    product_type  TEXT,
                    route         TEXT,
                    section       TEXT,
                    text          TEXT NOT NULL,
                    embedding     vector({COHERE_EMBED_DIM}) NOT NULL
                );
            """)
            # HNSW, not IVFFlat: IVFFlat is an approximate index that needs a
            # `lists` parameter tuned to the table size and gives incomplete/
            # wrong ORDER BY ... LIMIT results on small tables — a real,
            # observed failure mode here (silently dropping relevant
            # evidence), not a hypothetical one. HNSW doesn't have this
            # problem and needs no tuning to behave correctly at any size.
            cur.execute(f"DROP INDEX IF EXISTS {_TABLE}_embedding_idx;")
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {_TABLE}_embedding_hnsw_idx
                ON {_TABLE} USING hnsw (embedding vector_cosine_ops);
            """)
        conn.commit()
        log.info("Evidence store ready (table=%s).", _TABLE)
    finally:
        conn.close()


def upsert_chunks(chunk_df: pd.DataFrame) -> int:
    """Embed and upsert a chunk_df (as built by services.rag_pipeline.build_chunk_df)
    into the evidence store. Returns the number of rows upserted.

    Embeds in batches of EMBED_BATCH_SIZE — Cohere's embed API caps requests
    at 96 texts each; sending everything in one call would fail or silently
    truncate once a real corpus (hundreds+ chunks) is ingested."""
    if chunk_df.empty:
        return 0

    conn = _get_connection()
    total = 0
    try:
        with conn.cursor() as cur:
            for start in range(0, len(chunk_df), EMBED_BATCH_SIZE):
                batch = chunk_df.iloc[start:start + EMBED_BATCH_SIZE]
                embeddings = embed_texts(batch["text"].tolist(), input_type="search_document")

                for (_, row), embedding in zip(batch.iterrows(), embeddings):
                    cur.execute(
                        f"""
                        INSERT INTO {_TABLE}
                            (id, generic_name, brand_name, product_type, route, section, text, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                        ON CONFLICT (id) DO UPDATE SET
                            generic_name = EXCLUDED.generic_name,
                            brand_name   = EXCLUDED.brand_name,
                            product_type = EXCLUDED.product_type,
                            route        = EXCLUDED.route,
                            section      = EXCLUDED.section,
                            text         = EXCLUDED.text,
                            embedding    = EXCLUDED.embedding;
                        """,
                        (
                            row["doc_id"], row.get("generic_name"), row.get("brand_name"),
                            row.get("product_type"), row.get("route"), row.get("section"),
                            row["text"], _to_pgvector_literal(embedding),
                        ),
                    )
                conn.commit()
                total += len(batch)
                log.info("Upserted batch: %d / %d chunks", total, len(chunk_df))
        return total
    finally:
        conn.close()


def search(
    query: str,
    top_k: int = 5,
    drug_name: Optional[str] = None,
    section: Optional[str] = None,
) -> pd.DataFrame:
    """
    Embed `query` and return the top_k most similar chunks as a DataFrame
    shaped exactly like the old Qdrant-backed retrieve_chunks() output:
    generic_name, brand_name, product_type, route, section, text, score.

    Returns an empty DataFrame on any failure (missing config, connection
    error, embedding API error) rather than raising — evidence retrieval
    failing must not take down the caller.
    """
    try:
        embedding = embed_texts([query], input_type="search_query")[0]
        vector_literal = _to_pgvector_literal(embedding)

        filters, filter_params = [], []
        if drug_name:
            filters.append("generic_name = %s")
            filter_params.append(drug_name.strip().lower())
        if section:
            filters.append("section = %s")
            filter_params.append(section.strip().lower())
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        sql = f"""
            SELECT generic_name, brand_name, product_type, route, section, text,
                   1 - (embedding <=> %s::vector) AS score
            FROM {_TABLE}
            {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        params = [vector_literal, *filter_params, vector_literal, top_k]

        conn = _get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([dict(r) for r in rows])

    except Exception:
        log.exception("Evidence store search failed for query=%r", query)
        return pd.DataFrame()

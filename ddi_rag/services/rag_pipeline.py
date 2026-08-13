"""
services/rag_pipeline.py — Postgres/pgvector evidence store (via
services/evidence_store.py) + CRAG pipeline + Groq LLM generation.

CRAG (Corrective RAG) enhances standard RAG with a relevance grading step:
    1. Retrieve   — fetch top-K chunks from the evidence store
    2. Grade      — score retrieval quality (correct / ambiguous / incorrect)
    3. Correct    — apply corrective action based on grade:
                    correct   → use chunks as-is
                    ambiguous → broaden search, merge and re-rank results
                    incorrect → rewrite query via Groq, retry retrieval
    4. Generate   — produce answer using verified, high-quality context

Embeddings are computed by Cohere's hosted API (services/evidence_store.py) —
no local model, no torch. There is no load_models() step anymore; the
embedding "model" is just an HTTP call.

Public API:
    retrieve_chunks(query, top_k, drug_name, section)      — evidence-store retrieval
    answer_ddi(drug_name, section, top_k, history_context) — full CRAG pipeline
    answer_general(query, history_context)                 — general assistant (no retrieval)
"""

import logging
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from config import (
    CHUNK_OVERLAP, CHUNK_SIZE, DEFAULT_TOP_K,
    GENERAL_SYSTEM_PROMPT, GENERATION_MAX_NEW, GROQ_API_KEY, GROQ_MODEL, GROQ_TIMEOUT,
    MAX_TOP_K, SYSTEM_PROMPT, TEXT_COLS,
)
from services import evidence_store

# ── RxNorm API (structured DDI fallback — no local storage required) ──────────
_RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
_RXNORM_TIMEOUT = 5

log = logging.getLogger("ddi.crag")

# ── CRAG relevance thresholds ─────────────────────────────────────────────────
RELEVANCE_HIGH = 0.65   # score ≥ this → "correct"  (use chunks as-is)
RELEVANCE_LOW  = 0.40   # score < this → "incorrect" (rewrite query + retry)
                         # between the two  → "ambiguous" (broaden search)

# Control-character stripper
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def safe_str(val) -> str:
    return _CTRL.sub("", str(val) if val is not None else "")


# ── Chunking ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> List[str]:
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        end   = min(start + CHUNK_SIZE, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def build_chunk_df(df: pd.DataFrame) -> pd.DataFrame:
    valid_cols = [c for c in TEXT_COLS if c in df.columns]
    documents: List[Dict] = []

    for idx, row in df.iterrows():
        generic_name = safe_str(row.get("final_generic_name", "") or "").strip()
        brand_name   = safe_str(row.get("openfda_brand_name",  "") or "").strip()
        product_type = safe_str(row.get("openfda_product_type","") or "").strip()
        route        = safe_str(row.get("openfda_route",       "") or "").strip()

        for col in valid_cols:
            section_content = row.get(col, "")
            if pd.isna(section_content) or not str(section_content).strip():
                continue
            text = f"{col.replace('_', ' ').title()}: {section_content}"
            for ci, chunk in enumerate(_chunk_text(text)):
                documents.append({
                    "doc_id": f"{idx}_{col}_{ci}", "generic_name": generic_name,
                    "brand_name": brand_name, "product_type": product_type,
                    "route": route, "section": col, "text": chunk,
                })

    chunk_df = pd.DataFrame(documents)
    log.info("Built chunk_df: %d chunks from %d rows.", len(chunk_df), len(df))
    return chunk_df


# ── Base retrieval ────────────────────────────────────────────────────────────

def retrieve_chunks(
    query     : str,
    top_k     : int           = DEFAULT_TOP_K,
    drug_name : Optional[str] = None,
    section   : Optional[str] = None,
) -> pd.DataFrame:
    """
    Query the pgvector evidence store for the top-k most relevant chunks.
    Returns a DataFrame with: generic_name, brand_name, section, text, score.
    Delegates to services.evidence_store.search(), which already fails
    closed to an empty DataFrame on any error (missing config, connection
    failure, embedding API error) — evidence retrieval failing must not
    take down the caller.
    """
    chunks = evidence_store.search(
        query=query, top_k=min(top_k, MAX_TOP_K), drug_name=drug_name, section=section,
    )
    if chunks.empty:
        return chunks
    return chunks.assign(
        generic_name=chunks["generic_name"].map(safe_str),
        brand_name=chunks["brand_name"].map(safe_str),
        product_type=chunks["product_type"].map(safe_str),
        route=chunks["route"].map(safe_str),
        section=chunks["section"].map(safe_str),
        text=chunks["text"].map(safe_str),
        score=chunks["score"].astype(float).round(4),
    )


# ── CRAG components ───────────────────────────────────────────────────────────

def _grade_retrieval(chunks: pd.DataFrame) -> str:
    """
    Evaluate retrieval quality based on cosine similarity scores.

    Returns:
        'correct'   — top chunk score ≥ RELEVANCE_HIGH  → use as-is
        'ambiguous' — score between thresholds           → broaden search
        'incorrect' — top chunk score < RELEVANCE_LOW    → rewrite query
    """
    if chunks.empty:
        return "incorrect"

    best_score = float(chunks["score"].max())

    if best_score >= RELEVANCE_HIGH:
        grade = "correct"
    elif best_score < RELEVANCE_LOW:
        grade = "incorrect"
    else:
        grade = "ambiguous"

    log.info("CRAG grade: %s (best_score=%.4f)", grade, best_score)
    return grade


def _rewrite_query(original_query: str) -> str:
    """
    CRAG corrective action for 'incorrect' grade.
    Uses Groq to rephrase the query for better vector retrieval.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a query rewriter for a medical FDA drug database. "
                "Rewrite the given query to be more specific, using correct "
                "pharmacological terminology to improve search results. "
                "Return only the rewritten query — no explanation."
            ),
        },
        {"role": "user", "content": f"Original query: {original_query}"},
    ]
    rewritten = _call_groq_api(messages, temperature=0.3, max_tokens=80)
    log.info("CRAG query rewrite: '%s' → '%s'", original_query, rewritten)
    return rewritten


def _crag_retrieve(
    query     : str,
    drug_name : Optional[str],
    section   : Optional[str],
    top_k     : int,
) -> Tuple[pd.DataFrame, str]:
    """
    Full CRAG retrieval pipeline.

    Returns:
        (chunks DataFrame, retrieval_status string)

    Retrieval status values:
        'correct'                 — high confidence, used as-is
        'ambiguous:broadened'     — merged narrow + broad search results
        'incorrect:rewritten'     — query rewritten, retried globally
        'incorrect:no_evidence'   — no relevant chunks found after correction
    """
    # ── Step 1: Initial retrieval ─────────────────────────────────────────────
    chunks = retrieve_chunks(query, top_k, drug_name, section)
    grade  = _grade_retrieval(chunks)

    # ── Step 2a: Correct — high confidence ───────────────────────────────────
    if grade == "correct":
        return chunks, "correct"

    # ── Step 2b: Ambiguous — broaden search ───────────────────────────────────
    if grade == "ambiguous":
        log.info("CRAG ambiguous — broadening search (no metadata filter).")
        broad = retrieve_chunks(query, top_k * 2)   # no drug_name/section filter

        if not broad.empty:
            # Merge narrow + broad results, deduplicate, re-rank by score
            combined = (
                pd.concat([chunks, broad])
                .drop_duplicates(subset=["text"])
                .sort_values("score", ascending=False)
                .head(top_k)
                .reset_index(drop=True)
            )
            return combined, "ambiguous:broadened"

        return chunks, "ambiguous:broadened"   # fallback to original if broad empty

    # ── Step 2c: Incorrect — rewrite query + global retry ────────────────────
    log.info("CRAG incorrect — rewriting query and retrying globally.")
    rewritten      = _rewrite_query(query)
    retry_chunks   = retrieve_chunks(rewritten, top_k)   # global search, no filters
    retry_grade    = _grade_retrieval(retry_chunks)

    if retry_grade != "incorrect":
        return retry_chunks, "incorrect:rewritten"

    # Last resort: return whatever we have
    best = retry_chunks if not retry_chunks.empty else chunks
    status = "incorrect:no_evidence" if best.empty else "incorrect:rewritten"
    return best, status


# ── RxNorm identity lookup ────────────────────────────────────────────────────
# Note: RxNav's drug-drug interaction endpoints (interaction/list.json,
# interaction/interaction.json) were discontinued by NLM on 2024-01-02 and are
# no longer a valid safety signal — do not resurrect them as an interaction
# fallback. _rxnorm_get_rxcui() remains valid for drug *identity* resolution
# (RxCUI normalization) and is used by the medication-identity service.

@lru_cache(maxsize=512)
def _rxnorm_get_rxcui(drug_name: str) -> Optional[str]:
    """Resolve a drug name to an RxCUI identifier via the NLM RxNorm API."""
    try:
        r = requests.get(
            f"{_RXNORM_BASE}/rxcui.json",
            params={"name": drug_name, "search": 1},
            timeout=_RXNORM_TIMEOUT,
        )
        data = r.json()
        rxcui = data.get("idGroup", {}).get("rxnormId", [None])[0]
        if rxcui:
            return rxcui
        # Approximate match fallback
        r2 = requests.get(
            f"{_RXNORM_BASE}/approximateTerm.json",
            params={"term": drug_name, "maxEntries": 1},
            timeout=_RXNORM_TIMEOUT,
        )
        candidates = r2.json().get("approximateGroup", {}).get("candidate", [])
        return candidates[0]["rxcui"] if candidates else None
    except Exception:
        return None


# ── Groq API generation ───────────────────────────────────────────────────────

def _call_groq_api(
    messages   : list,
    temperature: float = 0.4,
    max_tokens : int   = None,
) -> str:
    """Send a messages list to Groq API and return the reply string."""
    if not GROQ_API_KEY:
        return (
            "GROQ_API_KEY not configured. "
            "Add GROQ_API_KEY to your .env file or Streamlit secrets."
        )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    messages,
        "max_tokens":  max_tokens or GENERATION_MAX_NEW,
        "temperature": temperature,
        "stream":      False,
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers = headers,
            json    = payload,
            timeout = GROQ_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return safe_str(data["choices"][0]["message"]["content"]).strip()

    except requests.Timeout:
        log.error("Groq API timed out after %ds", GROQ_TIMEOUT)
        return "Generation timed out. Please try again."
    except Exception as exc:
        log.exception("Groq API call failed")
        return f"Generation error: {safe_str(exc)}"


# ── General assistant (no retrieval) ─────────────────────────────────────────

@lru_cache(maxsize=256)
def answer_general(
    query          : str,
    history_context: str = "",
) -> Dict:
    """General medical assistant mode — no CRAG retrieval."""
    med_block = (
        f"\nPatient's current medications:\n{history_context}\n"
        if history_context else ""
    )
    messages = [
        {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
        {"role": "user",   "content": f"{med_block}\nQuestion: {query}"},
    ]
    answer = _call_groq_api(messages, temperature=0.5, max_tokens=600)
    return {"answer": answer, "sources": []}


# ── Full CRAG pipeline ────────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def _cached_answer(
    drug_name      : Optional[str],
    section        : Optional[str],
    top_k          : int,
    history_context: str,
) -> Dict:
    query = f"What are the drug interactions and warnings for {drug_name}?"

    # ── CRAG: retrieve + grade + correct ─────────────────────────────────────
    retrieved, crag_status = _crag_retrieve(
        query     = query,
        drug_name = drug_name,
        section   = section,
        top_k     = top_k,
    )

    log.info("CRAG status: %s | chunks: %d", crag_status, len(retrieved))

    if retrieved.empty:
        return {
            "answer"     : (
                "No relevant FDA label evidence found for this drug. "
                "Please consult a licensed pharmacist or physician."
            ),
            "sources"    : [],
            "crag_status": crag_status,
        }

    # ── Build prompt with top-3 verified chunks ──────────────────────────────
    fda_context = "\n".join(
        f"[{i}] {row['section'].replace('_',' ').title()}: {row['text'][:300]}"
        for i, (_, row) in enumerate(retrieved.head(3).iterrows(), 1)
    )

    med_block = (
        f"Patient's current medications:\n{history_context}\n\n"
        if history_context else ""
    )

    context = fda_context

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{med_block}"
                f"Evidence (CRAG status={crag_status}):\n{context}\n\n"
                f"Q: {query}\n\n"
                "Important: Explain the evidence. Do not make autonomous prescribing decisions."
            ),
        },
    ]

    answer = _call_groq_api(messages)

    return {
        "answer"     : answer,
        "crag_status": crag_status,
        "sources"    : [
            {
                "generic_name": safe_str(r.get("generic_name", "")),
                "brand_name"  : safe_str(r.get("brand_name",   "")),
                "product_type": safe_str(r.get("product_type", "")),
                "route"       : safe_str(r.get("route",        "")),
                "section"     : safe_str(r.get("section",      "")),
                "score"       : float(r.get("score", 0.0)),
                "text"        : safe_str(r.get("text",         "")),
            }
            for _, r in retrieved.iterrows()
        ],
    }


def answer_ddi(
    drug_name      : Optional[str] = None,
    section        : str           = "drug_interactions",
    top_k          : int           = DEFAULT_TOP_K,
    history_context: str           = "",
) -> Dict:
    """
    Full CRAG pipeline: retrieve → grade → correct → generate via Groq.

    Returns:
        {
            "answer"     : str,
            "sources"    : list[dict],
            "crag_status": str   # 'correct' | 'ambiguous:broadened' |
                                 # 'incorrect:rewritten' | 'incorrect:no_evidence'
        }
    """
    return _cached_answer(
        drug_name       = drug_name,
        section         = section,
        top_k           = min(top_k, MAX_TOP_K),
        history_context = history_context,
    )

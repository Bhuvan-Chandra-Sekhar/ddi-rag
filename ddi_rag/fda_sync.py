"""
fda_sync.py — Incremental sync from openFDA API.

STATUS: sync execution is currently disabled. This module was written
against a local ChromaDB index; the evidence store has since moved to
Postgres/pgvector (services/evidence_store.py, via Cohere embeddings),
and this module was never ported to sync against it. run_sync() and
start_scheduler() raise NotImplementedError rather than silently doing
nothing or crashing on import — reimplementing sync against the
evidence store is tracked as follow-up work, not attempted here (a
one-time manual ingestion path exists separately in scripts/).

The openFDA fetch/parse helpers below (_fetch_page, _parse_label) are
still valid and reusable once a pgvector-backed upsert path exists.
"""

import logging
import os
from datetime import date
from typing import Optional

import requests

from config import (
    COLLECTION_NAME, OPENFDA_BASE_URL, OPENFDA_PAGE_SIZE, SYNC_HOUR, TEXT_COLS,
)
from data_preprocessing import clean_text

log = logging.getLogger("ddi.sync")

# File to persist the last successful sync date
_SYNC_STATE_FILE = os.path.join(os.path.dirname(__file__), ".last_sync_date")


# ── Sync state ────────────────────────────────────────────────────────────────

def _load_last_sync_date() -> Optional[str]:
    """Return the last sync date as 'YYYYMMDD' string, or None."""
    try:
        if os.path.exists(_SYNC_STATE_FILE):
            with open(_SYNC_STATE_FILE) as f:
                return f.read().strip() or None
    except Exception:
        pass
    return None


def _save_last_sync_date(date_str: str):
    try:
        with open(_SYNC_STATE_FILE, "w") as f:
            f.write(date_str)
    except Exception as exc:
        log.warning("Could not save sync date: %s", exc)


# ── openFDA fetching ──────────────────────────────────────────────────────────

def _fetch_page(since: Optional[str], skip: int) -> dict:
    """
    Fetch one page of drug labels from openFDA.

    Args:
        since: 'YYYYMMDD' string — fetch labels updated on or after this date.
               None = fetch all (full sync, use sparingly).
        skip:  pagination offset
    """
    params = {"limit": OPENFDA_PAGE_SIZE, "skip": skip}

    if since:
        today = date.today().strftime("%Y%m%d")
        params["search"] = f"effective_time:[{since}+TO+{today}]"

    try:
        resp = requests.get(OPENFDA_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return {}   # no results for this date range
        raise
    except Exception as exc:
        log.error("openFDA fetch failed (skip=%d): %s", skip, exc)
        return {}


def _parse_label(record: dict) -> Optional[dict]:
    """
    Extract relevant fields from one openFDA drug label record.
    Returns None if the record has no useful drug data.
    """
    openfda = record.get("openfda", {})

    generic_names = openfda.get("generic_name", [])
    brand_names   = openfda.get("brand_name",   [])
    product_types = openfda.get("product_type", [])
    routes        = openfda.get("route",        [])

    generic_name = clean_text(generic_names[0], "openfda_generic_name") if generic_names else ""
    brand_name   = clean_text(brand_names[0],   "openfda_brand_name")   if brand_names   else generic_name
    product_type = clean_text(product_types[0], "openfda_product_type") if product_types else ""
    route        = clean_text(routes[0],        "openfda_route")        if routes        else ""

    if not generic_name:
        return None

    row = {
        "final_generic_name":   generic_name,
        "openfda_brand_name":   brand_name or generic_name,
        "openfda_product_type": product_type,
        "openfda_route":        route,
    }

    for col in TEXT_COLS:
        values   = record.get(col, [])
        raw_text = " ".join(values).strip() if values else ""
        row[col] = clean_text(raw_text, col_name=col)

    # Fill missing warnings to match CSV behaviour
    if not row.get("warnings"):
        row["warnings"] = "no warning from <fda data>"

    # Only keep records that have at least one useful text section
    if not any(row.get(c, "") for c in TEXT_COLS):
        return None

    return row


# ── Main sync entry point ─────────────────────────────────────────────────────

def run_sync(full: bool = False) -> dict:
    """
    Disabled. This function used to delete/upsert into a local ChromaDB
    collection; that code path was removed along with ChromaDB support.
    Sync against the pgvector evidence store (services/evidence_store.py)
    has not been implemented. Raising here — rather than silently
    returning a fake success dict — so a caller (or a scheduled job)
    cannot mistake "did nothing" for "synced".
    """
    raise NotImplementedError(
        "fda_sync.run_sync() is disabled: it targeted ChromaDB, which was "
        "removed. pgvector-backed sync has not been implemented yet."
    )


# ── APScheduler setup ─────────────────────────────────────────────────────────

def start_scheduler():
    """Disabled — see run_sync(). Does not schedule a job that would fail
    silently every night; raises immediately instead."""
    raise NotImplementedError(
        "fda_sync.start_scheduler() is disabled until run_sync() is "
        "reimplemented against Qdrant."
    )

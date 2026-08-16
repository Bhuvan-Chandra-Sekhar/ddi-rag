"""
prescription_parsing.py — Detect known drug names in free-text
prescription input, for /api/query's `detected_drugs` field.

NOTE: this used to be dead code, inline in app.py. init_lookups() existed
but was never called from anywhere — the lookup table was always empty,
so parse_prescription() always returned [], and /api/query silently fell
back to treating the entire raw prescription string as one unfiltered
semantic-search query (see app.py's query_api(): `detected if detected
else [None]`). Fixed by actually calling init_lookups() at import time,
sourced from the live evidence_chunks table rather than the 240MB source
CSV (which is gitignored and won't exist in a deployed environment).

Matching uses a single-pass Aho-Corasick scan (aho_corasick.py) instead
of one regex `finditer` call per known drug name — with hundreds of names
indexed, scanning the text once for every pattern in one pass matters:
O(text_length + matches) instead of O(n_patterns * text_length).
"""

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text as sql_text

from aho_corasick import AhoCorasick, is_word_boundary_match
from database import get_session

log = logging.getLogger("ddi.prescription_parsing")

_BRAND_TO_GENERIC: Dict[str, str] = {}
_SORTED_NAMES:     List[str]      = []
_AUTOMATON:        Optional[AhoCorasick] = None


def init_lookups() -> None:
    """
    Build the brand→generic map and the Aho-Corasick matcher from every
    distinct (generic_name, brand_name) pair currently in evidence_chunks.
    Call once at startup, before serving requests. Failing open (empty
    lookups, not raising) if the DB isn't reachable yet — evidence
    retrieval already fails closed the same way elsewhere in this app.
    """
    global _BRAND_TO_GENERIC, _SORTED_NAMES, _AUTOMATON

    b2g: Dict[str, str] = {}
    generics: set = set()
    try:
        with get_session() as session:
            rows = session.execute(
                sql_text("SELECT DISTINCT generic_name, brand_name FROM evidence_chunks")
            ).fetchall()
        for generic_name, brand_name in rows:
            g = (generic_name or "").strip().lower()
            b = (brand_name or "").strip().lower()
            if g:
                generics.add(g)
            if b and b != g:
                b2g[b] = g
    except Exception:
        log.exception("init_lookups: failed to load drug names from evidence_chunks")

    _BRAND_TO_GENERIC = b2g
    all_names = generics | set(b2g.keys())
    _SORTED_NAMES = sorted(all_names, key=len, reverse=True)
    _AUTOMATON = AhoCorasick(_SORTED_NAMES)
    log.info("Lookup tables built: %d names indexed.", len(_SORTED_NAMES))


def parse_prescription(text: str) -> List[str]:
    """
    Longest-match extraction of recognised drug names from prescription
    text. Brand names are resolved to their generic equivalent.
    Longest-match-wins, non-overlapping consumption.
    """
    if _AUTOMATON is None:
        return []

    text_lower = text.lower()
    candidates = [
        m for m in _AUTOMATON.find_all(text_lower)
        if is_word_boundary_match(text_lower, m.start, m.end)
    ]
    # Longest match wins; ties broken by leftmost position — deterministic,
    # unlike a per-name loop's tie order among equal-length names, which
    # would depend on Python's randomized string-hash-based set iteration.
    candidates.sort(key=lambda m: (-(m.end - m.start), m.start))

    found:    List[str]             = []
    consumed: List[Tuple[int, int]] = []
    for m in candidates:
        s, e = m.start, m.end
        if not any(cs <= s < ce or cs < e <= ce for cs, ce in consumed):
            generic = _BRAND_TO_GENERIC.get(m.pattern, m.pattern)
            if generic not in found:
                found.append(generic)
            consumed.append((s, e))
    return found

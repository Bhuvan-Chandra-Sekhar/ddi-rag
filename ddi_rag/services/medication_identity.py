"""
services/medication_identity.py — RxNorm-based medication identity resolution
(architecture doc, roadmap Phase 2).

Resolution never silently guesses: only an unambiguous rxcui.json hit is
auto-confirmed. An approximate/fuzzy RxNorm match is persisted with
identity_confirmed=False and must be reviewed by a pharmacist before a
SafetyCase relies on it — this is what "ambiguous names never silently
resolve" (Phase 2 exit gate) means in code.
"""

import logging
from functools import lru_cache
from typing import List, Optional

import requests

from models import Medication

log = logging.getLogger("ddi.medication_identity")

_RXNORM_BASE    = "https://rxnav.nlm.nih.gov/REST"
_RXNORM_TIMEOUT = 5

# Bump when the resolution logic itself changes (not RxNorm's own data) —
# recorded on every Medication row so a historical decision can always be
# traced back to the method/version that produced it.
RESOLUTION_VERSION = "medication-identity-v1"


@lru_cache(maxsize=1024)
def _lookup_exact_rxcui(name: str) -> Optional[str]:
    try:
        r = requests.get(
            f"{_RXNORM_BASE}/rxcui.json",
            params={"name": name, "search": 1},
            timeout=_RXNORM_TIMEOUT,
        )
        r.raise_for_status()
        ids = r.json().get("idGroup", {}).get("rxnormId") or []
        return ids[0] if ids else None
    except Exception:
        log.warning("RxNorm exact lookup failed for %r", name, exc_info=True)
        return None


@lru_cache(maxsize=1024)
def _lookup_approximate_rxcui(name: str) -> Optional[str]:
    try:
        r = requests.get(
            f"{_RXNORM_BASE}/approximateTerm.json",
            params={"term": name, "maxEntries": 1},
            timeout=_RXNORM_TIMEOUT,
        )
        r.raise_for_status()
        candidates = r.json().get("approximateGroup", {}).get("candidate") or []
        return candidates[0]["rxcui"] if candidates else None
    except Exception:
        log.warning("RxNorm approximate lookup failed for %r", name, exc_info=True)
        return None


@lru_cache(maxsize=1024)
def _fetch_ingredients(rxcui: str) -> List[str]:
    """Ingredient/multi-ingredient/precise-ingredient names for a combination
    product or single-ingredient drug (RxNorm term types IN, PIN, MIN)."""
    try:
        r = requests.get(
            f"{_RXNORM_BASE}/rxcui/{rxcui}/related.json",
            params={"tty": "IN+PIN+MIN"},
            timeout=_RXNORM_TIMEOUT,
        )
        r.raise_for_status()
        groups = r.json().get("relatedGroup", {}).get("conceptGroup") or []
        names: List[str] = []
        for group in groups:
            for prop in group.get("conceptProperties") or []:
                nm = prop.get("name")
                if nm and nm not in names:
                    names.append(nm)
        return names
    except Exception:
        log.warning("RxNorm ingredient lookup failed for rxcui=%s", rxcui, exc_info=True)
        return []


def clear_caches() -> None:
    """Reset memoized RxNorm lookups. Mainly for tests."""
    _lookup_exact_rxcui.cache_clear()
    _lookup_approximate_rxcui.cache_clear()
    _fetch_ingredients.cache_clear()


def resolve_medication_identity(display_name: str) -> dict:
    """
    Resolve free-text `display_name` to an RxCUI and ingredient list.

    Returns:
        rxcui              : str | None
        ingredients         : list[str]
        matched_exactly     : bool — True only for an unambiguous rxcui.json hit
        identity_confirmed  : bool — mirrors matched_exactly; an approximate
                                     match is never auto-confirmed
        resolution_method   : "exact_match" | "approximate_match" | "unresolved"
    """
    name = display_name.strip().lower()
    if not name:
        return {
            "rxcui": None, "ingredients": [],
            "matched_exactly": False, "identity_confirmed": False,
            "resolution_method": "unresolved",
        }

    rxcui = _lookup_exact_rxcui(name)
    matched_exactly = rxcui is not None

    if rxcui is None:
        rxcui = _lookup_approximate_rxcui(name)

    ingredients = _fetch_ingredients(rxcui) if rxcui else []
    method = "exact_match" if matched_exactly else ("approximate_match" if rxcui else "unresolved")

    return {
        "rxcui": rxcui,
        "ingredients": ingredients,
        "matched_exactly": matched_exactly,
        "identity_confirmed": matched_exactly,
        "resolution_method": method,
    }


def get_or_create_medication(session, display_name: str) -> Medication:
    """
    Return the existing Medication row for `display_name`, or resolve it via
    RxNorm and persist a new one. Rows with identity_confirmed=False came
    from an approximate match and must be reviewed before a SafetyCase or
    rule evaluation treats their ingredient list as authoritative.
    """
    name = display_name.strip()
    existing = session.query(Medication).filter_by(display_name=name).first()
    if existing:
        return existing

    resolution = resolve_medication_identity(name)
    medication = Medication(
        display_name=name,
        rxcui=resolution["rxcui"],
        ingredients=resolution["ingredients"] or None,
        identity_confirmed=resolution["identity_confirmed"],
        resolution_method=resolution["resolution_method"],
        resolution_version=RESOLUTION_VERSION,
    )
    session.add(medication)
    session.flush()
    return medication

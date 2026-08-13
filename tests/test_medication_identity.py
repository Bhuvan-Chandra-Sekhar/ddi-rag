"""
Phase 2 exit gate: ambiguous names never silently resolve. Exact RxNorm
matches auto-confirm; approximate matches must come back unconfirmed and
queued for pharmacist review.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Medication
from services import medication_identity as mi


@pytest.fixture(autouse=True)
def clear_rxnorm_cache():
    mi.clear_caches()
    yield
    mi.clear_caches()


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _fake_response(json_body):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return json_body
    return _Resp()


def test_exact_match_is_auto_confirmed():
    with patch.object(mi.requests, "get") as mock_get:
        def side_effect(url, params=None, timeout=None):
            if "rxcui.json" in url:
                return _fake_response({"idGroup": {"rxnormId": ["11289"]}})
            if "related.json" in url:
                return _fake_response({
                    "relatedGroup": {"conceptGroup": [
                        {"conceptProperties": [{"name": "warfarin"}]}
                    ]}
                })
            raise AssertionError(f"unexpected URL {url}")

        mock_get.side_effect = side_effect
        result = mi.resolve_medication_identity("warfarin")

    assert result["rxcui"] == "11289"
    assert result["matched_exactly"] is True
    assert result["identity_confirmed"] is True
    assert result["ingredients"] == ["warfarin"]
    assert result["resolution_method"] == "exact_match"


def test_approximate_match_is_never_auto_confirmed():
    with patch.object(mi.requests, "get") as mock_get:
        def side_effect(url, params=None, timeout=None):
            if "rxcui.json" in url:
                return _fake_response({"idGroup": {}})  # no exact hit
            if "approximateTerm.json" in url:
                return _fake_response({
                    "approximateGroup": {"candidate": [{"rxcui": "99999"}]}
                })
            if "related.json" in url:
                return _fake_response({"relatedGroup": {}})
            raise AssertionError(f"unexpected URL {url}")

        mock_get.side_effect = side_effect
        result = mi.resolve_medication_identity("warfrin")  # misspelled

    assert result["rxcui"] == "99999"
    assert result["matched_exactly"] is False
    assert result["identity_confirmed"] is False
    assert result["resolution_method"] == "approximate_match"


def test_no_match_returns_unconfirmed_none():
    with patch.object(mi.requests, "get") as mock_get:
        def side_effect(url, params=None, timeout=None):
            if "rxcui.json" in url:
                return _fake_response({"idGroup": {}})
            if "approximateTerm.json" in url:
                return _fake_response({"approximateGroup": {}})
            raise AssertionError(f"unexpected URL {url}")

        mock_get.side_effect = side_effect
        result = mi.resolve_medication_identity("not-a-real-drug-xyz")

    assert result["rxcui"] is None
    assert result["identity_confirmed"] is False
    assert result["resolution_method"] == "unresolved"


def test_get_or_create_medication_persists_and_deduplicates(session):
    with patch.object(mi.requests, "get") as mock_get:
        def side_effect(url, params=None, timeout=None):
            if "rxcui.json" in url:
                return _fake_response({"idGroup": {"rxnormId": ["11289"]}})
            if "related.json" in url:
                return _fake_response({"relatedGroup": {}})
            raise AssertionError(f"unexpected URL {url}")

        mock_get.side_effect = side_effect
        med1 = mi.get_or_create_medication(session, "warfarin")
        med2 = mi.get_or_create_medication(session, "warfarin")

    assert med1.id == med2.id
    assert session.query(Medication).count() == 1
    assert med1.identity_confirmed is True
    assert med1.resolution_method == "exact_match"
    assert med1.resolution_version == mi.RESOLUTION_VERSION
    # The raw entered text must survive untouched alongside the resolved identity.
    assert med1.display_name == "warfarin"

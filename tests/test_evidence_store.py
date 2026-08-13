"""
Tests for services/evidence_store.py — the Postgres+pgvector/Cohere
evidence store that replaced Qdrant/local sentence-transformers.

Everything here is mocked (no `cohere`/`pgvector` packages installed, no
live Postgres/Cohere credentials) — this verifies the request/query shapes
and failure handling, not a real round trip. End-to-end verification needs
real Supabase + Cohere credentials.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from services import evidence_store as es


def test_to_pgvector_literal_formats_as_bracketed_csv():
    assert es._to_pgvector_literal([0.1, 0.2, 0.3]) == "[0.1,0.2,0.3]"


def test_embed_texts_raises_without_api_key():
    with patch.object(es, "COHERE_API_KEY", ""):
        with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
            es.embed_texts(["warfarin"])


def test_embed_texts_returns_empty_for_empty_input():
    with patch.object(es, "COHERE_API_KEY", "fake-key"):
        assert es.embed_texts([]) == []


def test_embed_texts_calls_cohere_with_correct_shape():
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"embeddings": {"float": [[0.1, 0.2]]}}

    with patch.object(es, "COHERE_API_KEY", "fake-key"), \
         patch.object(es.requests, "post", return_value=fake_response) as mock_post:
        result = es.embed_texts(["warfarin causes bleeding"], input_type="search_document")

    assert result == [[0.1, 0.2]]
    call_kwargs = mock_post.call_args
    assert call_kwargs.args[0] == es._COHERE_EMBED_URL
    payload = call_kwargs.kwargs["json"]
    assert payload["texts"] == ["warfarin causes bleeding"]
    assert payload["input_type"] == "search_document"
    assert "Bearer fake-key" in call_kwargs.kwargs["headers"]["Authorization"]


def test_get_connection_rejects_non_postgres_url():
    with patch.object(es, "DATABASE_URL", "sqlite:///./drugsafe.db"):
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            es._get_connection()


def test_search_fails_closed_to_empty_dataframe_on_any_error():
    with patch.object(es, "COHERE_API_KEY", "fake-key"), \
         patch.object(es, "embed_texts", side_effect=RuntimeError("cohere down")):
        result = es.search("warfarin interactions")
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_search_builds_expected_query_and_returns_dataframe():
    fake_cursor = MagicMock()
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.fetchall.return_value = [
        {"generic_name": "warfarin", "brand_name": "Coumadin", "product_type": "human_prescription_drug",
         "route": "oral", "section": "drug_interactions", "text": "some fda text", "score": 0.83},
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with patch.object(es, "embed_texts", return_value=[[0.1, 0.2]]), \
         patch.object(es, "_get_connection", return_value=fake_conn):
        result = es.search("warfarin bleeding risk", top_k=5, drug_name="warfarin", section="drug_interactions")

    assert list(result.columns) == [
        "generic_name", "brand_name", "product_type", "route", "section", "text", "score",
    ]
    assert result.iloc[0]["generic_name"] == "warfarin"

    executed_sql, executed_params = fake_cursor.execute.call_args.args
    assert "generic_name = %s" in executed_sql
    assert "section = %s" in executed_sql
    assert "ORDER BY embedding <=> %s::vector" in executed_sql
    # params: [vector, drug_name_filter, section_filter, vector, top_k]
    assert executed_params[1] == "warfarin"
    assert executed_params[2] == "drug_interactions"
    assert executed_params[-1] == 5
    fake_conn.commit.assert_not_called()  # search never mutates
    fake_conn.close.assert_called_once()


def test_search_with_no_filters_omits_where_clause():
    fake_cursor = MagicMock()
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with patch.object(es, "embed_texts", return_value=[[0.1, 0.2]]), \
         patch.object(es, "_get_connection", return_value=fake_conn):
        result = es.search("some query")

    assert result.empty
    executed_sql = fake_cursor.execute.call_args.args[0]
    assert "WHERE" not in executed_sql


def test_upsert_chunks_returns_zero_for_empty_dataframe():
    assert es.upsert_chunks(pd.DataFrame()) == 0

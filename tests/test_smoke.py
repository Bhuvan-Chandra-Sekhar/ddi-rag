"""Smoke test: the Flask app boots, and pharmacy/chatbot routes are gone."""

from app import flask_app


def test_health_check_and_stripped_routes():
    client = flask_app.test_client()

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}

    # Pharmacy finder and general chatbot were intentionally removed from app.py.
    assert client.get("/api/nearby-pharmacy").status_code == 404
    assert client.post("/api/chat", json={"query": "hi"}).status_code == 404

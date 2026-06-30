"""Basic API smoke tests.

Uses a temporary SQLite database so tests don't touch your real journal.
Run with:  cd backend && pytest
"""
import os
import tempfile

import pytest

# Point the app at a throwaway database before importing it.
_tmp_db = os.path.join(tempfile.gettempdir(), "second_arrow_test.db")
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # triggers lifespan (create tables + seed)
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_concepts_seeded_and_ordered(client):
    r = client.get("/api/concepts")
    assert r.status_code == 200
    concepts = r.json()
    assert len(concepts) >= 15
    # The Second Arrow must be first in the learning path.
    assert concepts[0]["slug"] == "the-second-arrow"
    assert isinstance(concepts[0]["tags"], list)


def test_concept_detail_and_404(client):
    r = client.get("/api/concepts/the-second-arrow")
    assert r.status_code == 200
    assert r.json()["title"] == "The Second Arrow"

    r = client.get("/api/concepts/does-not-exist")
    assert r.status_code == 404


def test_resources(client):
    r = client.get("/api/resources")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_journal_create_list_get_delete(client):
    payload = {
        "first_arrow": "Someone interrupted me",
        "second_arrow": "They always do this",
        "body_sensation": "jaw",
        "chosen_response": "say nothing yet",
        "reflection": "Patience would mean waiting a beat.",
        "concept_slug": "the-second-arrow",
    }
    r = client.post("/api/journal", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["id"] > 0
    assert created["first_arrow"] == "Someone interrupted me"
    assert created["created_at"]

    entry_id = created["id"]

    r = client.get("/api/journal")
    assert r.status_code == 200
    assert any(e["id"] == entry_id for e in r.json())

    r = client.get(f"/api/journal/{entry_id}")
    assert r.status_code == 200
    assert r.json()["second_arrow"] == "They always do this"

    r = client.delete(f"/api/journal/{entry_id}")
    assert r.status_code == 204

    r = client.get(f"/api/journal/{entry_id}")
    assert r.status_code == 404

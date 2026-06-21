"""
Tests for the agent REST API (Phase 6).

Exercises all four routes across the full state machine:
  POST /agent/request
  GET  /agent/token/<id>
  DELETE /agent/token/<id>
  GET  /agent/pubkey
"""
import base64
import datetime

import pytest

import agent.api as api_module
import config
from agent.api import create_agent_app, init_queue
from agent.queue import RequestQueue


@pytest.fixture(autouse=True)
def reset_globals(tmp_path, monkeypatch):
    """Isolate module-level globals and redirect identity key to tmp dir."""
    monkeypatch.setattr(api_module, "_queue", None)
    monkeypatch.setattr(api_module, "_pubkey_bytes", None)
    monkeypatch.setattr(config, "TOKEN_KEY_FILE", str(tmp_path / "test.key"))


@pytest.fixture()
def queue(tmp_path):
    q = RequestQueue(
        str(tmp_path / "test.db"),
        ttl=30,
        rate_limit=100,
        expiry_interval=9999,  # never fire during tests
    )
    yield q
    q.stop()


@pytest.fixture()
def client(queue):
    app = create_agent_app(queue)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _submit(client, **overrides):
    body = {
        "tenant_id": "tenant-1",
        "agent_id": "agent-1",
        "service": "amazon",
        "task": "compare prices on these 3 items",
        **overrides,
    }
    return client.post("/agent/request", json=body)


# ---------------------------------------------------------------------------
# POST /agent/request
# ---------------------------------------------------------------------------

def test_submit_happy_path(client):
    r = _submit(client)
    assert r.status_code == 201
    data = r.get_json()
    assert data["state"] == "PENDING"
    assert "search" in data["scope"]
    assert "read" in data["scope"]
    assert "purchase" not in data["scope"]


def test_submit_missing_required_field_returns_400(client):
    r = client.post("/agent/request", json={"service": "amazon", "task": "compare"})
    assert r.status_code == 400


def test_submit_empty_body_returns_400(client):
    r = client.post("/agent/request", json={})
    assert r.status_code == 400


def test_submit_unknown_service_returns_empty_scope(client):
    r = _submit(client, service="unknownservice")
    assert r.status_code == 201
    assert r.get_json()["scope"] == []


# ---------------------------------------------------------------------------
# GET /agent/token/<id>
# ---------------------------------------------------------------------------

def test_poll_pending_returns_202(client):
    req_id = _submit(client).get_json()["id"]
    r = client.get(f"/agent/token/{req_id}")
    assert r.status_code == 202
    assert r.get_json()["status"] == "PENDING"


def test_poll_approved_returns_200(client, queue):
    req_id = _submit(client).get_json()["id"]
    queue.approve(req_id)
    r = client.get(f"/agent/token/{req_id}")
    assert r.status_code == 200
    assert r.get_json()["status"] == "APPROVED"


def test_poll_denied_returns_403(client, queue):
    req_id = _submit(client).get_json()["id"]
    queue.deny(req_id)
    r = client.get(f"/agent/token/{req_id}")
    assert r.status_code == 403
    assert r.get_json()["status"] == "DENIED"


def test_poll_expired_returns_410(client, queue):
    req_id = _submit(client).get_json()["id"]
    # Back-date the TTL so expire_stale() picks it up
    req = queue.get(req_id)
    req.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)
    queue.expire_stale()
    r = client.get(f"/agent/token/{req_id}")
    assert r.status_code == 410


def test_poll_not_found_returns_404(client):
    r = client.get("/agent/token/no-such-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /agent/token/<id>
# ---------------------------------------------------------------------------

def test_revoke_pending_cancels_and_returns_200(client, queue):
    req_id = _submit(client).get_json()["id"]
    r = client.delete(f"/agent/token/{req_id}")
    assert r.status_code == 200
    assert r.get_json()["status"] == "revoked"
    # Subsequent poll → denied (cancelled PENDING becomes DENIED)
    assert client.get(f"/agent/token/{req_id}").status_code == 403


def test_revoke_approved_expires_and_returns_200(client, queue):
    req_id = _submit(client).get_json()["id"]
    queue.approve(req_id)
    r = client.delete(f"/agent/token/{req_id}")
    assert r.status_code == 200
    # Subsequent poll → 410 (revoked APPROVED becomes EXPIRED)
    assert client.get(f"/agent/token/{req_id}").status_code == 410


def test_revoke_already_terminal_returns_410(client, queue):
    req_id = _submit(client).get_json()["id"]
    queue.deny(req_id)
    r = client.delete(f"/agent/token/{req_id}")
    assert r.status_code == 410


def test_revoke_not_found_returns_404(client):
    r = client.delete("/agent/token/ghost-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /agent/pubkey
# ---------------------------------------------------------------------------

def test_pubkey_returns_eddsa_key(client):
    r = client.get("/agent/pubkey")
    assert r.status_code == 200
    data = r.get_json()
    assert data["algorithm"] == "EdDSA"
    pub = base64.b64decode(data["public_key"])
    assert len(pub) == 32  # Ed25519 raw public keys are always 32 bytes


def test_pubkey_is_stable_across_calls(client):
    r1 = client.get("/agent/pubkey")
    r2 = client.get("/agent/pubkey")
    assert r1.get_json()["public_key"] == r2.get_json()["public_key"]

"""
Tests for DobermanClient SDK.

HTTP calls are mocked with unittest.mock — no live server required.
Crypto uses real Ed25519 keys so token verification is genuine.
"""
from __future__ import annotations

import base64
import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest

from agent.sdk import (
    ApprovalDenied,
    ApprovalExpired,
    ApprovalTimeout,
    DobermanClient,
    ScopeViolation,
)
from core.crypto import encode_jwt, generate_ed25519_keypair, ed25519_public_to_bytes

BASE_URL = "http://localhost:5002"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def keypair():
    return generate_ed25519_keypair()


@pytest.fixture()
def client():
    return DobermanClient(
        base_url=BASE_URL,
        tenant_id="test-tenant",
        agent_id="test-agent",
        poll_interval=0,  # no sleeping in tests
        timeout=5,
    )


def _make_token(priv_key, scope=None, expired=False) -> str:
    """Build a signed Ed25519 JWT for testing."""
    import datetime
    now = datetime.datetime.now(datetime.UTC)
    if expired:
        exp = int((now - datetime.timedelta(seconds=60)).timestamp())
    else:
        exp = int((now + datetime.timedelta(seconds=900)).timestamp())
    payload = {
        "jti": "test-token-id",
        "tenant": "test-tenant",
        "agent_id": "test-agent",
        "service": "amazon",
        "session_id": "req-001",
        "scope": scope or ["search", "read"],
        "iat": int(now.timestamp()),
        "exp": exp,
        "hint": base64.b64encode(b"encrypted-stub").decode(),
        "request_id": "req-001",
    }
    return encode_jwt(payload, priv_key)


# ---------------------------------------------------------------------------
# request_access
# ---------------------------------------------------------------------------

class TestRequestAccess:
    def test_approved(self, client, keypair):
        priv, pub = keypair
        token = _make_token(priv)
        pub_b64 = base64.b64encode(ed25519_public_to_bytes(pub)).decode()

        submit_resp = MagicMock(ok=True, status_code=201)
        submit_resp.json.return_value = {
            "id": "req-001", "scope": ["search", "read"], "state": "PENDING",
        }

        poll_pending = MagicMock(status_code=202)
        poll_pending.json.return_value = {"status": "PENDING"}

        poll_approved = MagicMock(status_code=200)
        poll_approved.json.return_value = {"status": "APPROVED", "token": token}

        with patch("requests.post", return_value=submit_resp), \
             patch("requests.get", side_effect=[poll_pending, poll_approved]):
            result_token, request_id = client.request_access("amazon", "compare prices")

        assert result_token == token
        assert request_id == "req-001"

    def test_denied(self, client):
        submit_resp = MagicMock(ok=True, status_code=201)
        submit_resp.json.return_value = {"id": "req-002", "scope": [], "state": "PENDING"}

        poll_denied = MagicMock(status_code=403)
        poll_denied.json.return_value = {"status": "DENIED"}

        with patch("requests.post", return_value=submit_resp), \
             patch("requests.get", return_value=poll_denied):
            with pytest.raises(ApprovalDenied):
                client.request_access("amazon", "place a bulk order")

    def test_expired(self, client):
        submit_resp = MagicMock(ok=True, status_code=201)
        submit_resp.json.return_value = {"id": "req-003", "scope": [], "state": "PENDING"}

        poll_expired = MagicMock(status_code=410)
        poll_expired.json.return_value = {"status": "EXPIRED"}

        with patch("requests.post", return_value=submit_resp), \
             patch("requests.get", return_value=poll_expired):
            with pytest.raises(ApprovalExpired):
                client.request_access("amazon", "compare prices")

    def test_timeout(self, client):
        submit_resp = MagicMock(ok=True, status_code=201)
        submit_resp.json.return_value = {"id": "req-004", "scope": [], "state": "PENDING"}

        poll_pending = MagicMock(status_code=202)
        poll_pending.json.return_value = {"status": "PENDING"}

        # Force immediate timeout: set timeout=0 and patch time.time to exceed it
        client.timeout = 0

        with patch("requests.post", return_value=submit_resp), \
             patch("requests.get", return_value=poll_pending):
            with pytest.raises(ApprovalTimeout):
                client.request_access("amazon", "compare prices")

    def test_submit_error_raises(self, client):
        bad_resp = MagicMock(ok=False, status_code=500, text="internal error")

        with patch("requests.post", return_value=bad_resp):
            with pytest.raises(RuntimeError, match="submit failed"):
                client.request_access("amazon", "compare prices")


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------

class TestVerifyToken:
    def test_valid_token(self, client, keypair):
        priv, pub = keypair
        token = _make_token(priv, scope=["search", "read"])
        pub_bytes = ed25519_public_to_bytes(pub)
        pub_b64 = base64.b64encode(pub_bytes).decode()

        pubkey_resp = MagicMock(ok=True)
        pubkey_resp.json.return_value = {"algorithm": "EdDSA", "public_key": pub_b64}

        with patch("requests.get", return_value=pubkey_resp):
            claims = client.verify_token(token)

        assert claims["scope"] == ["search", "read"]
        assert claims["service"] == "amazon"

    def test_pubkey_cached_after_first_call(self, client, keypair):
        priv, pub = keypair
        token = _make_token(priv)
        pub_b64 = base64.b64encode(ed25519_public_to_bytes(pub)).decode()

        pubkey_resp = MagicMock(ok=True)
        pubkey_resp.json.return_value = {"algorithm": "EdDSA", "public_key": pub_b64}

        with patch("requests.get", return_value=pubkey_resp) as mock_get:
            client.verify_token(token)
            client.verify_token(token)
        # pubkey should only be fetched once
        assert mock_get.call_count == 1

    def test_expired_token_raises(self, client, keypair):
        priv, pub = keypair
        token = _make_token(priv, expired=True)
        pub_b64 = base64.b64encode(ed25519_public_to_bytes(pub)).decode()

        pubkey_resp = MagicMock(ok=True)
        pubkey_resp.json.return_value = {"algorithm": "EdDSA", "public_key": pub_b64}

        with patch("requests.get", return_value=pubkey_resp):
            with pytest.raises(ValueError, match="expired"):
                client.verify_token(token)

    def test_wrong_key_raises(self, client, keypair):
        priv, _ = keypair
        token = _make_token(priv)

        # Different key — verification should fail
        _, other_pub = generate_ed25519_keypair()
        other_pub_b64 = base64.b64encode(ed25519_public_to_bytes(other_pub)).decode()

        pubkey_resp = MagicMock(ok=True)
        pubkey_resp.json.return_value = {"algorithm": "EdDSA", "public_key": other_pub_b64}

        with patch("requests.get", return_value=pubkey_resp):
            with pytest.raises(ValueError, match="verification failed"):
                client.verify_token(token)

    def test_scope_check_passes(self, client, keypair):
        priv, pub = keypair
        token = _make_token(priv, scope=["search", "read"])
        pub_b64 = base64.b64encode(ed25519_public_to_bytes(pub)).decode()

        pubkey_resp = MagicMock(ok=True)
        pubkey_resp.json.return_value = {"algorithm": "EdDSA", "public_key": pub_b64}

        with patch("requests.get", return_value=pubkey_resp):
            claims = client.verify_token(token, required_scope=["search"])

        assert "search" in claims["scope"]

    def test_scope_check_fails(self, client, keypair):
        priv, pub = keypair
        token = _make_token(priv, scope=["search", "read"])
        pub_b64 = base64.b64encode(ed25519_public_to_bytes(pub)).decode()

        pubkey_resp = MagicMock(ok=True)
        pubkey_resp.json.return_value = {"algorithm": "EdDSA", "public_key": pub_b64}

        with patch("requests.get", return_value=pubkey_resp):
            with pytest.raises(ScopeViolation, match="purchase"):
                client.verify_token(token, required_scope=["purchase"])


# ---------------------------------------------------------------------------
# revoke
# ---------------------------------------------------------------------------

class TestRevoke:
    def test_revoke_success(self, client):
        rev_resp = MagicMock(ok=True, status_code=200)
        rev_resp.json.return_value = {"status": "revoked", "request_id": "req-001"}

        with patch("requests.delete", return_value=rev_resp):
            client.revoke("req-001")  # should not raise

    def test_revoke_already_expired(self, client):
        rev_resp = MagicMock(ok=False, status_code=410, text="already expired")

        with patch("requests.delete", return_value=rev_resp):
            with pytest.raises(RuntimeError, match="revoke failed"):
                client.revoke("req-999")


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------

class TestGetSession:
    def test_session_has_auth_headers(self, keypair):
        priv, _ = keypair
        token = _make_token(priv, scope=["search", "read"])

        c = DobermanClient(BASE_URL, "t", "a")
        session = c.get_session(token)

        assert session.headers["Authorization"] == f"Bearer {token}"
        assert "search" in session.headers["X-GR-Scope"]
        assert "read" in session.headers["X-GR-Scope"]
        assert session.headers["X-GR-Service"] == "amazon"

    def test_session_is_requests_session(self, keypair):
        import requests as req_lib
        priv, _ = keypair
        token = _make_token(priv)

        c = DobermanClient(BASE_URL, "t", "a")
        session = c.get_session(token)
        assert isinstance(session, req_lib.Session)

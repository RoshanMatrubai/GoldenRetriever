"""
Agent-facing REST API — Blueprint mounted at /agent.

POST   /agent/request        submit a new scoped access request
GET    /agent/token/<id>     poll status (202 pending · 200 approved · 403 denied · 410 expired)
DELETE /agent/token/<id>     cancel (PENDING) or revoke (APPROVED)
GET    /agent/pubkey         GoldenRetriever's Ed25519 public key (base64)
"""
from __future__ import annotations

import base64

from flask import Blueprint, Flask, jsonify, request

import config
from agent.queue import (
    InvalidTransition, RateLimitExceeded, RequestNotFound,
    RequestQueue, RequestState,
)
from core.crypto import (
    ed25519_private_from_bytes, ed25519_private_to_bytes,
    ed25519_public_to_bytes, generate_ed25519_keypair,
)

agent_bp = Blueprint("agent", __name__, url_prefix="/agent")

_queue: RequestQueue | None = None
_pubkey_bytes: bytes | None = None


def init_queue(queue: RequestQueue) -> None:
    global _queue
    _queue = queue


def _get_queue() -> RequestQueue:
    if _queue is None:
        raise RuntimeError("Queue not initialized — call init_queue() first")
    return _queue


def _load_pubkey() -> bytes:
    """Return cached public key bytes; load or generate from TOKEN_KEY_FILE."""
    global _pubkey_bytes
    if _pubkey_bytes is not None:
        return _pubkey_bytes
    try:
        with open(config.TOKEN_KEY_FILE, "rb") as f:
            priv = ed25519_private_from_bytes(f.read())
    except FileNotFoundError:
        priv, _ = generate_ed25519_keypair()
        with open(config.TOKEN_KEY_FILE, "wb") as f:
            f.write(ed25519_private_to_bytes(priv))
        print(f"[agent-api] generated Ed25519 identity key → {config.TOKEN_KEY_FILE}", flush=True)
    _pubkey_bytes = ed25519_public_to_bytes(priv.public_key())
    return _pubkey_bytes


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@agent_bp.post("/request")
def submit_request():
    """Submit a new scoped access request; returns 201 with the pending request."""
    body = request.get_json(silent=True) or {}
    tenant_id = body.get("tenant_id", "").strip()
    agent_id  = body.get("agent_id", "").strip()
    service   = body.get("service", "").strip()
    task      = body.get("task", "").strip()

    if not all([tenant_id, agent_id, service, task]):
        return jsonify({"error": "tenant_id, agent_id, service, and task are required"}), 400

    try:
        req = _get_queue().submit(tenant_id, agent_id, service, task)
    except RateLimitExceeded as exc:
        return jsonify({"error": str(exc)}), 429
    except Exception as exc:
        print(f"[agent-api] submit error: {exc}", flush=True)
        return jsonify({"error": "internal error"}), 500

    return jsonify(req.to_dict()), 201


@agent_bp.get("/token/<request_id>")
def poll_token(request_id: str):
    """Poll an access request. Status codes signal the current state to the agent."""
    req = _get_queue().get(request_id)
    if req is None:
        return jsonify({"error": "not found"}), 404

    state = req.state
    data  = req.to_dict()

    if state == RequestState.PENDING:
        return jsonify({"status": "PENDING", "request": data}), 202
    if state == RequestState.APPROVED:
        return jsonify({"status": "APPROVED", "request": data, "token": data.get("token_id")}), 200
    if state == RequestState.DENIED:
        return jsonify({"status": "DENIED", "request": data}), 403
    # EXPIRED or any other terminal state
    return jsonify({"status": state.value, "request": data}), 410


@agent_bp.delete("/token/<request_id>")
def revoke_token(request_id: str):
    """Cancel a pending request or revoke an approved one."""
    q   = _get_queue()
    req = q.get(request_id)
    if req is None:
        return jsonify({"error": "not found"}), 404

    try:
        q.revoke(request_id)
    except InvalidTransition as exc:
        return jsonify({"error": str(exc)}), 410
    except RequestNotFound as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify({"status": "revoked", "request_id": request_id}), 200


@agent_bp.get("/pubkey")
def get_pubkey():
    """Return the GoldenRetriever Ed25519 public key agents use to verify tokens."""
    try:
        pub = _load_pubkey()
    except Exception as exc:
        print(f"[agent-api] pubkey error: {exc}", flush=True)
        return jsonify({"error": "could not load public key"}), 500
    return jsonify({"algorithm": "EdDSA", "public_key": base64.b64encode(pub).decode()}), 200


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_agent_app(queue: RequestQueue | None = None) -> Flask:
    """Create a standalone Flask app wrapping the agent blueprint."""
    app = Flask(__name__)
    if queue is not None:
        init_queue(queue)
    app.register_blueprint(agent_bp)
    return app

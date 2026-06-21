"""
Dashboard backend — Flask + SocketIO (async_mode="threading").

JSON API contract (stable — UI binds to these endpoints):

  GET  /api/status
       → {"status":"ok","pending_count":N,"version":"0.7.0"}

  GET  /api/requests?state=PENDING
       → {"requests":[...AccessRequest dicts...]}

  GET  /api/requests/all?limit=100
       → {"requests":[...]}

  POST /api/requests/<id>/approve
       → {"request":{...},"message":"approved"}

  POST /api/requests/<id>/deny
       → {"request":{...},"message":"denied"}

  DELETE /api/requests/<id>
       → {"message":"revoked","request_id":"<id>"}

  GET  /api/tenants
       → {"tenants":[...]}

  GET  /api/accounts?tenant_id=<id>
       → {"accounts":[...]}

  GET  /api/audit?limit=50&event=TOKEN_ISSUED&tenant_id=<id>
       → {"events":[{id,event,tenant_id,agent_id,service,request_id,scope,detail,timestamp}]}

SocketIO events (server → all clients):
  request:new       {"request": {...}}
  request:resolved  {"request": {...}}
  token:revoked     {"request_id": "...", "state": "..."}
"""
from __future__ import annotations

from flask import Flask, jsonify, redirect, request as flask_request
from flask_socketio import SocketIO

import audit.log as audit_log
import auth.adapters as adapters
from agent.queue import InvalidTransition, RequestNotFound, RequestQueue, RequestState
from auth.oauth import OAuthError, begin_oauth, complete_oauth
from core.tokens import issue_token
from core.vault import Vault

_queue: RequestQueue | None = None
_vault: Vault | None = None
_socketio: SocketIO | None = None
_oauth_states: dict[str, dict] = {}  # state_token → {service, tenant_id}


def create_dashboard_app(queue: RequestQueue, vault: Vault) -> tuple[Flask, SocketIO]:
    """Create the dashboard Flask+SocketIO app and wire the queue event hook."""
    global _queue, _vault, _socketio

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "gr-dashboard-secret-dev"  # MOCK

    sio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")
    _socketio = sio
    _queue = queue
    _vault = vault

    audit_log.set_emit_hook(sio.emit)
    queue.set_event_hook(_emit_event)

    @app.after_request
    def _add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.route("/api/<path:path>", methods=["OPTIONS"])
    def _options(path):
        return "", 204

    # --- Status ---

    @app.get("/api/status")
    def api_status():
        return jsonify({
            "status": "ok",
            "pending_count": len(_queue.list_pending()),
            "version": "0.9.0",
        })

    # --- Requests ---

    @app.get("/api/requests")
    def api_requests():
        state_param = flask_request.args.get("state", "PENDING").upper()
        try:
            target = RequestState(state_param)
        except ValueError:
            return jsonify({"error": f"Unknown state: {state_param}"}), 400
        if target == RequestState.PENDING:
            reqs = _queue.list_pending()
        else:
            reqs = [r for r in _queue.list_all(200) if r.state == target]
        return jsonify({"requests": [r.to_dict() for r in reqs]})

    @app.get("/api/requests/all")
    def api_requests_all():
        limit = min(int(flask_request.args.get("limit", 100)), 500)
        reqs = _queue.list_all(limit=limit)
        return jsonify({"requests": [r.to_dict() for r in reqs]})

    @app.post("/api/requests/<request_id>/approve")
    def api_approve(request_id: str):
        try:
            req = _queue.approve(request_id)
            # Resolve per-service credential hint (OAuth token or session cookies)
            hint_data = adapters.resolve_hint(req.service, req.tenant_id, _vault)
            token_str, token_id = issue_token(req, _vault.get_key(), hint_data=hint_data)
            _queue.attach_token(request_id, token_id, token_jwt=token_str)
            req = _queue.get(request_id)
            audit_log.log_event(
                audit_log.TOKEN_ISSUED,
                tenant_id=req.tenant_id, agent_id=req.agent_id,
                service=req.service, request_id=request_id,
                scope=req.scope,
                detail=(
                    f"token {token_id} issued "
                    f"(hint_type={hint_data.get('type','?')}, "
                    f"exp: {req.expires_at.isoformat() if req.expires_at else 'TTL'})"
                ),
            )
        except RequestNotFound:
            return jsonify({"error": "not found"}), 404
        except InvalidTransition as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            print(f"[dashboard] approve error: {exc}", flush=True)
            return jsonify({"error": "internal error"}), 500
        return jsonify({"request": req.to_dict(), "message": "approved", "token": token_str})

    @app.post("/api/requests/<request_id>/deny")
    def api_deny(request_id: str):
        try:
            req = _queue.deny(request_id)
        except RequestNotFound:
            return jsonify({"error": "not found"}), 404
        except InvalidTransition as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            print(f"[dashboard] deny error: {exc}", flush=True)
            return jsonify({"error": "internal error"}), 500
        return jsonify({"request": req.to_dict(), "message": "denied"})

    @app.delete("/api/requests/<request_id>")
    def api_revoke(request_id: str):
        try:
            req_before = _queue.get(request_id)
            req = _queue.revoke(request_id)
            if req_before and req_before.token_id:
                _vault.revoke_token(req_before.token_id, req_before.tenant_id)
        except RequestNotFound:
            return jsonify({"error": "not found"}), 404
        except InvalidTransition as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            print(f"[dashboard] revoke error: {exc}", flush=True)
            return jsonify({"error": "internal error"}), 500
        return jsonify({"message": "revoked", "request_id": request_id})

    # --- Tenants & Accounts ---

    @app.get("/api/tenants")
    def api_tenants():
        return jsonify({"tenants": _vault.list_tenants()})

    @app.get("/api/accounts")
    def api_accounts():
        tenant_id = flask_request.args.get("tenant_id")
        if not tenant_id:
            return jsonify({"error": "tenant_id is required"}), 400
        return jsonify({"accounts": _vault.list_service_accounts(tenant_id)})

    # --- Audit ---

    @app.get("/api/audit")
    def api_audit():
        limit = min(int(flask_request.args.get("limit", 50)), 500)
        event_filter = flask_request.args.get("event") or None
        tenant_id = flask_request.args.get("tenant_id") or None
        events = audit_log.get_recent(limit, event_filter=event_filter, tenant_id=tenant_id)
        return jsonify({"events": events})

    # --- OAuth flows (admin initiates on behalf of tenant) ---

    @app.get("/auth/oauth/<service>/begin")
    def auth_oauth_begin(service: str):
        """
        Redirect the admin to the provider's consent screen.
        Query param: tenant_id (required).

        MOCK: placeholder client credentials in config.py — real redirect
              only works once you fill in OAUTH_SERVICES client_id/secret.
        """
        tenant_id = flask_request.args.get("tenant_id")
        if not tenant_id:
            return jsonify({"error": "tenant_id is required"}), 400
        try:
            auth_url, state = begin_oauth(service)
        except OAuthError as exc:
            return jsonify({"error": str(exc)}), 400
        _oauth_states[state] = {"service": service, "tenant_id": tenant_id}
        return redirect(auth_url)

    @app.get("/auth/callback")
    def auth_oauth_callback():
        """
        Provider posts code + state here; we exchange for tokens and store in vault.
        OAUTH_REDIRECT_URI in config.py must point to this route.
        """
        code = flask_request.args.get("code")
        state = flask_request.args.get("state")
        error = flask_request.args.get("error")
        if error:
            return jsonify({"error": f"Provider returned: {error}"}), 400
        if not code or not state:
            return jsonify({"error": "Missing code or state"}), 400
        ctx = _oauth_states.pop(state, None)
        if not ctx:
            return jsonify({"error": "Unknown or expired state token"}), 400
        service = ctx["service"]
        tenant_id = ctx["tenant_id"]
        try:
            account_id = complete_oauth(service, code, state, tenant_id, _vault)
        except OAuthError as exc:
            print(f"[dashboard] OAuth callback error for {service}: {exc}", flush=True)
            return jsonify({"error": str(exc)}), 500
        return jsonify({
            "message": f"{service} OAuth tokens stored",
            "account_id": account_id,
            "tenant_id": tenant_id,
        })

    # --- Root ---

    @app.get("/")
    def root():
        return jsonify({"service": "GoldenRetriever", "version": "0.9.0", "status": "ok"})

    return app, sio


def _emit_event(event: str, data: dict) -> None:
    if _socketio is not None:
        try:
            # Strip full JWT from socket broadcasts — agents fetch it via the polling API
            safe = dict(data)
            if "request" in safe and isinstance(safe["request"], dict):
                safe["request"] = {k: v for k, v in safe["request"].items() if k != "token_jwt"}
            _socketio.emit(event, safe)
        except Exception as exc:
            print(f"[dashboard] emit error ({event}): {exc}", flush=True)

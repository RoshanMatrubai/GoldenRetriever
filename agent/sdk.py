"""
DobermanClient — Python SDK for agent-side integration.

Usage:
    client = DobermanClient(
        base_url="http://localhost:5002",
        tenant_id="my-tenant",
        agent_id="my-agent",
    )
    token, request_id = client.request_access("amazon", "compare prices on 3 items")
    claims = client.verify_token(token)
    session = client.get_session(token)
    client.revoke(request_id)
"""
from __future__ import annotations

import base64
import time

import jwt as pyjwt
import requests

from core.crypto import ed25519_public_from_bytes


class ApprovalDenied(Exception):
    """Admin explicitly denied the access request."""


class ApprovalExpired(Exception):
    """Access request expired before admin acted on it."""


class ApprovalTimeout(Exception):
    """Polling timed out — no admin decision within the configured window."""


class ScopeViolation(Exception):
    """Attempted action is outside the granted scope."""


class DobermanClient:
    """
    SDK wrapping the Doberman agent REST API.

    All network calls use `requests` with a per-call timeout of 10s.
    Public-key is fetched once from /agent/pubkey and cached for the
    lifetime of the client instance.
    """

    DEFAULT_POLL_INTERVAL = 2   # seconds between /token polls
    DEFAULT_TIMEOUT = 120       # seconds to wait for admin approval

    def __init__(
        self,
        base_url: str,
        tenant_id: str,
        agent_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.poll_interval = poll_interval
        self.timeout = timeout
        self._pubkey_cache: bytes | None = None  # raw Ed25519 public key bytes

    # -------------------------------------------------------------------------
    # Public methods
    # -------------------------------------------------------------------------

    def request_access(self, service: str, task: str) -> tuple[str, str]:
        """
        Submit an access request and block until it resolves.

        Returns (token_jwt, request_id) on approval.
        Raises ApprovalDenied, ApprovalExpired, or ApprovalTimeout otherwise.
        """
        resp = requests.post(
            f"{self.base_url}/agent/request",
            json={
                "tenant_id": self.tenant_id,
                "agent_id": self.agent_id,
                "service": service,
                "task": task,
            },
            timeout=10,
        )
        if not resp.ok:
            raise RuntimeError(
                f"[sdk] submit failed {resp.status_code}: {resp.text}"
            )

        body = resp.json()
        request_id = body["id"]
        scope = body.get("scope", [])
        print(
            f"[sdk] submitted request {request_id[:8]}… "
            f"service={service!r} scope={scope}",
            flush=True,
        )

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            poll = requests.get(
                f"{self.base_url}/agent/token/{request_id}",
                timeout=10,
            )
            status = poll.status_code
            data = poll.json()

            if status == 202:
                time.sleep(self.poll_interval)
                continue

            if status == 200:
                token = data.get("token")
                if not token:
                    raise RuntimeError("[sdk] APPROVED response missing token field")
                print(
                    f"[sdk] APPROVED {request_id[:8]}…  token={token[:24]}…",
                    flush=True,
                )
                return token, request_id

            if status == 403:
                raise ApprovalDenied(
                    f"Request {request_id} was denied by admin"
                )

            if status == 410:
                raise ApprovalExpired(
                    f"Request {request_id} expired before admin acted"
                )

            raise RuntimeError(
                f"[sdk] unexpected poll status {status}: {data}"
            )

        raise ApprovalTimeout(
            f"No admin decision within {self.timeout}s for request {request_id}"
        )

    def verify_token(self, token: str, required_scope: list[str] | None = None) -> dict:
        """
        Verify the token's Ed25519 signature and expiry using the server's public key.

        Returns decoded claims on success.
        Raises ValueError on invalid signature, expiry, or scope mismatch.
        The public key is fetched from /agent/pubkey once and cached.
        """
        pub_bytes = self._get_pubkey()
        pub_key = ed25519_public_from_bytes(pub_bytes)
        try:
            claims = pyjwt.decode(token, pub_key, algorithms=["EdDSA"])
        except pyjwt.ExpiredSignatureError as exc:
            raise ValueError(f"Token is expired: {exc}") from exc
        except pyjwt.InvalidTokenError as exc:
            raise ValueError(f"Token verification failed: {exc}") from exc

        if required_scope:
            token_scope = claims.get("scope", [])
            missing = [a for a in required_scope if a not in token_scope]
            if missing:
                raise ScopeViolation(
                    f"Token scope insufficient — missing: {missing}"
                )

        return claims

    def revoke(self, request_id: str) -> None:
        """Cancel a pending request or revoke an approved token."""
        resp = requests.delete(
            f"{self.base_url}/agent/token/{request_id}",
            timeout=10,
        )
        if not resp.ok:
            raise RuntimeError(
                f"[sdk] revoke failed {resp.status_code}: {resp.text}"
            )
        print(f"[sdk] revoked {request_id[:8]}…", flush=True)

    def get_session(self, token: str, request_id: str | None = None) -> requests.Session:
        """
        Build an authenticated requests.Session from a scoped token.

        Fetches the one-time hint from /agent/hint/<request_id>, then injects
        the real credential:
          - OAuth hint  → Authorization: Bearer <access_token>
          - Session hint → Cookie jar populated from encrypted cookie list
          - Stub / error → Authorization: Bearer <gr_jwt> (fallback)

        Always adds:
          - X-GR-Token:  the GR JWT (proof of grant)
          - X-GR-Scope:  comma-joined scope list
          - X-GR-Service: service name
        """
        claims = pyjwt.decode(token, options={"verify_signature": False})
        scope = claims.get("scope", [])
        service = claims.get("service", "")
        rid = request_id or claims.get("request_id", "")

        session = requests.Session()
        session.headers["X-GR-Token"] = token
        session.headers["X-GR-Scope"] = ",".join(scope)
        session.headers["X-GR-Service"] = service

        hint = None
        if rid:
            try:
                resp = requests.get(
                    f"{self.base_url}/agent/hint/{rid}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    hint = resp.json().get("hint", {})
                    print(
                        f"[sdk] hint fetched for {rid[:8]}… "
                        f"type={hint.get('type','?')} service={service!r}",
                        flush=True,
                    )
                elif resp.status_code == 410:
                    print(
                        f"[sdk] hint already consumed for {rid[:8]}… "
                        f"— using GR JWT as credential",
                        flush=True,
                    )
                else:
                    print(
                        f"[sdk] hint fetch failed {resp.status_code} for {rid[:8]}…",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[sdk] hint fetch error: {exc}", flush=True)

        if hint and hint.get("type") == "oauth":
            access_token = hint.get("access_token", "")
            token_type = hint.get("token_type", "Bearer")
            session.headers["Authorization"] = f"{token_type} {access_token}"
            print(f"[sdk] get_session: injected OAuth bearer for {service!r}", flush=True)
        elif hint and hint.get("type") == "session":
            cookies = hint.get("cookies", [])
            for c in cookies:
                session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )
            print(
                f"[sdk] get_session: injected {len(cookies)} cookie(s) for {service!r}",
                flush=True,
            )
        else:
            # Fallback: present the GR JWT itself as the Bearer credential
            session.headers["Authorization"] = f"Bearer {token}"
            print(
                f"[sdk] get_session: fallback — GR JWT as Bearer for {service!r}",
                flush=True,
            )

        return session

    def check_action(self, token: str, action: str, data: dict | None = None) -> bool:
        """
        Check whether an action is in scope via the /agent/action endpoint.

        Returns True if allowed; raises ScopeViolation if blocked (403).
        Raises ValueError on token/auth errors.
        """
        resp = requests.post(
            f"{self.base_url}/agent/action",
            json={"token": token, "action": action, "data": data or {}},
            timeout=10,
        )
        body = resp.json()
        if resp.status_code == 200:
            return True
        if resp.status_code == 403:
            raise ScopeViolation(
                f"Action '{action}' blocked — not in granted scope. "
                f"Server: {body.get('error', '')}"
            )
        raise ValueError(f"[sdk] action check failed {resp.status_code}: {body}")

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_pubkey(self) -> bytes:
        """Fetch and cache the server's Ed25519 public key bytes."""
        if self._pubkey_cache is None:
            resp = requests.get(f"{self.base_url}/agent/pubkey", timeout=10)
            if not resp.ok:
                raise RuntimeError(
                    f"[sdk] failed to fetch pubkey {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            self._pubkey_cache = base64.b64decode(data["public_key"])
            print(
                f"[sdk] fetched pubkey ({data.get('algorithm', 'EdDSA')}) "
                f"from {self.base_url}/agent/pubkey",
                flush=True,
            )
        return self._pubkey_cache



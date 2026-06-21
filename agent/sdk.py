"""
GoldenRetrieverClient — Python SDK for agent-side integration.

Usage:
    client = GoldenRetrieverClient(
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


class GoldenRetrieverClient:
    """
    SDK wrapping the GoldenRetriever agent REST API.

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

    def get_session(self, token: str) -> requests.Session:
        """
        Build an authenticated requests.Session from a scoped token.

        The returned session carries:
          - Authorization: Bearer <token>   (verified by GoldenRetriever on each call)
          - X-GR-Scope:    comma-joined scope list
          - X-GR-Service:  service name from the token claims

        OAuth Bearer / headless cookie injection is wired in Phase 14.
        For now, the JWT itself is the credential presented to downstream calls.
        """
        # Decode claims (display only — sig already verified by caller via verify_token)
        claims = pyjwt.decode(token, options={"verify_signature": False})
        scope = claims.get("scope", [])
        service = claims.get("service", "")
        hint_type = _hint_type(claims)

        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {token}"
        session.headers["X-GR-Scope"] = ",".join(scope)
        session.headers["X-GR-Service"] = service

        if hint_type == "oauth":
            # Phase 14 will populate a real OAuth Bearer via auth/oauth.py;
            # for now the GR JWT itself is forwarded as proof of grant.
            print(
                f"[sdk] get_session: oauth hint detected for {service!r} "
                f"(full token injection in Phase 14)",
                flush=True,
            )
        elif hint_type == "session":
            # Phase 14 will inject decrypted cookies from auth/session.py;
            # cookie jar is a stub here.
            print(
                f"[sdk] get_session: session/cookie hint detected for {service!r} "
                f"(cookie injection in Phase 14)",
                flush=True,
            )

        return session

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


def _hint_type(claims: dict) -> str:
    """Extract the hint type from decoded (unverified) JWT claims; returns 'stub' if absent."""
    hint_b64 = claims.get("hint", "")
    if not hint_b64:
        return "stub"
    # The hint payload is AES-GCM encrypted — we can't decrypt it without the master secret.
    # The type can only be inferred from context; leave it as 'stub' for SDK-side display.
    return "stub"  # Phase 14 will supply decrypted type via decrypt_hint()

"""
Access request queue — in-memory state machine backed by SQLite.

States: PENDING → APPROVED | DENIED | EXPIRED
"""
from __future__ import annotations

import datetime
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import config
from core.crypto import random_id
from policy.engine import derive_scope


class RequestState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


class RateLimitExceeded(Exception):
    pass


class RequestNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


@dataclass
class AccessRequest:
    id: str
    tenant_id: str
    agent_id: str
    service: str
    task: str
    scope: list
    state: RequestState
    created_at: datetime.datetime
    expires_at: datetime.datetime
    resolved_at: Optional[datetime.datetime] = None
    token_id: Optional[str] = None

    def is_pending(self) -> bool:
        return self.state == RequestState.PENDING

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "service": self.service,
            "task": self.task,
            "scope": self.scope,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "token_id": self.token_id,
        }


class RequestQueue:
    """
    Thread-safe request queue.

    In-memory dict holds live requests; SQLite is the durable store.
    Background thread auto-expires stale PENDING requests.
    """

    def __init__(
        self,
        db_path: str,
        ttl: int = None,
        rate_limit: int = None,
        rate_window: int = None,
        expiry_interval: int = 5,
    ):
        self._db_path = db_path
        self._ttl = ttl if ttl is not None else config.REQUEST_TTL_SECONDS
        self._rate_limit = rate_limit if rate_limit is not None else config.RATE_LIMIT_REQUESTS
        self._rate_window = rate_window if rate_window is not None else config.RATE_LIMIT_WINDOW_SECONDS
        self._expiry_interval = expiry_interval

        self._lock = threading.Lock()
        self._requests: dict[str, AccessRequest] = {}
        self._agent_timestamps: dict[str, list] = {}
        self._event_hook = None  # set via set_event_hook(fn)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._load_pending()

        self._stop_event = threading.Event()
        self._expiry_thread = threading.Thread(
            target=self._expiry_loop, daemon=True, name="gr-expiry"
        )
        self._expiry_thread.start()

    def set_event_hook(self, fn) -> None:
        """Register a callback fn(event: str, data: dict) for state-change events."""
        self._event_hook = fn

    # --- Public API ---

    def submit(self, tenant_id: str, agent_id: str, service: str, task: str) -> AccessRequest:
        """Create a new PENDING request; derives scope via policy engine."""
        with self._lock:
            self._check_and_record_rate_limit(agent_id)
            now = datetime.datetime.now(datetime.UTC)
            req = AccessRequest(
                id=random_id(),
                tenant_id=tenant_id,
                agent_id=agent_id,
                service=service,
                task=task,
                scope=derive_scope(service, task),
                state=RequestState.PENDING,
                created_at=now,
                expires_at=now + datetime.timedelta(seconds=self._ttl),
            )
            self._requests[req.id] = req
            self._persist(req)
        self._fire("request:new", {"request": req.to_dict()})
        return req

    def approve(self, request_id: str) -> AccessRequest:
        """Transition PENDING → APPROVED."""
        with self._lock:
            req = self._get_or_raise(request_id)
            if req.state != RequestState.PENDING:
                raise InvalidTransition(f"Cannot approve request in state {req.state.value}")
            req.state = RequestState.APPROVED
            req.resolved_at = datetime.datetime.now(datetime.UTC)
            self._persist(req)
        self._fire("request:resolved", {"request": req.to_dict()})
        return req

    def deny(self, request_id: str) -> AccessRequest:
        """Transition PENDING → DENIED."""
        with self._lock:
            req = self._get_or_raise(request_id)
            if req.state != RequestState.PENDING:
                raise InvalidTransition(f"Cannot deny request in state {req.state.value}")
            req.state = RequestState.DENIED
            req.resolved_at = datetime.datetime.now(datetime.UTC)
            self._persist(req)
        self._fire("request:resolved", {"request": req.to_dict()})
        return req

    def attach_token(self, request_id: str, token_id: str) -> AccessRequest:
        """Record the issued token ID on an APPROVED request."""
        with self._lock:
            req = self._get_or_raise(request_id)
            if req.state != RequestState.APPROVED:
                raise InvalidTransition(
                    f"Cannot attach token to request in state {req.state.value}"
                )
            req.token_id = token_id
            self._persist(req)
            return req

    def revoke(self, request_id: str) -> AccessRequest:
        """Cancel (PENDING→DENIED) or expire (APPROVED→EXPIRED) a request."""
        with self._lock:
            req = self._get_or_raise(request_id)
            if req.state == RequestState.PENDING:
                req.state = RequestState.DENIED
            elif req.state == RequestState.APPROVED:
                req.state = RequestState.EXPIRED
            else:
                raise InvalidTransition(
                    f"Cannot revoke request in terminal state {req.state.value}"
                )
            req.resolved_at = datetime.datetime.now(datetime.UTC)
            self._persist(req)
        self._fire("token:revoked", {"request_id": req.id, "state": req.state.value})
        return req

    def expire_stale(self) -> list:
        """Expire all PENDING requests past their TTL. Returns list of expired IDs."""
        now = datetime.datetime.now(datetime.UTC)
        expired = []
        with self._lock:
            for req in list(self._requests.values()):
                if req.state == RequestState.PENDING and now >= req.expires_at:
                    req.state = RequestState.EXPIRED
                    req.resolved_at = now
                    self._persist(req)
                    expired.append(req)
        for req in expired:
            self._fire("request:resolved", {"request": req.to_dict()})
        return [r.id for r in expired]

    def get(self, request_id: str) -> Optional[AccessRequest]:
        """Fetch by ID — checks memory first, then SQLite."""
        with self._lock:
            if request_id in self._requests:
                return self._requests[request_id]
        row = self._conn.execute(
            "SELECT * FROM requests WHERE id=?", (request_id,)
        ).fetchone()
        return _row_to_request(row) if row else None

    def list_pending(self) -> list:
        """All currently PENDING requests."""
        with self._lock:
            return [r for r in self._requests.values() if r.state == RequestState.PENDING]

    def list_all(self, limit: int = 100) -> list:
        """Recent requests from SQLite (authoritative for all states)."""
        rows = self._conn.execute(
            "SELECT * FROM requests ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_request(r) for r in rows]

    def stop(self):
        """Shut down the background expiry thread and close the DB connection."""
        self._stop_event.set()
        self._expiry_thread.join(timeout=2)
        self._conn.close()

    # --- Internals ---

    def _fire(self, event: str, data: dict) -> None:
        if self._event_hook is not None:
            try:
                self._event_hook(event, data)
            except Exception as exc:
                print(f"[queue] event hook error ({event}): {exc}", flush=True)

    def _init_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                service TEXT NOT NULL,
                task TEXT NOT NULL,
                scope TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                resolved_at TEXT,
                token_id TEXT
            )
        """)
        self._conn.commit()

    def _load_pending(self):
        """Load all PENDING requests into memory on startup."""
        rows = self._conn.execute(
            "SELECT * FROM requests WHERE state=?", (RequestState.PENDING.value,)
        ).fetchall()
        for row in rows:
            req = _row_to_request(row)
            self._requests[req.id] = req

    def _persist(self, req: AccessRequest):
        self._conn.execute(
            """
            INSERT OR REPLACE INTO requests
              (id, tenant_id, agent_id, service, task, scope, state,
               created_at, expires_at, resolved_at, token_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                req.id, req.tenant_id, req.agent_id, req.service, req.task,
                json.dumps(req.scope), req.state.value,
                req.created_at.isoformat(), req.expires_at.isoformat(),
                req.resolved_at.isoformat() if req.resolved_at else None,
                req.token_id,
            ),
        )
        self._conn.commit()

    def _get_or_raise(self, request_id: str) -> AccessRequest:
        req = self._requests.get(request_id)
        if req is None:
            raise RequestNotFound(f"Request {request_id!r} not found in active queue")
        return req

    def _check_and_record_rate_limit(self, agent_id: str):
        now = time.time()
        window = [t for t in self._agent_timestamps.get(agent_id, [])
                  if now - t < self._rate_window]
        if len(window) >= self._rate_limit:
            raise RateLimitExceeded(
                f"Agent {agent_id!r} exceeded rate limit: "
                f"{self._rate_limit} requests per {self._rate_window}s"
            )
        window.append(now)
        self._agent_timestamps[agent_id] = window

    def _expiry_loop(self):
        while not self._stop_event.wait(timeout=self._expiry_interval):
            try:
                expired = self.expire_stale()
                if expired:
                    print(
                        f"[queue] auto-expired {len(expired)} stale request(s): {expired}",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[queue] expiry error: {exc}", flush=True)


# --- helpers ---

def _row_to_request(row: sqlite3.Row) -> AccessRequest:
    return AccessRequest(
        id=row["id"],
        tenant_id=row["tenant_id"],
        agent_id=row["agent_id"],
        service=row["service"],
        task=row["task"],
        scope=json.loads(row["scope"]),
        state=RequestState(row["state"]),
        created_at=datetime.datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.datetime.fromisoformat(row["expires_at"]),
        resolved_at=(
            datetime.datetime.fromisoformat(row["resolved_at"])
            if row["resolved_at"] else None
        ),
        token_id=row["token_id"],
    )

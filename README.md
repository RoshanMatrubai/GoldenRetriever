# 🐕 GoldenRetriever · Scoped Access Broker for Agentic AI

> Companies don't hand their AI agents passwords. They hand them a scoped, expiring JWT — exactly the permissions the task needs, gone the moment the session ends.

GoldenRetriever sits between your AI agents and the third-party accounts they need. The agent requests access for a task; GoldenRetriever derives the minimum permission set, an admin approves, and the agent receives a short-lived Ed25519-signed JWT. Every grant is scoped, logged, and revocable.

---

## Quick Start

```bash
pip install -r requirements.txt
npm --prefix ui install

python main.py                        # dashboard :5001 · agent API :5002
npm --prefix ui run dev               # frontend dev server

python simulate_agent.py              # full approval loop smoke test
python simulate_agent.py --mode sdk   # same test via Python SDK
python simulate_agent.py --mode mcp   # same test via MCP tool calls
python main.py --mcp                  # stdio MCP server for Claude Code
```

---

## Build Status

| Phase | What | Status |
|---|---|---|
| 1 | Scaffold — config, main, ui shell, package dirs | ✅ |
| 2 | Crypto primitives — Argon2id, AES-256-GCM, Ed25519, EdDSA JWT | ✅ |
| 3 | Encrypted vault — SQLite + AES-256-GCM, multi-tenant, secrets masked on read | ✅ |
| 4 | Policy engine — task→scope derivation, least-privilege, 5 service catalogs | ✅ |
| 5 | Request queue — AccessRequest dataclass, state machine, background expiry, rate limiting | ✅ |
| 6 | Agent REST API — POST /request, GET/DELETE /token/<id>, GET /pubkey on :5002 | ✅ |
| 7 | Dashboard backend — Flask+SocketIO, stable JSON API, real-time events | ✅ |
| 8 | Polished dashboard UI — approval cards, scope badges, accounts, audit feed, live SocketIO | ✅ |
| 9 | Token issuance — Ed25519 JWT, AES-GCM hint, verify/revoke/decrypt, wired to approve+revoke | ✅ |
| 10 | Full approval loop — approve→scope→JWT→UI live update→agent poll→revoke; `simulate_agent.py` | ✅ |
| 11 | Python SDK — `GoldenRetrieverClient`: `request_access`, `verify_token`, `revoke`, `get_session` | ✅ |
| 12 | MCP server — FastMCP stdio, `request_access` / `list_available_services` / `revoke_token` | ✅ |
| 13 | Audit log — append-only `audit_log` table, event constants, wired to all lifecycle points, live UI feed | ✅ |
| 14 | OAuth + headless auth — Google/GitHub OAuth flow, Playwright session login, per-service adapters, hint wired into approve | ✅ |
| 15 | Session lifecycle — session bind, `GET /agent/hint/<id>` one-time fetch, real `get_session()`, UI Sessions tab, auto-expiry, `POST /agent/action` scope enforcement | ✅ |
| 16 | Demo polish — `simulate_agent.py` final (http/sdk/mcp modes), `DEMO.md`, README final | ✅ |

---

## Python SDK

```python
from agent.sdk import GoldenRetrieverClient, ApprovalDenied, ApprovalExpired, ApprovalTimeout, ScopeViolation

client = GoldenRetrieverClient(
    base_url="http://localhost:5002",
    tenant_id="my-tenant",
    agent_id="my-agent",
)

# Block until admin approves; raises ApprovalDenied / ApprovalExpired / ApprovalTimeout
token, request_id = client.request_access("amazon", "compare prices on 3 items")

# Verify signature + expiry using the server's Ed25519 public key (cached)
claims = client.verify_token(token, required_scope=["search"])

# Build an authenticated requests.Session with real credentials injected from the
# one-time hint (OAuth Bearer or cookie jar from headless session)
session = client.get_session(token, request_id=request_id)

# Check if an action is in scope (logs SCOPE_DENIED audit event on 403)
try:
    client.check_action(token, "purchase")
except ScopeViolation as exc:
    print("Blocked:", exc)

# Revoke when done
client.revoke(request_id)
```

---

## MCP Server (Claude Code integration)

```bash
# Terminal A — backend + dashboard
python main.py

# Terminal B — MCP server (stdio)
python main.py --mcp
# prints config snippet to paste into ~/.claude.json → mcpServers
```

The MCP server exposes three tools to the Claude CLI agent:

| Tool | Description |
|---|---|
| `request_access(service, task)` | Submit an access request; block until admin approves; return scoped JWT |
| `list_available_services()` | List services and their action catalogs |
| `revoke_token(request_id)` | Revoke an approved token or cancel a pending request |

All tools return structured dicts — never raise — so the agent always gets a readable response.

---

## Architecture

| Layer | Choice |
|---|---|
| KDF | Argon2id (m=65536, t=3, p=4) |
| Secret encryption | AES-256-GCM, random nonce per operation |
| Token format | Ed25519-signed JWT (`EdDSA`) with AES-GCM encrypted credential hint |
| Scope model | Per-request allow-list derived from agent task; embedded in signed claims |
| Service auth | OAuth 2.0 code flow (Google/GitHub via `authlib`) or Playwright headless login |
| Cookie cache | 6 h AES-GCM encrypted cookie cache for headless sessions |
| MCP | `fastmcp` stdio server — first-class Claude Code integration |
| Persistence | SQLite (`vault.db`) |

---

## Security Model

- Agents receive a **signed JWT** — never raw passwords, master vault keys, or OAuth secrets.
- The JWT `hint` is an AES-GCM blob decryptable only by the issuing server.
- Per-hint key = `HMAC(master_secret, request_id)` — derived at issue, never stored.
- Agents fetch the hint **once** via `GET /agent/hint/{id}` (consumed on first read; 410 on replay).
- Tokens are bound to a session; they auto-expire when `session_expires_at` is reached (background loop) or when the admin ends the session.
- Tokens expire at session end or TTL, whichever first — never renewable.
- Revocation checked on every use.
- Out-of-scope actions return 403 and log a `SCOPE_DENIED` audit event.

---

## Project Layout

```
config.py          — ports, paths, TTLs, service adapter stubs
main.py            — entry point (--mcp for MCP server)
core/              — crypto primitives, vault, token issuance
policy/            — task-to-scope engine (least-privilege derivation)
agent/             — REST API, SDK, MCP server
auth/              — OAuth flow and Playwright headless login
auth/adapters/     — per-service login adapters
dashboard/         — Flask + SocketIO backend + routes
audit/             — append-only audit log
ui/                — frontend dashboard (swappable design shell)
```

---

## Dashboard API Contract (stable — UI binds to these)

All routes on `:5001`. Agent API lives on `:5002`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/status` | Health + pending count |
| GET | `/api/requests?state=PENDING` | Pending (or filtered) requests |
| GET | `/api/requests/all?limit=100` | All requests, newest first |
| POST | `/api/requests/<id>/approve` | Approve → resolves credential hint → issues scoped JWT; returns `{request, message, token}` |
| POST | `/api/requests/<id>/deny` | Deny a pending request |
| DELETE | `/api/requests/<id>` | Revoke an approved/pending request |
| GET | `/api/tenants` | List tenants |
| GET | `/api/accounts?tenant_id=<id>` | List service accounts for a tenant |
| GET | `/api/audit?limit=50&event=TOKEN_ISSUED&tenant_id=<id>` | Audit log, newest first; optional filters |
| GET | `/api/sessions` | List active sessions (APPROVED requests with live tokens) |
| POST | `/api/sessions/<id>/end` | End a live session — revokes token, logs `SESSION_ENDED` |
| GET | `/auth/oauth/<service>/begin?tenant_id=<id>` | Start OAuth flow — redirects to provider consent screen |
| GET | `/auth/callback` | OAuth callback — exchanges code, stores encrypted tokens in vault |

**Agent API (`:5002`):**

| Method | Path | Description |
|---|---|---|
| POST | `/agent/request` | Submit scoped access request |
| GET | `/agent/token/<id>` | Poll status (202/200/403/410) |
| DELETE | `/agent/token/<id>` | Cancel/revoke |
| GET | `/agent/pubkey` | Ed25519 public key |
| GET | `/agent/hint/<id>` | One-time credential hint (410 on replay) |
| POST | `/agent/action` | Scope enforcement check — 200/403 + `SCOPE_DENIED` audit |

**SocketIO events (server → client):**
- `request:new` — new pending request arrived `{"request": {...}}`
- `request:resolved` — approved, denied, or expired `{"request": {...}}`
- `token:revoked` — token explicitly revoked `{"request_id": "...", "state": "..."}`
- `session:started` — token issued for an approved request `{"request": {...}}`
- `session:ended` — session ended (TTL/admin/revoke) `{"request_id":"...","service":"...","agent_id":"...","reason":"..."}`
- `audit:event` — every lifecycle event `{event, tenant_id, agent_id, service, request_id, scope, detail, timestamp}`

---

## Demo Arc (90 seconds)

See [`DEMO.md`](DEMO.md) for the full script with talking points.

```bash
# Terminal A — backend (dashboard :5001 + agent API :5002)
python main.py

# Terminal B — frontend
npm --prefix ui run dev

# Terminal C — agent smoke test (choose a mode)
python simulate_agent.py              # raw HTTP (default)
python simulate_agent.py --mode sdk   # Python SDK
python simulate_agent.py --mode mcp   # MCP tool calls (Claude CLI simulation)
```

```
Act 1  simulate_agent.py submits Amazon "compare prices"
         → policy derives scope=[search,read], NO purchase
         → pending card appears in UI via SocketIO

Act 2  Admin clicks Approve
         → Sessions tab shows live session with scope badges + TTL countdown
         → agent receives Ed25519-signed JWT

Act 3  In-scope: search → 200 OK · read → 200 OK

Act 4  Out-of-scope: purchase → 403 + SCOPE_DENIED in audit feed
                     delete   → 403 + SCOPE_DENIED in audit feed

Act 5  Admin clicks "End Session"
         → SESSION_ENDED in audit · subsequent poll → 410 EXPIRED ✓

Act 6  Audit tab: SUBMITTED → SCOPE_DERIVED → APPROVED → TOKEN_ISSUED
                → SCOPE_CHECK → SCOPE_DENIED → SESSION_ENDED
```

---

## License

MIT © 2026 Roshan Matrubai, Daksh Sharma, and Samarth Nayar

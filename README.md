# 🐕 Doberman · Scoped Access Broker for Agentic AI

> Companies don't hand their AI agents passwords. They hand them a scoped, expiring JWT — exactly the permissions the task needs, gone the moment the session ends.

Doberman sits between your AI agents and the third-party accounts they need (Amazon, Google, GitHub, Slack, etc.). When an agent needs access, it submits a request describing its task. Doberman's policy engine derives the **minimum permission set** that task requires, an admin approves it in the dashboard, and the agent receives a short-lived Ed25519-signed JWT. The token carries only what the task needs — nothing more — and dies automatically when the session ends.

Every grant is scoped, logged, and one-click revocable.

---

## What It Looks Like

The dashboard is a polished sidebar app:

- **Requests** — live feed of pending and resolved requests. Each pending card shows the derived scope with an inline **✎ edit** scope editor. Service dropdown + "Simulate request" fires a real demo request to the backend. Approve/Deny buttons with scope override support.
- **Active Sessions** — live tokens with pulsing green indicators and TTL countdowns. Per-session **"Try an action"** buttons fire real scope-enforcement checks (in-scope → ✓ green, out-of-scope → ✕ red). One-click **End Session**.
- **Audit Log** — full append-only event stream with event-type and agent filters; live updates via SocketIO (`SUBMITTED → SCOPE_DERIVED → APPROVED → TOKEN_ISSUED → SCOPE_DENIED → SESSION_ENDED`).
- **Connected Accounts** — service accounts from the encrypted vault with masked credentials.
- **Agent Overview** — agents derived from live request history with request counts, approval rates, and site access.

---

## Getting Started (from scratch)

### Prerequisites

- **Python 3.10+** — `python3 --version`
- **Node.js 18+** — `node --version`
- **npm** — comes with Node

### 1. Clone and install

```bash
git clone <repo-url>
cd Doberman

# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
npm --prefix ui install
```

### 2. Start everything

```bash
./start.sh
```

That's it. The script:
1. Kills any stale processes on ports 5001, 5002, and 5173
2. Starts the Python backend (Flask + SocketIO) on `:5001` (dashboard API) and `:5002` (agent API)
3. Starts the Vite dev server (React UI) on `:5173`
4. Waits for both to be healthy, then opens **http://localhost:5173** in your browser

You should see the Doberman dashboard with a green **Live** indicator in the sidebar footer and the **Requests** screen open by default.

Press `Ctrl+C` to stop everything cleanly.

### 3. Run the demo

The dashboard opens on the **Requests** screen. The full demo loop:

1. Select a service (Amazon, Google, GitHub, Slack, Jira) from the dropdown and click **Simulate request**
2. A pending card appears showing the derived scope (e.g. `search read` — no `purchase`)
3. Optionally click **✎ edit** to adjust the scope before approving
4. Click **✓ Approve** — the card updates to Approved; navigate to **Active Sessions** to see the live token with pulsing dot and TTL countdown
5. On the session card, click action buttons (e.g. "Search products" → allowed, "Add to cart" → denied) to test scope enforcement
6. Click **End Session** — the token is immediately killed and the session disappears
7. Navigate to **Access History** to see the full audit trail: `SUBMITTED → SCOPE_DERIVED → APPROVED → TOKEN_ISSUED → SCOPE_DENIED → SESSION_ENDED`

See [DEMO.md](DEMO.md) for the full script with talking points (~90 seconds).

---

## Manual startup (two terminals)

If you prefer not to use `start.sh`:

```bash
# Terminal A — backend (dashboard :5001 + agent API :5002)
python main.py

# Terminal B — frontend dev server
npm --prefix ui run dev
```

Then open **http://localhost:5173**.

---

## Claude Code Integration (MCP)

Doberman has a first-class Claude Code integration. Claude Code acts as the AI agent — it calls `request_access` via MCP, the approval card appears live in the dashboard, and once you approve it Claude continues its task with a scoped token.

### Setup

```bash
# 1. Register the MCP server with Claude Code (run in a plain terminal, not inside Claude Code)
claude mcp add doberman -- python3 /path/to/Doberman/main.py --mcp

# 2. Verify it registered
claude mcp list

# 3. Start the backend (must be running before Claude uses any tools)
python main.py
```

Then start a new Claude Code session and ask it something like:

> "Use Doberman to get Amazon access, then compare prices for the M4 MacBook Pro, M4 MacBook Air, and Dell XPS 15."

Claude will call `request_access("amazon", "compare prices …")` → the pending card appears in your dashboard → you approve → Claude gets the scoped JWT and continues.

### MCP tools exposed

| Tool | Description |
|---|---|
| `request_access(service, task)` | Submit a request; block until approved; return scoped JWT + request_id |
| `list_available_services()` | List all services and their action catalogs |
| `revoke_token(request_id)` | Revoke a live token or cancel a pending request |

All tools return structured dicts and never raise, so Claude always gets a readable response.

> **Note:** `main.py --mcp` is a stdio server — Claude Code spawns and manages the process automatically. You do not run it manually alongside the backend.

---

## Python SDK

```python
from agent.sdk import DobermanClient, ApprovalDenied, ApprovalExpired, ApprovalTimeout, ScopeViolation

client = DobermanClient(
    base_url="http://localhost:5002",
    tenant_id="demo",
    agent_id="my-agent",
)

# Block until admin approves (raises on denial/timeout)
token, request_id = client.request_access("amazon", "compare prices on 3 items")

# Verify signature + expiry using the server's Ed25519 public key (cached)
claims = client.verify_token(token, required_scope=["search"])

# Build an authenticated requests.Session — OAuth Bearer or cookie jar injected from hint
session = client.get_session(token, request_id=request_id)

# Scope enforcement check (logs SCOPE_DENIED audit event on violation)
try:
    client.check_action(token, "purchase")
except ScopeViolation as exc:
    print("Blocked:", exc)

# Revoke when done
client.revoke(request_id)
```

### Smoke test

```bash
python simulate_agent.py              # raw HTTP
python simulate_agent.py --mode sdk   # Python SDK
python simulate_agent.py --mode mcp   # MCP (simulates Claude Code behavior)
```

---

## How It Works

### Request lifecycle

```
Agent                    Doberman             Admin
  │                            │                       │
  ├─ POST /agent/request ──────►                       │
  │   service="amazon"         │                       │
  │   task="compare prices"    │                       │
  │                            ├── derive scope ──────►│ card in dashboard
  │                            │   [search, read]      │
  │◄─ 202 (request_id) ────────┤                       │
  │                            │                       │
  ├─ GET /agent/token/{id} ───►│   (polling…)          │
  │◄─ 202 pending ─────────────┤                       │
  │                            │                  click Approve
  │                            │◄─────────────────────┤
  │                            ├── issue JWT ──────────►dashboard live update
  │                            │   scope=[search,read] │
  ├─ GET /agent/token/{id} ───►│                       │
  │◄─ 200 {token, scope} ──────┤                       │
  │                            │                       │
  ├─ GET /agent/hint/{id} ────►│  (one-time fetch)     │
  │◄─ encrypted credentials ───┤                       │
  │                            │                       │
  ├─ [use service in scope] ──►│  SCOPE_CHECK: 200     │
  ├─ [out-of-scope attempt] ──►│  SCOPE_DENIED: 403    │
  │                            │                       │
  ├─ DELETE /agent/token/{id}──►│  revoke              │
  │◄─ 200 ──────────────────────┤                       │
```

### Security properties

- Agents receive a **signed JWT** — never raw passwords, vault keys, or OAuth secrets
- The JWT `hint` is an AES-GCM blob; the per-hint key is `HMAC(master_secret, request_id)` — derived at issue, never stored
- The hint is fetched **once** (`GET /agent/hint/{id}`) and consumed — 410 on replay
- Tokens are session-bound: they expire at `session_expires_at` or TTL, whichever comes first
- Tokens are **never renewable** — a new task requires a new request and a new approval
- Revocation is checked on every use
- Out-of-scope actions return 403 and log a `SCOPE_DENIED` audit event

---

## Architecture

| Layer | Choice |
|---|---|
| KDF | Argon2id (m=65536, t=3, p=4) |
| Secret encryption | AES-256-GCM, random nonce per operation, stored in SQLite |
| Token format | Ed25519-signed JWT (`EdDSA`) with AES-GCM encrypted credential hint |
| Scope model | Per-request allow-list derived from the agent's task description; embedded in signed claims |
| Service auth | OAuth 2.0 code flow (Google/GitHub via `authlib`) or Playwright headless login |
| Cookie cache | 6 h AES-GCM encrypted cache for headless sessions |
| MCP | `fastmcp` stdio server — first-class Claude Code integration |
| Persistence | SQLite (`vault.db`) |
| Real-time UI | Flask-SocketIO (`threading` mode) |

### Project layout

```
config.py          — ports, paths, TTLs, service adapter stubs
main.py            — entry point  (python main.py / python main.py --mcp)
start.sh           — one-command startup script
simulate_agent.py  — smoke test / demo runner
core/              — crypto primitives, encrypted vault, token issuance
policy/            — task → scope derivation (least-privilege)
agent/             — REST API (:5002), Python SDK, MCP server
auth/              — OAuth flow, Playwright headless login
auth/adapters/     — per-service login adapters
dashboard/         — Flask + SocketIO backend + dashboard routes (:5001)
audit/             — append-only audit log
ui/                — React frontend (Vite dev server)
```

---

## API Reference

All dashboard routes on `:5001`. Agent API on `:5002`.

### Dashboard API

| Method | Path | Description |
|---|---|---|
| GET | `/api/status` | Health check + pending count |
| GET | `/api/requests?state=PENDING` | Pending (or filtered) requests |
| GET | `/api/requests/all?limit=100` | All requests, newest first |
| POST | `/api/requests/<id>/approve` | Approve → derive scope → issue scoped JWT |
| POST | `/api/requests/<id>/deny` | Deny a pending request |
| DELETE | `/api/requests/<id>` | Revoke an approved or pending request |
| GET | `/api/tenants` | List tenants |
| GET | `/api/accounts?tenant_id=<id>` | List service accounts for a tenant |
| GET | `/api/sessions` | Active sessions (approved requests with live tokens) |
| POST | `/api/sessions/<id>/end` | End a live session — revokes token, logs `SESSION_ENDED` |
| GET | `/api/audit?limit=50&event=TOKEN_ISSUED` | Audit log, newest first; filterable by event/tenant |
| GET | `/auth/oauth/<service>/begin?tenant_id=<id>` | Start OAuth flow for a service |
| GET | `/auth/callback` | OAuth callback — exchanges code, stores encrypted tokens |

### Agent API

| Method | Path | Description |
|---|---|---|
| POST | `/agent/request` | Submit a scoped access request |
| GET | `/agent/token/<id>` | Poll status — 202 pending / 200 approved / 403 denied / 410 expired |
| DELETE | `/agent/token/<id>` | Cancel or revoke |
| GET | `/agent/pubkey` | Ed25519 public key for offline token verification |
| GET | `/agent/hint/<id>` | One-time credential hint fetch (410 on replay) |
| POST | `/agent/action` | Scope enforcement check — 200 allowed / 403 + `SCOPE_DENIED` audit |

### SocketIO events (server → client)

| Event | Payload | When |
|---|---|---|
| `request:new` | `{request}` | New pending request submitted |
| `request:resolved` | `{request}` | Request approved, denied, or expired |
| `token:revoked` | `{request_id, state}` | Token explicitly revoked |
| `session:started` | `{request}` | Token issued for an approved request |
| `session:ended` | `{request_id, service, agent_id, reason}` | Session ended (TTL / admin / revoke) |
| `audit:event` | `{event, tenant_id, agent_id, service, request_id, scope, detail, timestamp}` | Every lifecycle event |

---

## Build Phases

| Phase | What | Status |
|---|---|---|
| 1 | Scaffold — config, main, UI shell, package dirs | ✅ |
| 2 | Crypto — Argon2id, AES-256-GCM, Ed25519, EdDSA JWT | ✅ |
| 3 | Encrypted vault — SQLite + AES-256-GCM, multi-tenant, secrets masked | ✅ |
| 4 | Policy engine — task→scope derivation, least-privilege, 5 service catalogs | ✅ |
| 5 | Request queue — state machine, background expiry, per-agent rate limiting | ✅ |
| 6 | Agent REST API — `/request`, `/token/<id>`, `/pubkey` on `:5002` | ✅ |
| 7 | Dashboard backend — Flask + SocketIO, stable JSON contract, real-time events | ✅ |
| 8 | Dashboard UI — approval cards, scope badges, accounts strip, audit feed | ✅ |
| 9 | Token issuance — Ed25519 JWT, AES-GCM hint, verify/revoke, wired to approve | ✅ |
| 10 | Full approval loop — approve→scope→JWT→live UI update→agent poll→revoke | ✅ |
| 11 | Python SDK — `DobermanClient` with `request_access`, `verify_token`, `get_session` | ✅ |
| 12 | MCP server — FastMCP stdio, `request_access` / `list_available_services` / `revoke_token` | ✅ |
| 13 | Audit log — append-only table, all lifecycle events, live UI feed | ✅ |
| 14 | OAuth + headless auth — Google/GitHub OAuth, Playwright session login, per-service adapters | ✅ |
| 15 | Session lifecycle — session bind, one-time hint fetch, scope enforcement, auto-expiry | ✅ |
| 16 | Demo polish — `simulate_agent.py` final, `DEMO.md`, UI swap-ready | ✅ |

---

## License

MIT © 2026 Roshan Matrubai, Daksh Sharma, and Samarth Nayar

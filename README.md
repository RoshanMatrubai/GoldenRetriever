# 🐕 GoldenRetriever · Scoped Access Broker for Agentic AI

> Companies don't hand their AI agents passwords. They hand them a scoped, expiring JWT — exactly the permissions the task needs, gone the moment the session ends.

GoldenRetriever sits between your AI agents and the third-party accounts they need. The agent requests access for a task; GoldenRetriever derives the minimum permission set, an admin approves, and the agent receives a short-lived Ed25519-signed JWT. Every grant is scoped, logged, and revocable.

---

## Quick Start

```bash
pip install -r requirements.txt

python main.py          # dashboard :5001 · agent API :5002
python main.py --mcp    # stdio MCP server for Claude Code
npm --prefix ui install && npm --prefix ui run dev   # frontend dev server
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
| 7–16 | Dashboard → UI → Tokens → Audit → OAuth → Demo | 🔜 |

---

## Architecture

| Layer | Choice |
|---|---|
| KDF | Argon2id (m=65536, t=3, p=4) |
| Secret encryption | AES-256-GCM, random nonce per operation |
| Token format | Ed25519-signed JWT (`EdDSA`) with AES-GCM encrypted credential hint |
| Scope model | Per-request allow-list derived from agent task; embedded in signed claims |
| MCP | `fastmcp` stdio server — first-class Claude Code integration |
| Persistence | SQLite (`vault.db`) |

---

## Security Model

- Agents receive a **signed JWT** — never raw passwords, master vault keys, or OAuth secrets.
- The JWT `hint` is an AES-GCM blob decryptable only by the issuing server.
- Per-hint key = `HMAC(master_secret, request_id)` — derived at issue, never stored.
- Agents fetch the hint **once** via `GET /agent/hint/{id}` (consumed on first read).
- Tokens expire at session end or TTL, whichever first — never renewable.
- Revocation checked on every use.

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

## Demo Arc (90 seconds)

```
A: python main.py            # backend :5001/:5002
B: npm --prefix ui run dev   # UI
C: python main.py --mcp      # MCP server

Agent → request_access("Amazon", "compare prices on these 3 items")
1. Pending card appears: derived scope = [search, read], NO purchase
2. Admin clicks Approve
3. Agent receives scoped JWT (exp: session end)
4. Agent searches prices — in scope → 200 OK
5. Agent attempts checkout — out of scope → blocked + shown in UI
6. Session ends → token auto-expires
7. Audit feed: SUBMITTED → SCOPE_DERIVED → APPROVED → TOKEN_ISSUED → SCOPE_DENIED → SESSION_ENDED
```

---

## License

MIT © 2026 Roshan Matrubai

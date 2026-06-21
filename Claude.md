# 🐕 Doberman · Scoped Access Broker for Agentic AI
> Companies don't hand their AI agents passwords. They hand them a scoped, expiring JWT — exactly the permissions the task needs, gone the moment the session ends.

Doberman is a B2B SaaS that sits between a company's AI agents and the third-party accounts they need (Amazon, Google, internal tools, etc.). Instead of giving an agent a raw password and trusting it, the agent requests access for a task; Doberman derives the minimum permissions that task requires (e.g. "search prices on Amazon" → read/browse only, **no purchase**), an admin approves on a dashboard, and the agent gets a short-lived JWT handoff token that expires at session end. Every grant is scoped, logged, and revocable. Works with Claude's CLI agent as a first-class client.

**Demo-first:** every feature must be visibly demoable in the UI. Build each capability so it can be triggered, watched, and explained live — no invisible backend-only wins.

---

## STACK & COMMANDS
```
install:   pip install -r requirements.txt && npm --prefix ui install
backend:   python main.py            # API + dashboard backend on :5001
agent-api: (same process)            # agent-facing API on :5002
cli:       python main.py --mcp      # stdio MCP server for Claude CLI agent
ui:        npm --prefix ui run dev   # frontend dev server (swappable shell)
test:      pytest core/test_<module>.py -x
lint:      flake8 core/ agent/ auth/ policy/ dashboard/ audit/
```
**Never** run the full test suite. Single-file only.

---

## ARCHITECTURE (locked — do not deviate)
| Layer | Decision |
|---|---|
| KDF | Argon2id (m=65536, t=3, p=4) — NOT PBKDF2, NOT bcrypt |
| Secret encryption | AES-256-GCM, random nonce per op, stored in SQLite |
| Handoff token | Ed25519-signed JWT (`EdDSA`) carrying a scoped permission claim + encrypted credential hint |
| Scope model | Permission set derived per request; embedded as signed JWT claims; enforced at issuance and verifiable by the agent |
| Task → scope | Policy engine parses the agent's task/prompt → minimum permission set (`policy/`) |
| Service auth | Per service: OAuth flow (real provider token) OR Playwright headless login (session cookies) |
| Session lifetime | Token bound to a session; auto-expires at session end or TTL, whichever first; never renewable |
| MCP | `fastmcp` stdio server — first-class Claude CLI agent integration |
| Persistence | SQLite for tenants, accounts, requests, tokens, audit log |
| Request queue | In-memory + SQLite state machine; background expiry thread |
| UI | Polished frontend behind a stable API contract — **swappable**: final design sketch arrives last and drops in without backend changes |

**Key dirs:** `config.py` · `core/` (crypto, vault, tokens) · `policy/` (task→scope engine) · `agent/` (api, sdk, mcp_server) · `auth/` (oauth, session, adapters) · `dashboard/` (backend routes + SocketIO) · `ui/` (frontend) · `audit/`

---

## TOKEN & SCOPE MODEL
- Agents receive a JWT signed by Doberman's Ed25519 identity key — verifiable offline via the public key.
- Payload carries: `tenant`, `agent_id`, `service`, `session_id`, `scope` (explicit allow-list of actions), `iat`, `exp`, and an AES-GCM encrypted `hint` (`{type:"oauth",...}` or `{type:"session", cookies:[...]}`).
- Scope is an **allow-list**: an agent told to compare prices gets `["search","read"]` — never `["purchase","checkout"]`. The agent and downstream enforcement both read the signed scope; nothing outside it is permitted.
- Per-hint key = `HMAC(master_secret, request_id)`, never stored. Hint fetched once, then consumed.
- Token expires at session end or TTL (whichever first), never renews — re-request for new work. Revocation checked on every use.
- Agents NEVER receive: raw passwords, the master vault key, OAuth client secrets, scopes they weren't granted, or other tenants' tokens.

**Request states:** `PENDING → APPROVED | DENIED | EXPIRED`; APPROVED → scoped token issued; session end / revoke → token dead (410).

---

## BUILD PLAN (build in this order — one phase at a time)
Build bottom-up. Each phase leaves the repo importable and runnable, **and leaves something new visibly demoable in the UI** once the dashboard exists. Restate the phase goal in one line before starting. **Recommend `/clear` between phases.**

1. **Scaffold** — `config.py` (ports, paths, TTLs, `SERVICE_ADAPTERS` stub), `main.py` (`--mcp` flag, clean imports, prints startup line, exits), `requirements.txt` (backend deps only), `ui/` shell scaffolded, `.gitignore`, `LICENSE` (MIT 2026), `README.md`, package dirs + `__init__.py`. → `chore: scaffold Doberman project structure and entry point`
2. **Crypto primitives** — `core/crypto.py`: Argon2id, AES-GCM, Ed25519 (keygen/sign/verify/to-from-bytes), `encode/decode_jwt` (EdDSA), `derive_hint_key` (HMAC-SHA256), `random_id`. `core/test_crypto.py` (use m=256). → `feat: crypto primitives (Argon2id, AES-GCM, Ed25519, JWT)`
3. **Encrypted vault** — `core/vault.py`: SQLite store for tenants, service accounts (usernames/passwords/OAuth config), revoked tokens; create/unlock (Argon2id), CRUD with AES-GCM blobs, secrets masked on read. `core/test_vault.py`. → `feat: encrypted multi-tenant vault (SQLite + AES-256-GCM)`
4. **Policy engine (task → scope)** — `policy/engine.py`: given a service + task/prompt, derive the minimum permission allow-list; service-level action catalogs; conservative default (deny anything not clearly required). `policy/test_engine.py` covering e.g. "compare Amazon prices" → no purchase. → `feat: task-to-scope policy engine with least-privilege defaults`
5. **Request queue** — `agent/queue.py`: `AccessRequest` dataclass, state machine (submit/approve/deny/attach_token/expire_stale), background expiry thread, per-agent rate limit. `agent/test_queue.py`. → `feat: access request queue with state machine and auto-expiry`
6. **Agent REST API** — `agent/api.py` Blueprint `/agent`: `POST /request` (task + service → scoped pending request), `GET /token/{id}` (poll: 200/202/403/410/404), `DELETE /token/{id}`, `GET /pubkey`. `agent/test_api.py`. → `feat: agent REST API (scoped request, poll, revoke, pubkey)`
7. **Dashboard backend + SocketIO** — `dashboard/app.py` Flask+SocketIO (`async_mode="threading"`): `init_app`, routes for status / accounts / pending requests / audit; emits `request:new` / `request:resolved` / `token:revoked`. Stable JSON contract the UI binds to. → `feat: dashboard backend with real-time request feed`
8. **UI shell (swappable, polished)** — `ui/`: full polished frontend over the Phase 7 API — pending-request approval cards showing the **derived scope** per request, accounts manager, active tokens + session status, audit feed, live updates via SocketIO. Clean component seams so the final sketch swaps in without touching the API. → `feat: polished swappable dashboard UI with scoped approval cards`
9. **Token issuance** — `core/tokens.py`: load/create Ed25519 identity, `issue_token` (embed scope claim + encrypt hint + sign), `verify_token` (sig + expiry + revocation + scope), `decrypt_hint`. Wire approve route → issue scoped token; revoke route. `core/test_tokens.py`. → `feat: Ed25519 scoped JWT issuance, verification, and revocation`
10. **Full approval loop** — wire dashboard `approve`/`deny` → policy scope → issue token → emit resolution; UI cards reflect live state; agent polling completes the round-trip. Smoke test `simulate_agent.py`. → `feat: wire full scoped approval loop (approve → scoped JWT → polling agent)`
11. **Python SDK** — `agent/sdk.py` `DobermanClient`: `request_access(service, task)` (poll), `verify_token` (cached pubkey), `revoke`, `get_session` (oauth→Bearer / session→cookie jar). Exceptions `ApprovalDenied/Expired/Timeout`. `agent/test_sdk.py`. → `feat: DobermanClient SDK with scoped get_session()`
12. **MCP server (Claude CLI agent)** — `agent/mcp_server.py` FastMCP: `request_access(service, task)` (blocks, returns scoped token, never raises), `list_available_services`, `revoke_token`. `main.py --mcp` launches it + prints config snippet for the Claude CLI agent. Add `fastmcp`. → `feat: MCP server for Claude CLI agent (request_access, list_services, revoke)`
13. **Audit log** — `audit/log.py`: append-only `audit_log` table, event constants (incl. `SCOPE_DERIVED`, `TOKEN_ISSUED`, `SESSION_ENDED`), `log_event` / `get_recent` / filters. Wire into every lifecycle point; surface in UI audit feed. → `feat: append-only audit log wired to all access lifecycle events`
14. **OAuth + headless service auth** — `auth/oauth.py` (Google/GitHub auth-code + refresh, encrypted storage) and `auth/session.py` (`headless_login` async Playwright, 6h encrypted cookie cache) + `auth/adapters/` (generic/google/github; raise `TwoFactorRequired`/`LoginFailed`). Approve route picks per service → fills the token hint. Add `authlib requests playwright`. → `feat: per-service OAuth and Playwright headless login for token hints`
15. **Session lifecycle + scope enforcement demo** — bind tokens to a session; auto-expire on session end; `GET /agent/hint/{id}` one-time hint fetch; `get_session()` builds the real scoped session. UI shows a live session ending + a denied out-of-scope action. → `feat: session-bound expiry and live scope-enforcement demo`
16. **Demo polish + UI swap-readiness** — `simulate_agent.py` final (`--service`, `--task`, `--mode sdk|mcp`, graceful errors), `DEMO.md` (multi-act: scoped approve → agent acts in-scope → out-of-scope denied → revoke → session-end expiry → audit), confirm UI swaps cleanly via the frozen API contract, `README.md` final. → `feat: demo polish, simulate_agent final, DEMO.md, UI swap verified`

> When the final UI sketch arrives, it replaces `ui/` against the same Phase 7 API contract — no backend phase is touched.

---

## LIVING DOCS (update each phase before the commit block)
- **README.md** — new features, updated layout.
- **requirements.txt** / **ui/package.json** — append new deps only (never pre-add).
- **.gitignore** — new runtime artifacts.
- **config.py** — new keys near related ones, short comment.
- **API contract note in README** — if a phase changes any route the UI binds to, document it (the UI depends on this staying stable).
> Rule: if the phase changed how someone installs, runs, or demos the project, the docs change in the same phase.

---

## GIT / COMMITS
- **NEVER run git or commit automatically.** The human commits.
- End each phase by printing a ready-to-paste block:
  ```
  ✅ PHASE <n> COMPLETE — ready to commit
    git add <exact files — never -A or .>
    git commit -m "<type>: <message>"
  Suggested: /clear before Phase <n+1>.
  ```
- Conventional commits: `chore feat fix docs test refactor`.
- Never stage secrets, vault DBs, identity keys, cookie caches, or `node_modules/`.

---

## ANTI-PATTERNS (never do these)
- ❌ Sending raw passwords to agents — scoped tokens only.
- ❌ Issuing a token broader than the task requires — least privilege always; default deny.
- ❌ Logging secrets anywhere (audit logs tenant/agent/service/scope, never credentials).
- ❌ Storing plaintext credentials, OAuth tokens, or cookies — always AES-GCM encrypted.
- ❌ Auto-approving requests — every grant is an explicit admin action.
- ❌ Renewable or session-outliving tokens — expire at session end, re-request.
- ❌ A feature that can't be shown in the UI — if it can't be demoed, rethink it.
- ❌ Coupling the UI to backend internals — bind only to the documented API contract.
- ❌ Silent try/except — fail loudly to console + dashboard.
- ❌ Running git / `git add -A` / `git add .`.
- ❌ Pre-adding deps before they're used.
- ❌ Abstractions/refactors not required for the demo.
- ❌ Full test-suite runs — single-file only.

---

## MOCKS (flag every one with `# MOCK`)
- OAuth app credentials (placeholder client_id/secret; flow is real once filled).
- Argon2id timing in tests (m=256).
- Billing / tenant signup gate (no real payment for the demo).
- 2FA — raise `TwoFactorRequired`, surface it; don't intercept OTPs.
- Any downstream third-party action the agent performs (mock the call, show the scope check passing/failing).

---

## DEMO ARC (happy path — practice to ~90s, all visible in the UI)
```
A: python main.py            # backend + dashboard :5001
B: npm --prefix ui run dev   # UI
C: python main.py --mcp      # MCP server for the Claude CLI agent
Agent: request_access("Amazon", "compare prices on these 3 items")

1. Agent requests Amazon access for a price-comparison task
2. UI pending card appears: derived scope = [search, read], NO purchase
3. Admin clicks Approve
4. Agent receives scoped JWT (exp: session end)
5. Agent searches prices — in scope, 200 OK
6. Agent attempts checkout — out of scope, blocked + shown in UI
7. Session ends → token auto-expires
8. Audit feed: SUBMITTED → SCOPE_DERIVED → APPROVED → TOKEN_ISSUED → SCOPE_DENIED → SESSION_ENDED
9. Admin revokes a live token → agent's next call → 410
```
The demo is the pitch: **agents get exactly what the task needs, nothing more, and only until the job is done.**

---

## MILESTONES & NOTIFICATIONS
The Bark `curl` below is a **build-completion ping to my phone** — NOT a product feature. After finishing everything (or at a key milestone: Phase 3, 4, 8, 10, 12, 16), run:
```bash
curl -s "https://api.day.app/Ty6uAVeqkSq5D2u35yMotQ/Alert%20Sound/[URL_ENCODED_MESSAGE]?sound=birdsong"
```
Then print:
```
=== 🐕 MILESTONE COMPLETE - READY FOR REVIEW 🐕 ===
DONE: [what was built]
DOCS: [README/reqs/.gitignore/config/API-contract updated? Y/N]
NEXT: [immediate next step]
FILES: [files touched]
DEMOABLE?: [can this be shown in the UI? Y/N — must be Y once dashboard exists]
SECRETS_EXPOSED?: [touched plaintext credentials? must be N]
```

---

## WORKFLOW
1. Restate the phase goal in one line before starting.
2. Build in order — one phase at a time, each importable/runnable and (post-dashboard) demoable.
3. Edit existing files; create new only when none fits.
4. Hardcode config in `config.py`. No `.env`.
5. Throw visible errors to console + dashboard. No silent try/except.
6. Raw passwords never leave `core/vault.py`; every other layer uses scoped tokens/hints.
7. Keep the UI bound to the documented API contract so the final sketch swaps in cleanly.
8. Update living docs before each commit block.
9. Ask before: deleting files, adding packages, schema changes, OAuth app registration, or changing a route the UI depends on.
10. Code like a lazy senior dev — no abstractions until needed twice.

## CONTEXT HYGIENE
- Append to every reply: `CTX: <low|med|HIGH>`
- If HIGH or repeated tool errors → output: `⚠️ Run /clear now`
- Use /compact every ~40 exchanges

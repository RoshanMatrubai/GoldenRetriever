# GoldenRetriever — Live Demo Script

Target runtime: ~90 seconds for the happy path.  
Practice this a couple of times before pitching.

---

## Setup (do before the audience arrives)

```bash
# Terminal A — backend (dashboard :5001 + agent API :5002)
python main.py

# Terminal B — frontend dev server
npm --prefix ui install   # first time only
npm --prefix ui run dev

# Terminal C — smoke-test agent (keep ready to run)
# python simulate_agent.py
```

Open **http://localhost:5173** (or whatever Vite prints) in a browser.  
Confirm the Pending tab is empty and the Audit feed shows recent events.

---

## Act 1 — Agent Requests Access (0–15 s)

**Say:** "An AI agent needs to compare Amazon prices. Instead of handing it a password, it calls GoldenRetriever."

**Run** (Terminal C):
```bash
python simulate_agent.py --service amazon --task "compare prices on these 3 items"
```

**Point to:** The terminal output showing:
```
derived scope = ['read', 'search']
```

**Say:** "GoldenRetriever's policy engine read the task and derived the minimum permission set: search and read — *no purchase, no delete*."

**Point to:** The UI Pending tab — a new approval card appeared instantly via SocketIO with:
- Agent ID, service, task description
- Scope badges: `search` `read`  (green)
- No `purchase` badge — that action is absent from the derived scope

---

## Act 2 — Admin Approves (15–30 s)

**Say:** "The admin reviews the derived scope and decides: yes, this agent should be able to search and read, nothing more."

**Click:** the **Approve** button on the pending card.

**Point to:**
- The card moves off the Pending tab
- The **Sessions** tab gains a new row with:
  - Scope: `search read`
  - TTL countdown (15-minute session)
  - Token ID

**In Terminal C**, the agent's poll completes:
```
[OK]  APPROVED — scoped JWT received
```

**Say:** "The agent receives a short-lived Ed25519-signed JWT. The scope is locked into the signature — it can't be widened without a new request and a new admin approval."

---

## Act 3 — In-Scope Action Succeeds (30–45 s)

**Point to** Terminal C output:
```
[200 OK ]  search        (price comparison search) — in scope, allowed
[200 OK ]  read          (read product details) — in scope, allowed
```

**Point to** the Audit feed in the UI — `SCOPE_CHECK` events appear for each allowed action.

**Say:** "The agent searches and reads — both actions are in scope, both succeed."

---

## Act 4 — Out-of-Scope Action Blocked (45–60 s)

**Point to** Terminal C output:
```
[403 DENY]  purchase      (checkout / place order) — out of scope, SCOPE_DENIED logged
[403 DENY]  delete        (cancel an order) — out of scope, SCOPE_DENIED logged
```

**Point to** the Audit feed — `SCOPE_DENIED` events appear for `purchase` and `delete`.

**Say:** "The agent tried to check out. GoldenRetriever blocked it immediately — `purchase` was never in the signed scope, so the JWT itself proves the denial is correct. The audit event is immutable."

---

## Act 5 — Session Ends & Token Expires (60–75 s)

**Click:** **End Session** on the active session in the Sessions tab.

**Point to:**
- The session row disappears (or turns red)
- The Audit feed shows `SESSION_ENDED`

**In Terminal C**:
```
[OK]  Session ended via dashboard — SESSION_ENDED logged in audit
[OK]  GET /agent/token/<id>… → 410 EXPIRED ✓
```

**Say:** "Session ended. The token is dead — 410 on every subsequent poll. The agent can't reuse it, can't renew it. If it needs to do more work, it submits a new request and goes through the same approval flow."

---

## Act 6 — Full Audit Trail (75–90 s)

**Click** the **Audit** tab in the UI.

**Walk through** the event timeline:
```
SUBMITTED       → agent requested amazon access
SCOPE_DERIVED   → policy engine derived [read, search]
APPROVED        → admin clicked Approve
TOKEN_ISSUED    → Ed25519 JWT issued, hint encrypted
SCOPE_CHECK     → search — allowed
SCOPE_CHECK     → read — allowed
SCOPE_DENIED    → purchase — blocked
SCOPE_DENIED    → delete — blocked
SESSION_ENDED   → admin ended session
```

**Say:** "Every action is logged append-only. You get a complete, tamper-evident chain from request to expiry. Compliance, audit, incident response — all covered."

---

## Bonus: SDK Mode

Show the same flow using the Python SDK:
```bash
python simulate_agent.py --mode sdk
```

Output confirms: `request_access()` blocks, `verify_token()` checks the Ed25519 signature, `get_session()` builds an authenticated `requests.Session`, `check_action()` raises `ScopeViolation` on `purchase`.

## Bonus: MCP Mode (Claude CLI integration)

Show MCP tool call simulation:
```bash
python simulate_agent.py --mode mcp
```

This runs the exact same logic the Claude CLI agent calls via the MCP server (`request_access`, `list_available_services`, `revoke_token`), verifying the full integration path.

To wire GoldenRetriever into Claude Code's MCP config:
```bash
python main.py --mcp   # prints the config snippet to paste into ~/.claude.json
```

---

## Common Questions

**Q: What if the agent needs to buy something for real?**  
A: It submits a new request with a task like "purchase item X", the policy engine includes `purchase` in the derived scope, and the admin approves that specific grant. Each grant is task-bound and expires independently.

**Q: What if the admin is unavailable?**  
A: The pending request expires after 60 seconds (configurable). The agent re-requests when it can be serviced. No access is ever auto-granted.

**Q: Can an agent widen its own scope?**  
A: No. The scope is derived server-side from the task text, embedded in the signed JWT, and enforced on every API call. The agent cannot modify what it was granted.

**Q: What happens if a token leaks?**  
A: It's scoped to a specific task and expires at session end (max 15 minutes). The admin can revoke it instantly via the dashboard. The audit log records exactly what actions were taken with it before revocation.

**Q: Is this production-ready?**  
A: The crypto is production-grade (Argon2id, AES-256-GCM, Ed25519). The OAuth and Playwright service adapters use real provider flows. The placeholder client IDs in `config.py` need replacing with real app registrations before pointing at live services.

# Doberman — Demo Script
> One command, one browser tab, five clicks. ~90 seconds.

---

## 0 · Setup (once, before the demo)

```bash
./start.sh
```

That's it. The script:
- Kills anything on ports 5001, 5002, 5173.
- Starts the backend (Flask + SocketIO on :5001 / :5002).
- Starts the Vite dev server (React UI on :5173).
- Opens **http://localhost:5173** in your browser automatically.

You should see the Doberman bento dashboard, connection dot **green**, all four tiles visible.

---

## The pitch (say this while pointing at the screen)

> "Companies don't hand their AI agents passwords. Doberman gives each agent exactly the permissions one task needs — nothing more — as a short-lived signed token that expires the moment the job ends. Every grant is visible, logged, and one-click revocable."

---

## Act 1 — Agent requests access

**What to click:** Demo Controls bar (top center) → select **🛒 Amazon** → click **▶ Simulate Request**

**What you'll see:**
- A toast slides up: *"New request — Amazon · agent:demo-agent"*
- A card appears in the **Pending Approvals** tile with a warm amber border flash.
- The card shows the agent's task: *"compare prices on these 3 laptops"*
- Beneath the task: the derived scope — `search` `read` — **no `purchase`, no `checkout`**.

**What to say:**
> "The agent asked for Amazon access. Our policy engine read the task and derived the minimum scope — search and read only. The agent never sees credentials, never gets asked for them."

---

## Act 2 — Admin approves

**What to click:** Click **✓ Approve** on the pending card.

**What you'll see:**
- The card collapses and slides out with a spring animation.
- The **Active Sessions** tile border flashes green; a new session card appears with a pulsing green dot, showing `search` `read` scope badges and a live TTL countdown.
- The **Audit Log** tile (right column) streams four events:
  - `SUBMITTED` (red)
  - `SCOPE_DERIVED` (indigo)
  - `APPROVED` (green)
  - `TOKEN_ISSUED` (green)

**What to say:**
> "I approve it. The agent immediately receives a short-lived Ed25519-signed JWT — scoped to exactly those two actions, expiring at session end. The audit trail is already complete."

---

## Act 3 — In-scope action (allowed)

**What to click:** Click **✓ In-Scope** in the Demo Controls bar.

**What you'll see:**
- The Demo Controls bar briefly shows: `search: ALLOWED ✓` in green.
- Audit log gets a new `ACTION_ALLOWED` event in green.

**What to say:**
> "The agent tries to search Amazon. That's in scope — it goes through, green."

---

## Act 4 — Out-of-scope action (blocked)

**What to click:** Click **✕ Blocked** in the Demo Controls bar.

**What you'll see:**
- The Demo Controls bar shows: `purchase: BLOCKED ✕` in red.
- Audit log gets a `SCOPE_DENIED` event in red, detail shows *"purchase not in scope [search, read]"*.

**What to say:**
> "The agent tries to check out. Blocked — the token literally doesn't carry purchase permission. The agent can't exceed its mandate even if the underlying service would allow it."

---

## Act 5 — Session ends, token dies

**What to click:** In the **Active Sessions** tile, click **End Session** on the session card.

**What you'll see:**
- Session card disappears; a red "Session ended — Amazon (ended by admin)" banner animates in.
- Audit log gets `SESSION_ENDED` in amber.
- (If the agent calls the API now it gets HTTP 410 Gone.)

**What to say:**
> "Session over. The token is dead — not expired, not invalid: gone. Any subsequent call from the agent returns 410. Re-access requires a new request, a new approval."

---

## Act 6 — Show the audit trail

**What to point at:** The **Audit Log** tile (right column, full height).

Events in order from top:
```
HH:MM:SS  SESSION_ENDED   Amazon
HH:MM:SS  SCOPE_DENIED    Amazon · [search, read] · purchase not in scope
HH:MM:SS  ACTION_ALLOWED  Amazon · [search, read] · search
HH:MM:SS  TOKEN_ISSUED    Amazon · [search, read]
HH:MM:SS  APPROVED        Amazon
HH:MM:SS  SCOPE_DERIVED   Amazon · [search, read]
HH:MM:SS  SUBMITTED       Amazon
```

**What to say:**
> "Every grant, every action, every block — immutable, timestamped, visible. This is the compliance story: you can show exactly what each agent was allowed to do, and when."

---

## Optional extras (if time / if asked)

| Question / Prompt | Action |
|---|---|
| "Show me GitHub" | Select 🐱 GitHub → Simulate Request → Approve |
| "What if Slack?" | Select 💬 Slack → Simulate Request — derived scope: `read`, `summarize` |
| "Revoke live?" | With an active session, click End Session mid-demo — 410 immediately |
| "Multiple agents?" | Simulate Request twice without approving — two cards in Pending tile |
| "MCP server?" | `python3 main.py --mcp` — prints Claude CLI config snippet for the stdio MCP server |

---

## Teardown

Press **Ctrl+C** in the terminal where `start.sh` is running. It kills both processes cleanly.

---

## Common gotchas

| Symptom | Fix |
|---|---|
| Connection dot stays grey | Backend didn't start — check `/tmp/gr-backend.log` |
| "No active sessions" on Blocked click | Approve a request first (Act 2) |
| Card doesn't disappear after Approve | SocketIO may be disconnected — refresh the tab |
| Port already in use | `start.sh` auto-kills on startup; if it fails, `lsof -ti:5001 \| xargs kill` |

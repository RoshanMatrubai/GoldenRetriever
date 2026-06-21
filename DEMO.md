# Doberman — Demo Script
> One command, one browser tab. ~90 seconds.

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

You should see the new Doberman Sidebar dashboard. Check the bottom left of the sidebar — the connection dot should say **Live** in green.

---

## The pitch (say this while pointing at the screen)

> "Companies don't hand their AI agents passwords. Doberman gives each agent exactly the permissions one task needs — nothing more — as a short-lived signed token that expires the moment the job ends. Every grant is visible, logged, and one-click revocable."

---

## Act 1 — Agent requests access

**Where to go:** Click **Requests** on the left sidebar.

**What to click:** In the Demo Controls (top right), select **Amazon** from the dropdown → click **▶ Simulate request**

**What you'll see:**
- A toast notification slides in.
- A card appears in the list with a **Pending** status.
- The card shows the agent's task: *"compare prices on these 3 laptops"*
- Beneath the task, the derived scope is listed — `search` `read` — **no `purchase`, no `delete`**.

**What to say:**
> "The agent asked for Amazon access. Our policy engine read the task and automatically derived the minimum scope — search and read only. The agent never sees our actual credentials."

---

## Act 2 — Admin approves

**What to click:** Click **✓ Approve** on the pending card.

**What you'll see:**
- The card collapses and disappears.

**What to say:**
> "I approve the request. The agent is immediately issued a short-lived, Ed25519-signed JWT that is strictly scoped to those two actions."

---

## Act 3 — In-scope action (allowed)

**Where to go:** Click **Active Sessions** on the left sidebar.

**What you'll see:**
- A new session card appears with a pulsing green **LIVE** badge.
- You can see the `search` and `read` scope tags and a live TTL countdown.

**What to click:** Under "Try an action" on the session card, click **Search products**.

**What you'll see:**
- The button flashes green and changes to `✓ Search products`.

**What to say:**
> "The agent tries to search Amazon. Because 'search' is mathematically proven to be inside the signed scope, the gateway allows the API call."

---

## Act 4 — Out-of-scope action (blocked)

**What to click:** Under "Try an action", click **Add to cart**.

**What you'll see:**
- The button flashes red and changes to `✕ Add to cart`.

**What to say:**
> "Now, what if the AI hallucinates and tries to check out a shopping cart? The gateway intercepts the call, checks the signed token, sees that 'purchase' is out of scope, and instantly blocks it. The blast radius is totally contained."

---

## Act 5 — Session ends, token dies

**What to click:** On the session card, click **✕ End Session**.

**What you'll see:**
- The session card disappears.

**What to say:**
> "Session over. The token is dead — not just expired, but actively revoked. Any subsequent call from the agent is blocked."

---

## Act 6 — Show the audit trail

**Where to go:** Click **Audit Log** on the left sidebar.

**What you'll see:**
A chronological feed of the entire lifecycle.

**What to point at:** Read the events from top to bottom (the newest is at the top):
- `SESSION_ENDED`
- `SCOPE_DENIED` (detail shows *"purchase not in scope [search, read]"*)
- `ACTION_ALLOWED`
- `TOKEN_ISSUED`
- `APPROVED`
- `SCOPE_DERIVED`
- `SUBMITTED`

**What to say:**
> "Every grant, every action, every block — immutable, timestamped, and visible. This is the compliance story: you can show exactly what each agent was allowed to do, and when."

---

## Teardown

Press **Ctrl+C** in the terminal where `start.sh` is running. It kills both processes cleanly.

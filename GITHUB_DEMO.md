# Doberman — GitHub Demo Script

This script walks through the **GitHub** scenario, demonstrating how Doberman prevents an autonomous agent from pushing unauthorized code commits to your repository.

---

## The setup (Before the demo)

Make sure your local environment is running:
```bash
./start.sh
```
Open **http://localhost:5173** and verify the dashboard says **Live** in the bottom left.

---

## Act 1 — The Request

**Where to go:** Click **Requests** on the left sidebar.

**What to click:** In the Demo Controls (top right), select **GitHub** from the dropdown → click **▶ Simulate request**

**What you'll see:**
- A card appears in the Pending list.
- The task might read something like: *"look at the open issues in this repo"*
- Beneath the task, the derived scope is listed — `search` `read` — **no `write`, no `delete`**.

**What to say:**
> "Let's say an AI coding agent wants to help us triage some bugs. It asks Doberman for GitHub access to read the open issues. 
> 
> Doberman's policy engine automatically derives the minimum necessary scope: it grants 'search' and 'read', but strictly denies 'write' access (meaning it cannot push code) and 'delete' access."

---

## Act 2 — The Approval

**What to click:** Click **✓ Approve** on the pending card.

**What you'll see:**
- The card collapses.

**What to say:**
> "I approve the request. The agent is instantly issued a short-lived cryptographic token scoped precisely to read-only actions."

---

## Act 3 — In-Scope Action (View Issues)

**Where to go:** Click **Active Sessions** on the left sidebar.

**What to click:** Under "Try an action" on the session card, click **View issues**.

**What you'll see:**
- The button flashes green and changes to `✓ View issues`.

**What to say:**
> "The agent successfully queries the GitHub API to view the issues. Because 'read' is inside its signed scope, Doberman allows the call."

---

## Act 4 — Out-of-Scope Action (Push Commit)

**What to click:** Under "Try an action", click **Push commit**.

**What you'll see:**
- The button flashes red and changes to `✕ Push commit`.

**What to say:**
> "But what happens if the AI agent hallucinates and tries to push a rogue code commit to our main branch? 
> 
> Doberman intercepts the API call, reads the token, sees that 'write' is out of scope, and instantly blocks the push. The agent cannot write to your repository, no matter what prompt injection it receives."

---

## Act 5 — Revocation & Audit Trail

**What to click:** 
1. On the session card, click **✕ End Session**.
2. Click **Audit Log** on the left sidebar.

**What to point at:** The red `SCOPE_DENIED` event showing that a `write` action was blocked because it was not in `[search, read]`.

**What to say:**
> "Once the job is done, the token is revoked. And if we check our immutable audit log, we have a permanent cryptographic record of exactly when the agent tried to push code, and exactly how Doberman blocked it. Total security for autonomous engineering."

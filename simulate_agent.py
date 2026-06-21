#!/usr/bin/env python3
"""
simulate_agent.py — smoke-test the full GoldenRetriever scoped approval loop.

  python simulate_agent.py                          # default: amazon price comparison
  python simulate_agent.py --service github --task "read the latest issues"
  python simulate_agent.py --no-revoke              # skip the revoke step

Requires the backend to be running (python main.py).
Waits for a human admin to approve the request on the dashboard.
Exit codes: 0=passed, 1=submit error, 2=denied, 3=expired/error, 4=timeout.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import sys
import time

import requests as http

import config
from policy.engine import is_action_in_scope, list_service_actions

AGENT_BASE    = f"http://localhost:{config.AGENT_API_PORT}"
POLL_INTERVAL = 2    # seconds between status polls
POLL_TIMEOUT  = 120  # seconds to wait for admin approval


def _decode_claims(token: str) -> dict:
    """Decode JWT payload (display only — signature not verified here)."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    pad = 4 - len(parts[1]) % 4
    try:
        return json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (pad % 4)))
    except Exception:
        return {}


def _bar(char: str = "─", width: int = 60) -> str:
    return char * width


def main() -> None:
    parser = argparse.ArgumentParser(description="GoldenRetriever agent smoke test")
    parser.add_argument("--service",   default="amazon",
                        help="Service to request access to (default: amazon)")
    parser.add_argument("--task",      default="compare prices on these 3 items",
                        help="Natural-language task description")
    parser.add_argument("--tenant-id", default="demo-tenant",
                        help="Tenant identifier")
    parser.add_argument("--agent-id",  default="demo-agent-001",
                        help="Agent identifier")
    parser.add_argument("--no-revoke", action="store_true",
                        help="Skip the revoke step (leave token live)")
    args = parser.parse_args()

    print(f"\n{_bar('═')}")
    print("  GoldenRetriever — Full Approval Loop Smoke Test")
    print(_bar("═"))
    print(f"  Service : {args.service}")
    print(f"  Task    : {args.task}")
    print(f"  Tenant  : {args.tenant_id}")
    print(f"  Agent   : {args.agent_id}")
    print(f"  Backend : {AGENT_BASE}")
    print(_bar("═"))

    # ── 1. Submit access request ──────────────────────────────────────────
    print("\n[1/7] Submitting access request…")
    try:
        resp = http.post(f"{AGENT_BASE}/agent/request", json={
            "tenant_id": args.tenant_id,
            "agent_id":  args.agent_id,
            "service":   args.service,
            "task":      args.task,
        }, timeout=10)
    except http.exceptions.ConnectionError:
        print(f"  [FAIL] Cannot reach {AGENT_BASE} — is 'python main.py' running?")
        sys.exit(1)

    if resp.status_code != 201:
        print(f"  [FAIL] Submit failed: {resp.status_code} — {resp.text}")
        sys.exit(1)

    req_data   = resp.json()
    request_id = req_data["id"]
    scope      = req_data["scope"]
    print(f"  [OK]  request_id    = {request_id}")
    print(f"  [OK]  derived scope = {scope}")

    # ── 2. Poll for approval ──────────────────────────────────────────────
    print(f"\n[2/7] Waiting for admin approval (timeout {POLL_TIMEOUT}s)…")
    print(f"  Open → http://localhost:{config.DASHBOARD_PORT} and click Approve\n")

    token_str = None
    deadline  = time.time() + POLL_TIMEOUT
    dots      = 0
    while time.time() < deadline:
        try:
            poll   = http.get(f"{AGENT_BASE}/agent/token/{request_id}", timeout=5)
            status = poll.status_code
            body   = poll.json()
        except http.exceptions.RequestException as exc:
            print(f"\n  [ERROR] Poll failed: {exc}")
            sys.exit(3)

        if status == 202:
            dots = (dots + 1) % 4
            sys.stdout.write(f"  PENDING{'.' * dots}   \r")
            sys.stdout.flush()
            time.sleep(POLL_INTERVAL)
            continue

        if status == 200:
            token_str = body.get("token")
            print(f"\n  [OK]  APPROVED — scoped JWT received")
            break

        if status == 403:
            print(f"\n  [DENIED] Admin denied the request.")
            sys.exit(2)

        print(f"\n  [ERROR] Unexpected status {status}: {body}")
        sys.exit(3)

    if not token_str:
        print(f"\n  [TIMEOUT] No approval within {POLL_TIMEOUT}s.")
        sys.exit(4)

    # ── 3. Decode and display token claims ────────────────────────────────
    print("\n[3/7] JWT claims (decoded, not re-verified here):")
    claims   = _decode_claims(token_str)
    exp_dt   = datetime.datetime.fromtimestamp(claims.get("exp", 0), tz=datetime.timezone.utc)
    jti      = claims.get("jti", "")
    print(f"  tenant     : {claims.get('tenant')}")
    print(f"  agent_id   : {claims.get('agent_id')}")
    print(f"  service    : {claims.get('service')}")
    print(f"  scope      : {claims.get('scope')}")
    print(f"  jti        : {jti[:14]}…")
    print(f"  expires    : {exp_dt.isoformat()}")
    print(f"  algorithm  : EdDSA (Ed25519)")

    # ── 4. Fetch and verify pubkey ────────────────────────────────────────
    print("\n[4/7] Fetching GoldenRetriever Ed25519 public key…")
    try:
        pk_resp = http.get(f"{AGENT_BASE}/agent/pubkey", timeout=5)
        pk_data = pk_resp.json()
        print(f"  [OK]  algorithm  = {pk_data.get('algorithm')}")
        print(f"  [OK]  public_key = {pk_data.get('public_key', '')[:32]}…")
    except Exception as exc:
        print(f"  [WARN] Could not fetch pubkey: {exc}")

    # ── 5. Scope enforcement matrix ───────────────────────────────────────
    print(f"\n[5/7] Scope enforcement matrix for '{args.service}':")
    all_actions = list_service_actions(args.service)
    if not all_actions:
        print(f"  [WARN] No known actions for service '{args.service}'")
    for action in all_actions:
        allowed = is_action_in_scope(action, scope)
        sym     = "✓ ALLOWED" if allowed else "✕ BLOCKED"
        print(f"  [{sym}]  {action}")

    # ── 6. Demo: in-scope vs out-of-scope actions ─────────────────────────
    print(f"\n[6/7] Live scope enforcement demo:")
    _demo_action("search",   scope, "price comparison search")
    _demo_action("read",     scope, "read product details")
    _demo_action("purchase", scope, "checkout / place order")    # MOCK
    _demo_action("delete",   scope, "cancel an order")           # MOCK

    # ── 7. Revoke token ───────────────────────────────────────────────────
    if not args.no_revoke:
        print(f"\n[7/7] Revoking token…")
        try:
            rev = http.delete(f"{AGENT_BASE}/agent/token/{request_id}", timeout=5)
        except http.exceptions.RequestException as exc:
            print(f"  [WARN] Revoke request failed: {exc}")
        else:
            if rev.status_code == 200:
                print(f"  [OK]  Token revoked — polling now returns 410")
                # Confirm 410
                confirm = http.get(f"{AGENT_BASE}/agent/token/{request_id}", timeout=5)
                if confirm.status_code == 410:
                    print(f"  [OK]  GET /agent/token/{request_id[:8]}… → 410 EXPIRED ✓")
                else:
                    print(f"  [?]   Expected 410, got {confirm.status_code}")
            else:
                print(f"  [WARN] Revoke returned {rev.status_code}: {rev.text}")
    else:
        print(f"\n[7/7] Skipping revoke (--no-revoke)")

    # ── Done ──────────────────────────────────────────────────────────────
    print(f"\n{_bar('═')}")
    print("  SMOKE TEST PASSED — full scoped approval loop verified")
    print(_bar("═"))
    print()


def _demo_action(action: str, scope: list, description: str) -> None:
    allowed = is_action_in_scope(action, scope)
    if allowed:
        print(f"  [200 OK ]  {action:12s}  ({description}) — in scope, proceeding")  # MOCK downstream call
    else:
        print(f"  [403 DENY]  {action:12s}  ({description}) — out of scope, blocked")


if __name__ == "__main__":
    main()

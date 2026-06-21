"""
Doberman MCP server — Claude CLI agent integration via FastMCP stdio.

Tools exposed:
  request_access(service, task)    — block until approved; return scoped token info
  list_available_services()        — list services + their action catalogs
  revoke_token(request_id)         — revoke an approved or pending request

Never raises from tool handlers — errors are returned as structured dicts so the
Claude CLI agent always receives a readable response.
"""
from __future__ import annotations

import sys

import config
from agent.sdk import (
    ApprovalDenied, ApprovalExpired, ApprovalTimeout, DobermanClient,
)
from fastmcp import FastMCP
from policy.engine import list_service_actions, list_supported_services

mcp = FastMCP(
    "Doberman",
    instructions=(
        "Doberman is a scoped access broker. Before an agent can use a "
        "third-party service, it must request access and wait for admin approval. "
        "Tokens are short-lived, scoped to the minimum permissions the task needs, "
        "and automatically expire at session end. Use request_access() to obtain a "
        "token, then pass it to your downstream calls. Revoke when done."
    ),
)


def _make_client() -> DobermanClient:
    return DobermanClient(
        base_url=config.MCP_AGENT_API_URL,
        tenant_id=config.MCP_DEFAULT_TENANT,
        agent_id=config.MCP_DEFAULT_AGENT,
        timeout=config.MCP_POLL_TIMEOUT,
    )


@mcp.tool()
def request_access(service: str, task: str) -> dict:
    """
    Request scoped access to a third-party service for a specific task.

    Submits the request to Doberman, derives the minimum permission
    scope required for the task, and blocks until an admin approves or denies
    (or the timeout elapses).

    Returns a dict with:
      success      — True if approved and a token was issued
      token        — signed Ed25519 JWT (present on success)
      request_id   — use this to revoke the token when the task is done
      scope        — list of allowed actions (e.g. ["search", "read"])
      service      — the service name
      error        — human-readable error message (present on failure)
      reason       — one of "denied" | "expired" | "timeout" | "error"

    Never raises — always returns a structured result.
    """
    print(
        f"[mcp] request_access called: service={service!r} task={task!r}",
        file=sys.stderr,
        flush=True,
    )
    client = _make_client()
    try:
        token, request_id = client.request_access(service, task)
        claims = client.verify_token(token)
        scope = claims.get("scope", [])
        print(
            f"[mcp] approved — request_id={request_id[:8]}… scope={scope}",
            file=sys.stderr,
            flush=True,
        )
        return {
            "success": True,
            "token": token,
            "request_id": request_id,
            "scope": scope,
            "service": service,
            "expires_at": claims.get("exp"),
        }
    except ApprovalDenied as exc:
        print(f"[mcp] denied: {exc}", file=sys.stderr, flush=True)
        return {
            "success": False,
            "service": service,
            "error": str(exc),
            "reason": "denied",
        }
    except ApprovalExpired as exc:
        print(f"[mcp] expired: {exc}", file=sys.stderr, flush=True)
        return {
            "success": False,
            "service": service,
            "error": str(exc),
            "reason": "expired",
        }
    except ApprovalTimeout as exc:
        print(f"[mcp] timeout: {exc}", file=sys.stderr, flush=True)
        return {
            "success": False,
            "service": service,
            "error": str(exc),
            "reason": "timeout",
        }
    except Exception as exc:
        print(f"[mcp] request_access error: {exc}", file=sys.stderr, flush=True)
        return {
            "success": False,
            "service": service,
            "error": f"Unexpected error: {exc}",
            "reason": "error",
        }


@mcp.tool()
def list_available_services() -> dict:
    """
    List all services Doberman can broker access to, with their allowed actions.

    Returns a dict with:
      services — list of {service, actions} objects
        service — service name (e.g. "amazon", "github")
        actions — list of action names the policy engine knows about

    Use this to discover which service name to pass to request_access().
    """
    services = []
    for svc in list_supported_services():
        services.append({
            "service": svc,
            "actions": list_service_actions(svc),
        })
    return {"services": services}


@mcp.tool()
def revoke_token(request_id: str) -> dict:
    """
    Revoke an approved token or cancel a pending request.

    Call this when the task is complete so the token expires immediately
    rather than waiting for its TTL. Good practice for least-privilege hygiene.

    Returns a dict with:
      success    — True if revoked
      request_id — echoed back
      error      — error message if revocation failed
    """
    print(
        f"[mcp] revoke_token called: request_id={request_id[:8]}…",
        file=sys.stderr,
        flush=True,
    )
    client = _make_client()
    try:
        client.revoke(request_id)
        return {"success": True, "request_id": request_id}
    except Exception as exc:
        print(f"[mcp] revoke error: {exc}", file=sys.stderr, flush=True)
        return {
            "success": False,
            "request_id": request_id,
            "error": str(exc),
        }


def run():
    """Launch the MCP stdio server — called by main.py --mcp."""
    mcp.run(transport="stdio", show_banner=False)

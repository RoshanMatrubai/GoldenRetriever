"""
Adapter registry — maps service names to the right auth strategy and resolves
credential hints for token issuance.
"""
from __future__ import annotations

from auth.adapters.amazon import AmazonAdapter
from auth.adapters.generic import ServiceAdapter
from auth.adapters.github import GithubAdapter
from auth.adapters.google import GoogleAdapter

_REGISTRY: dict[str, ServiceAdapter] = {
    "google": GoogleAdapter(),
    "github": GithubAdapter(),
    "amazon": AmazonAdapter(),
}


def get_adapter(service: str) -> ServiceAdapter:
    return _REGISTRY.get(service.lower(), ServiceAdapter())


def resolve_hint(service: str, tenant_id: str, vault) -> dict:
    """
    Resolve a credential hint for the given service + tenant.
    Always returns a dict (falls back to stub on error — logs loudly).
    """
    adapter = get_adapter(service)
    try:
        hint = adapter.resolve_hint(tenant_id, vault)
        print(f"[adapters] hint resolved for {service} (type={hint.get('type')})", flush=True)
        return hint
    except Exception as exc:
        print(
            f"[adapters] hint resolution FAILED for {service}: {exc} — falling back to stub",
            flush=True,
        )
        return {"type": "stub", "service": service}

"""Base adapter — subclass per service."""
from __future__ import annotations


class ServiceAdapter:
    service_name: str = "generic"
    auth_type: str = "stub"

    def resolve_hint(self, tenant_id: str, vault) -> dict:
        """Return a hint dict to embed in the scoped JWT."""
        return {"type": "stub", "service": self.service_name}

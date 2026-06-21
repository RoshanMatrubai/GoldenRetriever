"""GitHub OAuth adapter — looks up stored OAuth tokens and refreshes if needed."""
from __future__ import annotations

from auth.adapters.generic import ServiceAdapter


class GithubAdapter(ServiceAdapter):
    service_name = "github"
    auth_type = "oauth"

    def resolve_hint(self, tenant_id: str, vault) -> dict:
        from auth.oauth import get_oauth_hint, refresh_if_needed

        accounts = vault.list_service_accounts(tenant_id, reveal=True)
        acct = next((a for a in accounts if a["service"] == "github"), None)
        if not acct:
            print("[adapter:github] no GitHub account found — stub hint", flush=True)
            return {"type": "stub", "service": "github"}

        creds = refresh_if_needed(acct["credentials"], "github", acct["id"], vault)
        return get_oauth_hint(creds, "github")

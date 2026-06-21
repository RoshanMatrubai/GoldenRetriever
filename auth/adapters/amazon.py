"""Amazon headless adapter — uses Playwright to log in and return session cookies."""
from __future__ import annotations

from auth.adapters.generic import ServiceAdapter


class AmazonAdapter(ServiceAdapter):
    service_name = "amazon"
    auth_type = "headless"

    def resolve_hint(self, tenant_id: str, vault) -> dict:
        from auth.session import LoginFailed, TwoFactorRequired, headless_login

        accounts = vault.list_service_accounts(tenant_id, reveal=True)
        acct = next((a for a in accounts if a["service"].lower() == "amazon"), None)
        if not acct:
            print("[adapter:amazon] no Amazon account found — stub hint", flush=True)
            return {"type": "stub", "service": "amazon"}

        username = acct["username"]
        password = acct["credentials"].get("password", "")
        try:
            return headless_login("amazon", username, password, vault)
        except TwoFactorRequired as exc:
            print(f"[adapter:amazon] 2FA required: {exc}", flush=True)
            raise
        except LoginFailed as exc:
            print(f"[adapter:amazon] login failed: {exc}", flush=True)
            raise

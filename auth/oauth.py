"""
Google and GitHub OAuth 2.0 authorization-code flow with encrypted token storage.

MOCK: OAUTH_SERVICES in config.py contains placeholder client_id/client_secret.
      Fill in real app credentials before running the live OAuth flow.
      The flow structure (state, code exchange, refresh) is production-ready.
"""
from __future__ import annotations

import datetime
import secrets

from authlib.integrations.requests_client import OAuth2Session  # type: ignore

import config
from core.vault import Vault

_PROVIDERS: dict[str, dict] = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
    },
}


class OAuthError(Exception):
    pass


def _make_session(service: str) -> OAuth2Session:
    svc = config.OAUTH_SERVICES.get(service)
    if not svc:
        raise OAuthError(f"No OAuth config for service: {service}")
    return OAuth2Session(
        client_id=svc["client_id"],
        client_secret=svc["client_secret"],
        scope=svc.get("scope", ""),
        redirect_uri=config.OAUTH_REDIRECT_URI,
    )


def begin_oauth(service: str) -> tuple[str, str]:
    """Return (auth_url, state) to redirect the user to the provider."""
    provider = _PROVIDERS.get(service)
    if not provider:
        raise OAuthError(f"Unknown OAuth service: {service}")
    state = secrets.token_urlsafe(32)
    sess = _make_session(service)
    extra = {}
    if service == "google":
        extra = {"access_type": "offline", "prompt": "consent"}
    auth_url, _ = sess.create_authorization_url(
        provider["authorize_url"], state=state, **extra
    )
    return auth_url, state


def complete_oauth(
    service: str, code: str, state: str, tenant_id: str, vault: Vault
) -> str:
    """
    Exchange authorization code for tokens; store encrypted in vault.
    Returns the vault account_id.
    """
    provider = _PROVIDERS.get(service)
    if not provider:
        raise OAuthError(f"Unknown OAuth service: {service}")
    sess = _make_session(service)
    token = sess.fetch_token(provider["token_url"], code=code, state=state)
    credentials = {
        "type": "oauth",
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token", ""),
        "token_type": token.get("token_type", "Bearer"),
        "expires_at": (
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=int(token.get("expires_in", 3600)))
        ).isoformat(),
        "scope": token.get("scope", ""),
    }
    username = f"{service}_oauth"
    account_id = vault.add_service_account(tenant_id, service, username, credentials)
    print(f"[oauth] stored {service} tokens for tenant {tenant_id} → account {account_id}", flush=True)
    return account_id


def refresh_if_needed(
    credentials: dict, service: str, account_id: str, vault: Vault
) -> dict:
    """
    Refresh the access token if it expires within 5 minutes.
    Updates vault in place; returns (possibly refreshed) credentials.
    """
    if credentials.get("type") != "oauth":
        return credentials
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        return credentials
    provider = _PROVIDERS.get(service)
    if not provider:
        return credentials

    try:
        expires_at = datetime.datetime.fromisoformat(credentials.get("expires_at", ""))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.UTC)
        if expires_at > datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5):
            return credentials
    except (ValueError, TypeError):
        pass  # unknown expiry — attempt refresh anyway

    sess = _make_session(service)
    new_token = sess.refresh_token(provider["token_url"], refresh_token=refresh_token)
    credentials = {
        **credentials,
        "access_token": new_token["access_token"],
        "refresh_token": new_token.get("refresh_token", refresh_token),
        "expires_at": (
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=int(new_token.get("expires_in", 3600)))
        ).isoformat(),
    }
    vault.update_service_account_credentials(account_id, credentials)
    print(f"[oauth] refreshed {service} token for account {account_id}", flush=True)
    return credentials


def get_oauth_hint(credentials: dict, service: str) -> dict:
    """Build the hint payload to embed in the scoped JWT."""
    return {
        "type": "oauth",
        "service": service,
        "access_token": credentials.get("access_token", ""),
        "token_type": credentials.get("token_type", "Bearer"),
        "scope": credentials.get("scope", ""),
        "expires_at": credentials.get("expires_at", ""),
    }

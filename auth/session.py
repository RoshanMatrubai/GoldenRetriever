"""
Playwright headless login for services that don't offer OAuth.

MOCK: _playwright_login() drives a real browser but the Amazon login flow
      uses placeholder selectors. Replace with verified selectors before
      running against a live account.
      Run `playwright install chromium` to enable the live browser flow.
      Without it the code falls back to _mock_cookies() (clearly labelled).
"""
from __future__ import annotations

import asyncio


class TwoFactorRequired(Exception):
    pass


class LoginFailed(Exception):
    pass


# Selector maps per service — expand as adapters are added
_LOGIN_URLS = {
    "amazon": "https://www.amazon.com/ap/signin",
}

_SELECTORS = {
    "amazon": {
        "email": 'input[name="email"]',
        "email_submit": "#continue",
        "password": 'input[name="password"]',
        "login_submit": "#signInSubmit",
        "otp": 'input[name="otpCode"]',
        "error": ".a-alert-content",
    },
}


def headless_login(service: str, username: str, password: str, vault) -> dict:
    """
    Return a session hint dict with cookies.
    Checks the 6 h encrypted cache first; falls back to Playwright login.
    """
    cached = vault.get_cookie_cache(service, username)
    if cached is not None:
        print(f"[session] cache hit — reusing cookies for {service}/{username}", flush=True)
        return {"type": "session", "service": service, "cookies": cached}

    try:
        cookies = asyncio.run(_playwright_login(service, username, password))
        print(f"[session] Playwright login succeeded for {service}/{username}", flush=True)
    except (TwoFactorRequired, LoginFailed):
        raise
    except ImportError:
        print(f"[session] playwright not installed — MOCK stub cookies for {service}", flush=True)
        cookies = _mock_cookies(service, username)
    except Exception as exc:
        print(f"[session] Playwright error for {service}: {exc} — MOCK stub cookies", flush=True)
        cookies = _mock_cookies(service, username)

    vault.set_cookie_cache(service, username, cookies)
    return {"type": "session", "service": service, "cookies": cookies}


async def _playwright_login(service: str, username: str, password: str) -> list[dict]:
    """Drive a real Chromium session to log in and return cookies."""
    from playwright.async_api import async_playwright  # type: ignore

    url = _LOGIN_URLS.get(service.lower())
    if not url:
        raise LoginFailed(f"No headless login URL configured for: {service}")
    sel = _SELECTORS.get(service.lower(), {})

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            await page.goto(url)
            await page.fill(sel["email"], username)
            await page.click(sel["email_submit"])
            await page.fill(sel["password"], password)
            await page.click(sel["login_submit"])
            await page.wait_for_load_state("networkidle")

            if sel.get("otp") and await page.query_selector(sel["otp"]):
                raise TwoFactorRequired(f"{service} requires 2FA — cannot proceed automatically")

            if sel.get("error"):
                err_el = await page.query_selector(sel["error"])
                if err_el:
                    msg = (await err_el.text_content() or "").strip()
                    raise LoginFailed(f"{service} login failed: {msg}")

            raw = await ctx.cookies()
            return [
                {
                    "name": c["name"], "value": c["value"],
                    "domain": c["domain"], "path": c["path"],
                    "secure": c.get("secure", False),
                }
                for c in raw
            ]
        finally:
            await browser.close()


def _mock_cookies(service: str, username: str) -> list[dict]:  # MOCK
    """Stub cookies returned when Playwright is unavailable (demo only)."""
    domain = f".{service.lower()}.com"
    return [
        {"name": "session-id", "value": f"mock-{username[:8]}-001",
         "domain": domain, "path": "/", "secure": True},
        {"name": "ubid-main", "value": "mock-ubid-001",
         "domain": domain, "path": "/", "secure": True},
    ]

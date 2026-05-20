"""CloakBrowser — stealth + privacy Playwright session for the search pipeline.

Features:
  - Anti-detection: navigator.webdriver=false, randomized UA/viewport/locale/timezone
  - Privacy: optional SOCKS5/HTTP proxy via CLOAK_PROXY_URL, isolated context per session
  - Visual: full-page fetch with JS rendering, screenshot, extracted text
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False
    logger.warning("playwright not installed — CloakBrowser unavailable")

# ── Config ────────────────────────────────────────────────────────────────────
_PROXY_URL      = os.getenv("CLOAK_PROXY_URL", "").strip()      # e.g. socks5://127.0.0.1:9050
_HEADLESS       = os.getenv("CLOAK_HEADLESS", "1") != "0"
_BROWSER_TYPE   = os.getenv("CLOAK_BROWSER_TYPE", "chromium")   # chromium|firefox|webkit
_FETCH_TIMEOUT  = int(os.getenv("CLOAK_FETCH_TIMEOUT_MS", "15000"))
_SCREENSHOT     = os.getenv("CLOAK_SCREENSHOT", "1") != "0"

# Realistic desktop UAs (Chrome 124 on Win/Mac/Linux)
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 2560, "height": 1440},
    {"width": 1280, "height": 800},
]

# JS injected into every page to mask automation fingerprints
_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'permissions', {
  get: () => ({ query: () => Promise.resolve({ state: 'granted' }) })
});
"""


class CloakBrowserSession:
    """One-shot stealth browser session: open → fetch → close."""

    def __init__(self) -> None:
        self._pw  = None
        self._browser = None
        self._context = None
        self._ua = random.choice(_USER_AGENTS)
        self._viewport = random.choice(_VIEWPORTS)

    async def __aenter__(self) -> "CloakBrowserSession":
        if not _PLAYWRIGHT_OK:
            raise RuntimeError("playwright not installed")
        self._pw = await async_playwright().__aenter__()
        launcher = getattr(self._pw, _BROWSER_TYPE)

        launch_kwargs: dict = {
            "headless": _HEADLESS,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ] if _BROWSER_TYPE == "chromium" else [],
        }
        if _PROXY_URL:
            launch_kwargs["proxy"] = {"server": _PROXY_URL}

        self._browser = await launcher.launch(**launch_kwargs)

        ctx_kwargs: dict = {
            "user_agent": self._ua,
            "viewport": self._viewport,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "color_scheme": random.choice(["dark", "light"]),
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-platform": '"Windows"',
                "sec-ch-ua-mobile": "?0",
            },
        }
        if _PROXY_URL:
            ctx_kwargs["proxy"] = {"server": _PROXY_URL}

        self._context = await self._browser.new_context(**ctx_kwargs)
        await self._context.add_init_script(_STEALTH_SCRIPT)
        return self

    async def __aexit__(self, *_) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.__aexit__(None, None, None)
        except Exception as exc:
            logger.debug("CloakBrowserSession teardown: %s", exc)

    async def fetch_page(self, url: str) -> dict:
        """Navigate to url, return rendered text + optional screenshot."""
        from core.url_guard import require_safe_url, UnsafeURLError  # type: ignore
        try:
            require_safe_url(url)
        except UnsafeURLError as _e:
            return {"url": url, "final_url": url, "title": "", "text": "",
                    "screenshot_b64": None, "status_code": 0, "error": f"SSRF blocked: {_e}"}
        page = await self._context.new_page()
        result: dict = {
            "url": url,
            "final_url": url,
            "title": "",
            "text": "",
            "screenshot_b64": None,
            "status_code": 0,
            "error": None,
        }
        try:
            response = await page.goto(url, timeout=_FETCH_TIMEOUT, wait_until="domcontentloaded")
            if response:
                result["status_code"] = response.status
                result["final_url"] = page.url
            # Wait briefly for JS to settle
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # networkidle can time out on heavy pages; proceed anyway
            result["title"] = await page.title()
            result["text"] = (await page.inner_text("body") or "").strip()[:8000]
            if _SCREENSHOT:
                try:
                    png = await page.screenshot(type="png", full_page=False)
                    result["screenshot_b64"] = base64.b64encode(png).decode()
                except Exception:
                    pass
        except Exception as exc:
            result["error"] = str(exc)
            logger.debug("CloakBrowser.fetch_page(%s): %s", url, exc)
        finally:
            await page.close()
        return result


async def fetch_url(url: str) -> dict:
    """Convenience: open a fresh cloaked session, fetch one URL, close."""
    async with CloakBrowserSession() as session:
        return await session.fetch_page(url)


def fetch_url_sync(url: str) -> dict:
    """Sync wrapper for use from non-async contexts."""
    try:
        return asyncio.get_event_loop().run_until_complete(fetch_url(url))
    except RuntimeError:
        return asyncio.run(fetch_url(url))

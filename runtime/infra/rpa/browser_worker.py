"""BrowserWorker — Playwright async browser sessions."""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Any, Optional

from .schema import BrowserAction, WorkerSession, SessionStatus, TakeoverToken, ActionResult
from .action_executor import ActionExecutor
from .replay_recorder import ReplayRecorder

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False
    logger.warning("playwright not installed — RPA browser workers unavailable")

_BROWSER_TYPE = os.getenv("WORKER_BROWSER", "chromium")
_HEADLESS = os.getenv("WORKER_HEADLESS", "1") != "0"


class BrowserWorker:
    """Owns one Playwright browser context for a session."""

    def __init__(self, session: WorkerSession):
        self.session = session
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._executor: Optional[ActionExecutor] = None
        self._recorder: Optional[ReplayRecorder] = None

    @property
    def available(self) -> bool:
        return _PLAYWRIGHT_OK

    async def start(self) -> None:
        if not _PLAYWRIGHT_OK:
            raise RuntimeError("playwright not installed")
        self._pw = await async_playwright().__aenter__()
        browser_launcher = getattr(self._pw, _BROWSER_TYPE)
        self._browser = await browser_launcher.launch(headless=_HEADLESS)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        self._executor = ActionExecutor(self._page)
        self._recorder = ReplayRecorder(self.session.tenant_id, self.session.session_id)
        self.session.status = SessionStatus.RUNNING
        # CDP URL only available for chromium
        if _BROWSER_TYPE == "chromium" and hasattr(self._browser, "ws_endpoint"):
            self.session.cdp_ws_url = self._browser.ws_endpoint
        logger.info("BrowserWorker %s started (%s)", self.session.session_id, _BROWSER_TYPE)

    async def execute(self, action: BrowserAction) -> ActionResult:
        if self._executor is None:
            return ActionResult(ok=False, action=action.type, error="worker_not_started")
        result = await self._executor.execute(action)
        # Capture screenshot for recording if action produced a visual change
        screenshot = None
        if self._page and result.ok and action.type not in (
                "screenshot", "wait", "key", "evaluate"):
            try:
                screenshot = await self._page.screenshot(type="png")
            except Exception:
                pass
        if self._recorder:
            self._recorder.record(result, screenshot)
        self.session.action_count += 1
        import time
        self.session.last_action_at = time.time()
        return result

    async def screenshot_bytes(self) -> Optional[bytes]:
        if self._page is None:
            return None
        try:
            return await self._page.screenshot(type="png")
        except Exception:
            return None

    def takeover_token(self) -> Optional[TakeoverToken]:
        if not self.session.cdp_ws_url:
            return None
        import time
        self.session.status = SessionStatus.PAUSED
        return TakeoverToken(
            session_id=self.session.session_id,
            cdp_url=self.session.cdp_ws_url,
            expires_at=time.time() + 3600,
            tenant_id=self.session.tenant_id,
        )

    async def stop(self) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.__aexit__(None, None, None)
        except Exception as e:
            logger.debug("BrowserWorker stop error: %s", e)
        finally:
            self.session.status = SessionStatus.TERMINATED
            logger.info("BrowserWorker %s terminated", self.session.session_id)

"""ActionExecutor — anti-hallucination safeguarded browser action runner."""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Optional

from .schema import ActionResult, ActionType, BrowserAction
from .visual_grounder import resolve_selector, screenshot_hash

logger = logging.getLogger(__name__)

_RATE_LIMIT_DELAY = 0.1  # 100ms between actions → max 10/sec


class ActionExecutor:
    def __init__(self, page: Any, rate_actions_per_sec: int = 10):
        self._page = page
        self._min_delay = 1.0 / max(1, rate_actions_per_sec)
        self._last_action_ts = 0.0

    async def execute(self, action: BrowserAction) -> ActionResult:
        # Rate limiting
        elapsed = time.time() - self._last_action_ts
        if elapsed < self._min_delay:
            await asyncio.sleep(self._min_delay - elapsed)
        self._last_action_ts = time.time()

        before_hash: Optional[str] = None
        after_hash: Optional[str] = None
        if action.verify:
            before_hash = await screenshot_hash(self._page)

        t0 = time.time()
        result = await self._dispatch(action)
        result.duration_ms = (time.time() - t0) * 1000
        result.before_hash = before_hash

        if action.verify and result.ok:
            after_hash = await screenshot_hash(self._page)
            result.after_hash = after_hash

        return result

    async def _dispatch(self, action: BrowserAction) -> ActionResult:
        p = self._page
        base = {"action": action.type, "selector": action.selector}

        try:
            if action.type == ActionType.NAVIGATE:
                await p.goto(action.value, timeout=action.timeout_ms, wait_until="domcontentloaded")
                return ActionResult(ok=True, **base)

            if action.type in (ActionType.CLICK, ActionType.HOVER, ActionType.TYPE,
                               ActionType.SELECT, ActionType.EXTRACT):
                if action.selector:
                    box = await resolve_selector(p, action.selector)
                    if box is None:
                        return ActionResult(ok=False, error="element_not_found", **base)

            if action.type == ActionType.CLICK:
                await p.click(action.selector, timeout=action.timeout_ms)
                return ActionResult(ok=True, **base)

            if action.type == ActionType.HOVER:
                await p.hover(action.selector, timeout=action.timeout_ms)
                return ActionResult(ok=True, **base)

            if action.type == ActionType.TYPE:
                await p.fill(action.selector, action.value or "", timeout=action.timeout_ms)
                return ActionResult(ok=True, **base)

            if action.type == ActionType.SELECT:
                await p.select_option(action.selector, action.value, timeout=action.timeout_ms)
                return ActionResult(ok=True, **base)

            if action.type == ActionType.EXTRACT:
                text = await p.inner_text(action.selector, timeout=action.timeout_ms)
                return ActionResult(ok=True, value_extracted=text, **base)

            if action.type == ActionType.SCREENSHOT:
                buf = await p.screenshot(type="png")
                import base64
                return ActionResult(ok=True, value_extracted=base64.b64encode(buf).decode(), **base)

            if action.type == ActionType.WAIT:
                ms = int(action.value or "1000")
                await asyncio.sleep(ms / 1000)
                return ActionResult(ok=True, **base)

            if action.type == ActionType.SCROLL:
                await p.evaluate(f"window.scrollBy(0, {int(action.value or '300')})")
                return ActionResult(ok=True, **base)

            if action.type == ActionType.KEY:
                await p.keyboard.press(action.value or "Enter")
                return ActionResult(ok=True, **base)

            if action.type == ActionType.EVALUATE:
                val = await p.evaluate(action.value or "null")
                return ActionResult(ok=True, value_extracted=val, **base)

            if action.type == ActionType.OCR:
                buf = await p.screenshot(type="png")
                from .ocr_engine import extract_text
                ocr = await extract_text(buf)
                return ActionResult(ok=True, value_extracted=ocr, **base)

            return ActionResult(ok=False, error=f"unknown_action:{action.type}", **base)

        except Exception as e:
            return ActionResult(ok=False, error=str(e), **base)

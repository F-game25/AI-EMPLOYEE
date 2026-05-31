"""Visual grounding — locate elements via DOM before acting."""
from __future__ import annotations
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PLAYWRIGHT_OK = False
try:
    from playwright.async_api import Page  # noqa: F401
    _PLAYWRIGHT_OK = True
except ImportError:
    pass


async def resolve_selector(page: Any, selector: str) -> Optional[dict]:
    """Return element bounding box dict or None if not found."""
    if not _PLAYWRIGHT_OK or page is None:
        return None
    try:
        el = await page.query_selector(selector)
        if el is None:
            return None
        box = await el.bounding_box()
        return box  # {x, y, width, height} or None if not visible
    except Exception as e:
        logger.debug("resolve_selector(%s): %s", selector, e)
        return None


async def find_text_element(page: Any, text: str) -> Optional[dict]:
    """Find element containing exact text, return bounding box."""
    if not _PLAYWRIGHT_OK or page is None:
        return None
    try:
        el = await page.get_by_text(text, exact=True).first.element_handle()
        if el:
            return await el.bounding_box()
        return None
    except Exception as e:
        logger.debug("find_text_element(%s): %s", text, e)
        return None


async def screenshot_hash(page: Any) -> Optional[str]:
    """Return MD5 of current viewport screenshot for diff verification."""
    if not _PLAYWRIGHT_OK or page is None:
        return None
    try:
        import hashlib
        buf = await page.screenshot(type="png")
        return hashlib.md5(buf).hexdigest()
    except Exception:
        return None

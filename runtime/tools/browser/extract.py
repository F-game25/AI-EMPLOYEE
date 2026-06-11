"""Bounded content extraction from a browser session (output ≤ 20KB)."""
from __future__ import annotations

from typing import Any, Optional

from tools.browser.action_executor import resolve_selector

MAX_OUTPUT_CHARS = 20_000

KINDS = {"text", "html", "value", "title", "url"}  # plus attr:<name>


def extract(session, kind: str, ref_or_selector: Optional[str] = None) -> dict[str, Any]:
    """Extract content → {ok, kind, target, data, truncated}.

    kind ∈ text | html | value | title | url | attr:<name>. ``value`` and
    ``attr:`` require a target; text/html default to the whole page.
    """
    kind = (kind or "text").strip().lower()
    attr_name = kind[5:] if kind.startswith("attr:") else None
    if kind not in KINDS and attr_name is None:
        return {"ok": False, "kind": kind, "target": ref_or_selector,
                "data": "", "truncated": False,
                "detail": f"unsupported kind (one of {sorted(KINDS)} or attr:<name>)"}
    if (kind == "value" or attr_name is not None) and not ref_or_selector:
        return {"ok": False, "kind": kind, "target": ref_or_selector,
                "data": "", "truncated": False,
                "detail": "this kind requires a ref (@eN) or CSS selector"}
    sel = resolve_selector(ref_or_selector)

    def job() -> Any:
        page = session.page
        if kind == "title":
            return page.title()
        if kind == "url":
            return page.url
        loc = page.locator(sel).first if sel else None
        if attr_name is not None:
            return loc.get_attribute(attr_name)
        if kind == "text":
            return loc.inner_text() if loc else page.inner_text("body")
        if kind == "html":
            return loc.inner_html() if loc else page.content()
        return loc.input_value()  # value

    try:
        raw = session.call(job)
    except Exception as exc:
        return {"ok": False, "kind": kind, "target": ref_or_selector,
                "data": "", "truncated": False, "detail": str(exc)}
    text = "" if raw is None else str(raw)
    truncated = len(text) > MAX_OUTPUT_CHARS
    return {"ok": True, "kind": kind, "target": ref_or_selector,
            "data": text[:MAX_OUTPUT_CHARS], "truncated": truncated}

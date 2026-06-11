"""Action executor — click/fill/type/press/scroll/select on refs or selectors.

``@eN`` resolves to ``[data-ai-ref="eN"]``: the persisted DOM attribute is the
source of truth (no cached ref table to drift out of sync). Anything else is
treated as a CSS selector.

Every result carries ``side_effect_class`` so the capability layer can gate:
  - 'submit'     — click on type=submit / a button inside a form / Enter in a textbox
  - 'input'      — fill/type/select/press (local state change)
  - 'navigation' — plain click / scroll
"""
from __future__ import annotations

import re
from typing import Any, Optional

ACTIONS = {"click", "fill", "type", "press", "scroll", "select"}

_REF_RE = re.compile(r"^@?(e\d+)$")
_DEFAULT_TIMEOUT_MS = 10_000

_IS_SUBMITISH_JS = (
    "el => ((el.getAttribute('type') || '').toLowerCase() === 'submit')"
    " || (el.tagName === 'BUTTON' && !!el.closest('form'))"
    " || (el.tagName === 'INPUT' && (el.type || '').toLowerCase() === 'submit')"
)
_IS_TEXTBOX_JS = (
    "el => el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'"
    " || el.isContentEditable || (el.getAttribute('role') || '') === 'textbox'"
)


def resolve_selector(ref_or_selector: Optional[str]) -> Optional[str]:
    """``@eN``/``eN`` → ``[data-ai-ref="eN"]``; otherwise pass through as CSS."""
    if not ref_or_selector:
        return None
    m = _REF_RE.match(ref_or_selector.strip())
    return f'[data-ai-ref="{m.group(1)}"]' if m else ref_or_selector


def act(session, action: str, ref_or_selector: Optional[str] = None,
        value: Any = None, timeout_ms: int = _DEFAULT_TIMEOUT_MS) -> dict[str, Any]:
    """Perform ``action`` → {ok, action, target, detail, side_effect_class}.

    Approval is a capability-layer concern — this executor only acts and
    honestly classifies the side effect.
    """
    action = (action or "").strip().lower()
    target = ref_or_selector
    if action not in ACTIONS:
        return {"ok": False, "action": action, "target": target,
                "detail": f"unsupported action (one of {sorted(ACTIONS)})",
                "side_effect_class": "input"}
    sel = resolve_selector(ref_or_selector)
    if action in ("click", "fill", "type", "select") and not sel:
        return {"ok": False, "action": action, "target": target,
                "detail": "a ref (@eN) or CSS selector is required",
                "side_effect_class": "input"}

    def job() -> tuple[str, str]:
        page = session.page
        if action == "click":
            loc = page.locator(sel).first
            try:
                submitish = bool(loc.evaluate(_IS_SUBMITISH_JS))
            except Exception:
                submitish = False
            loc.click(timeout=timeout_ms)
            return ("submit" if submitish else "navigation"), f"clicked {sel}"

        if action == "fill":
            page.locator(sel).first.fill("" if value is None else str(value),
                                         timeout=timeout_ms)
            return "input", f"filled {sel}"

        if action == "type":
            loc = page.locator(sel).first
            text = "" if value is None else str(value)
            typer = getattr(loc, "press_sequentially", None) or loc.type
            typer(text, timeout=timeout_ms)
            return "input", f"typed {len(text)} chars into {sel}"

        if action == "press":
            key = str(value or "Enter")
            if sel:
                loc = page.locator(sel).first
                try:
                    textbox = bool(loc.evaluate(_IS_TEXTBOX_JS))
                except Exception:
                    textbox = False
                loc.press(key, timeout=timeout_ms)
                cls = "submit" if (key == "Enter" and textbox) else "input"
                return cls, f"pressed {key} on {sel}"
            page.keyboard.press(key)
            return "input", f"pressed {key}"

        if action == "scroll":
            if isinstance(value, (int, float)):
                dy = int(value)
            else:
                dy = {"up": -600, "down": 600, "top": -10**7,
                      "bottom": 10**7}.get(str(value or "down").lower(), 600)
            if sel:
                page.locator(sel).first.evaluate("(el, dy) => el.scrollBy(0, dy)", dy)
            else:
                page.evaluate("dy => window.scrollBy(0, dy)", dy)
            return "navigation", f"scrolled {dy}px"

        # select
        loc = page.locator(sel).first
        values = [str(v) for v in value] if isinstance(value, (list, tuple)) \
            else [str(value)]
        loc.select_option(values, timeout=timeout_ms)
        return "input", f"selected {values} in {sel}"

    try:
        side_effect_class, detail = session.call(job)
    except Exception as exc:
        return {"ok": False, "action": action, "target": target,
                "detail": str(exc), "side_effect_class": "input"}
    return {"ok": True, "action": action, "target": target,
            "detail": detail, "side_effect_class": side_effect_class}

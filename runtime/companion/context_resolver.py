"""Context resolver for the Companion Gateway.

Resolves vague / deictic references ("fix it", "summarize this", "continue",
"that one", "the error") against the *live UI context* the frontend sends —
not hardcoded string matching against a corpus. This is what makes the avatar
feel context-aware: "fix it" means the failing task you're looking at right now.

Hot-path rule: pure-Python, deterministic, no LLM. Cheap enough to run on every
message.

Context dict shape (sent by the frontend)::

    {
      "current_page":    str,
      "selected_item":   dict | None,
      "recent_events":   list[dict],   # newest-last; events may carry type/level
      "active_task":     dict | None,
      "recent_messages": list[dict],
    }

Salience order when binding a vague reference::

    selected_item  >  active_task  >  most-recent error event  >  current_page

Anti-fabrication: a referent is only ever bound to something actually present
in the context. If nothing salient exists, the text is returned unchanged with
low confidence and no referents.

Public surface::

    from companion.context_resolver import get_context_resolver
    out = get_context_resolver().resolve("fix it", context)
    # -> {resolved_text, referents, focus, confidence}
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Deictic / vague reference triggers. Presence of any of these means the message
# leans on context to be actionable.
_DEICTIC = (
    "fix it", "fix this", "fix that", "do it", "do this", "do that",
    "summarize this", "summarise this", "summarize it", "summarise it",
    "explain this", "explain it", "explain that",
    "continue", "keep going", "carry on", "resume", "again", "retry",
    "redo it", "try again", "this one", "that one", "the error", "the failure",
    "the issue", "the problem", "the task", "this page", "here", "above",
    "the last one", "the previous", "what happened",
)
# Standalone pronouns / pointers (word-boundary matched).
_PRONOUNS = ("it", "this", "that", "these", "those", "them", "one")

_ERROR_LEVELS = {"error", "err", "critical", "fatal", "failed", "failure"}
_FAIL_STATUSES = {"failed", "failing", "error", "errored", "crashed",
                  "blocked", "stuck"}

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip())


def _has_pronoun(low: str) -> bool:
    return any(re.search(rf"\b{p}\b", low) for p in _PRONOUNS)


def _is_deictic(low: str) -> bool:
    if any(phrase in low for phrase in _DEICTIC):
        return True
    # A short message that is essentially just a verb + pronoun ("fix it",
    # "rerun that") also counts.
    return len(low.split()) <= 4 and _has_pronoun(low)


def _label(obj: dict, fallback: str) -> str:
    """Human-ish label for a context object, preferring descriptive keys."""
    for k in ("title", "name", "label", "summary", "description",
              "goal", "task", "message", "id"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback


def _looks_failing(obj: dict) -> bool:
    status = str(obj.get("status", "")).lower()
    if status in _FAIL_STATUSES:
        return True
    level = str(obj.get("level", "")).lower()
    if level in _ERROR_LEVELS:
        return True
    return bool(obj.get("error"))


def _newest_error_event(events: list) -> Optional[dict]:
    """Most-recent event (events are newest-last) that looks like an error."""
    if not events:
        return None
    for ev in reversed(events):
        if not isinstance(ev, dict):
            continue
        etype = str(ev.get("type", "")).lower()
        level = str(ev.get("level", "")).lower()
        status = str(ev.get("status", "")).lower()
        if (level in _ERROR_LEVELS or status in _FAIL_STATUSES
                or "error" in etype or "fail" in etype or ev.get("error")):
            return ev
    return None


class ContextResolver:
    """Binds vague references to the most salient live-context element."""

    def resolve(self, text: str, context: Optional[dict] = None) -> dict:
        raw = _norm(text)
        ctx = context or {}
        low = raw.lower()

        if not raw:
            return self._out(raw, [], None, 0.1)

        deictic = _is_deictic(low)
        focus, referents, salience = self._collect(ctx, deictic)

        # Nothing to bind to → never fabricate. Return text unchanged.
        if focus is None:
            # If the message clearly needed context but none exists, flag it
            # via low confidence; otherwise it's just a self-contained message.
            conf = 0.2 if deictic else 0.5
            return self._out(raw, [], None, conf)

        # Confidence: strong when the message is vague AND we found a salient
        # target; moderate when the message was already specific but we still
        # have useful focus to attach.
        confidence = round(min(0.97, salience + (0.25 if deictic else 0.0)), 3)

        resolved_text = self._compose(raw, focus, deictic)
        return self._out(resolved_text, referents, focus, confidence)

    # ── Gather candidate referents in salience order ───────────────────────────
    def _collect(self, ctx: dict, deictic: bool):
        referents: list = []
        focus: Optional[dict] = None
        salience = 0.0

        sel = ctx.get("selected_item")
        active = ctx.get("active_task")
        events = ctx.get("recent_events") or []
        page = ctx.get("current_page")

        # 1) selected_item — user is literally pointing at it. Highest priority.
        if isinstance(sel, dict) and sel:
            ref = self._ref("selected_item", sel, _label(sel, "the selected item"))
            referents.append(ref)
            focus, salience = ref, 0.7

        # 2) active_task — what the system is currently working on.
        if isinstance(active, dict) and active:
            failing = _looks_failing(active)
            ref = self._ref("active_task", active,
                            _label(active, "the active task"),
                            failing=failing)
            referents.append(ref)
            if focus is None:
                focus = ref
                salience = 0.72 if failing else 0.6

        # 3) most-recent error event.
        err = _newest_error_event(events)
        if err is not None:
            ref = self._ref("recent_event", err,
                            _label(err, "the recent error"), failing=True)
            referents.append(ref)
            if focus is None:
                focus, salience = ref, 0.62

        # 4) current_page — weakest anchor, only when nothing better exists.
        if focus is None and isinstance(page, str) and page.strip():
            ref = self._ref("current_page", {"page": page}, page.strip())
            referents.append(ref)
            focus, salience = ref, 0.45

        # If the message wasn't deictic and we only have a page, don't force a
        # binding — keep referents for transparency but treat focus as soft.
        if not deictic and focus is not None and focus["source"] == "current_page":
            salience = min(salience, 0.4)

        return focus, referents, salience

    @staticmethod
    def _ref(source: str, obj: dict, label: str, failing: bool = False) -> dict:
        return {
            "source": source,
            "label": label,
            "failing": bool(failing),
            "object": obj,
        }

    @staticmethod
    def _compose(text: str, focus: dict, deictic: bool) -> str:
        """Append a short, factual resolved-context preamble. Never invents."""
        label = focus["label"]
        src = focus["source"]
        if src == "selected_item":
            tgt = f"the selected item ({label})"
        elif src == "active_task":
            tgt = (f"the failing active task ({label})" if focus["failing"]
                   else f"the active task ({label})")
        elif src == "recent_event":
            tgt = f"the recent error ({label})"
        else:  # current_page
            tgt = f"the current page ({label})"

        suffix = f" [resolved target: {tgt}]"
        return text + suffix

    @staticmethod
    def _out(resolved_text: str, referents: list, focus: Optional[dict],
             confidence: float) -> dict:
        return {
            "resolved_text": resolved_text,
            "referents": referents,
            "focus": focus,
            "confidence": round(float(confidence), 3),
        }


_SINGLETON: Optional[ContextResolver] = None


def get_context_resolver() -> ContextResolver:
    """Return the process-wide ContextResolver singleton."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = ContextResolver()
    return _SINGLETON

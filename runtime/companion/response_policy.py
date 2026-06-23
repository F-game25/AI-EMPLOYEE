"""Response policy engine for the Companion Gateway — answer discipline.

A real teammate matches the *shape* of the answer to the question: a simple
operational value gets one short sentence (no tutorial, no menu of options); a
direct action is confirmed → executed → summarized; a complex planning request
is allowed structure; an error gets a short line plus the next best action.

This module derives a ``ResponsePolicy`` from the generic intent fields the
classifier returns (``mode``, ``task_type``, ``is_command``, ``confidence``) —
keyed off generic fields only so it keeps working as new intents are added by
the intent-classifier owner. It carries NO LLM call: it both (a) shapes the
system prompt the runtime sends, and (b) post-shapes the reply to enforce the
sentence budget when the model over-answers.

Public surface
--------------
    from companion.response_policy import policy_for, ResponsePolicy
    policy = policy_for(intent, user_requested_detail=False)
    system_hint = policy.system_prompt_hint()
    reply = policy.shape(reply)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

# Reply styles.
STYLE_VALUE = "value"          # one short factual answer
STYLE_CONFIRM_ACT = "confirm_act"  # confirm + execute + summarize
STYLE_STRUCTURED = "structured"    # numbered/sectioned, multi-step OK
STYLE_ERROR = "error"          # short line + next action
STYLE_CONVERSATIONAL = "conversational"  # default chit-chat, brief

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# A modest cap so "no max" still bounds run-on replies in practice.
_UNBOUNDED = 999

# When the user explicitly wants depth, these words appear. Used to relax the
# policy on demand ("explain in detail", "give me the steps", "full breakdown").
_DETAIL_REQUEST = re.compile(
    r"\b(in detail|step[- ]?by[- ]?step|walk me through|explain (?:how|why|the)|"
    r"full (?:breakdown|explanation|details?)|elaborate|give me (?:the )?steps|"
    r"tutorial|uitleg|leg uit|in detail|stap voor stap|alle stappen|"
    r"give me options|what are my options|show me options|welke opties)\b",
    re.IGNORECASE)


@dataclass
class ResponsePolicy:
    """Length/style contract for a single reply."""

    style: str
    max_sentences: int
    allow_options: bool
    allow_tutorial: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "max_sentences": self.max_sentences,
            "allow_options": self.allow_options,
            "allow_tutorial": self.allow_tutorial,
        }

    # ── Prompt shaping ────────────────────────────────────────────────────────

    def system_prompt_hint(self) -> str:
        """A directive appended to the system prompt to bias the model up front.

        Cheaper and higher-quality than truncating after the fact — the model
        is told the budget before it writes.
        """
        parts: list[str] = []
        if self.max_sentences < _UNBOUNDED:
            n = self.max_sentences
            parts.append(
                f"Answer in at most {n} sentence{'s' if n != 1 else ''}.")
        if self.style == STYLE_VALUE:
            parts.append("Give the direct answer only — no preamble, no caveats.")
        elif self.style == STYLE_CONFIRM_ACT:
            parts.append("State what you did and the result. Do not explain how "
                         "to do it manually.")
        elif self.style == STYLE_STRUCTURED:
            parts.append("A short numbered structure is fine when it genuinely "
                         "helps; stay concise.")
        elif self.style == STYLE_ERROR:
            parts.append("State the problem briefly, then the single best next "
                         "action.")
        if not self.allow_tutorial:
            parts.append("Never explain how the user could do this manually when "
                         "the system can do it — do it, or say you can.")
        if not self.allow_options:
            parts.append("Do not offer a menu of options unless explicitly asked.")
        return " ".join(parts)

    # ── Reply shaping (enforcement when the model over-answers) ───────────────

    def shape(self, reply: str) -> str:
        """Trim a reply to the sentence budget. Code blocks are left intact.

        Only trims when the policy is genuinely short (value/error). Structured
        and confirm-act replies are left as-is beyond a generous safety cap so we
        never amputate a legitimately useful multi-step answer.
        """
        text = str(reply or "").strip()
        if not text:
            return text
        if self.max_sentences >= _UNBOUNDED:
            return text
        # Don't slice through fenced code — those carry real payload.
        if "```" in text:
            return text
        sentences = _SENTENCE_SPLIT.split(text)
        if len(sentences) <= self.max_sentences:
            return text
        return " ".join(s.strip() for s in sentences[: self.max_sentences]).strip()


# ── Mode/task → policy mapping (keyed off generic intent fields) ──────────────

# Simple operational value lookups (time, hardware, cwd, status reads). These
# task_type hints come from the classifier/broker layer; matching is generic so
# new system-info task types fall through to the value policy by name convention.
_VALUE_TASK_HINTS = ("system", "system_info", "status", "lookup", "monitoring")


def _is_value_question(intent: dict) -> bool:
    """A short operational/value question → one-line answer."""
    mode = str(intent.get("mode", "")).lower()
    task = str(intent.get("task_type", "")).lower()
    if task.startswith("briefing"):
        return False
    if mode == "monitoring":
        return True
    if any(h in task for h in _VALUE_TASK_HINTS):
        return True
    return False


def policy_for(intent: Optional[dict], *,
               user_text: str = "",
               user_requested_detail: Optional[bool] = None,
               error: bool = False) -> ResponsePolicy:
    """Derive a :class:`ResponsePolicy` from generic intent fields.

    ``user_requested_detail`` overrides the default brevity when the user asked
    for depth/options/a tutorial (auto-detected from ``user_text`` when not
    passed explicitly).
    """
    intent = intent or {}
    if user_requested_detail is None:
        user_requested_detail = bool(_DETAIL_REQUEST.search(user_text or ""))

    if error:
        return ResponsePolicy(STYLE_ERROR, max_sentences=2,
                              allow_options=False, allow_tutorial=False)

    mode = str(intent.get("mode", "")).lower()
    task = str(intent.get("task_type", "")).lower()
    is_command = bool(intent.get("is_command"))

    # Direct action → confirm + execute + summarize (no manual tutorial).
    if is_command or mode in ("execution", "debugging"):
        return ResponsePolicy(STYLE_CONFIRM_ACT, max_sentences=3,
                              allow_options=False,
                              allow_tutorial=user_requested_detail)

    # A morning brief is a compact structured conversation starter, not a single
    # scalar status value.
    if task.startswith("briefing"):
        return ResponsePolicy(STYLE_STRUCTURED, max_sentences=_UNBOUNDED,
                              allow_options=False, allow_tutorial=False)

    # Simple operational/value question → one short answer.
    if _is_value_question(intent):
        return ResponsePolicy(STYLE_VALUE, max_sentences=2,
                              allow_options=user_requested_detail,
                              allow_tutorial=user_requested_detail)

    # Complex planning → structured allowed.
    if mode == "planning":
        return ResponsePolicy(STYLE_STRUCTURED, max_sentences=_UNBOUNDED,
                              allow_options=True, allow_tutorial=True)

    # Analysis → moderately long, structure allowed, but no unsolicited options.
    if mode == "analysis":
        return ResponsePolicy(STYLE_STRUCTURED, max_sentences=_UNBOUNDED,
                              allow_options=user_requested_detail,
                              allow_tutorial=user_requested_detail)

    # Default conversation → brief, no menus/tutorials unless asked.
    max_s = _UNBOUNDED if user_requested_detail else 4
    return ResponsePolicy(STYLE_CONVERSATIONAL, max_sentences=max_s,
                          allow_options=user_requested_detail,
                          allow_tutorial=user_requested_detail)

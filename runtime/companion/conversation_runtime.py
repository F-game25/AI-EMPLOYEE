"""Conversation runtime — the Companion Gateway orchestrator.

This is the single entry point a turn flows through. It wires the foundation
modules into one pipeline and produces a typed ``CompanionResponse``:

    resolve context → classify intent → pick model target → act-by-mode →
    build response (with avatar state + meta).

It is a ROUTING + PLANNING layer. It never calls subsystems directly — the
``ExecutionBroker`` does that, and only for safety-gate-cleared capabilities.
``engine.api.generate`` is synchronous, so ``handle`` is synchronous too.

Paid-target gating
------------------
Model selection always defaults to the FREE local model (``prefer='local'``).
A paid target (external API / rented GPU) is only chosen when the caller passes
``context.allow_paid=True`` AND ``context.prefer_target`` — and even then it
comes back ``requires_approval=True`` and is surfaced in ``approvals_required``,
never auto-run. ``resolve_target`` enforces this; the runtime honours it.

Failure invariant
----------------
``handle`` / ``handle_message`` always return a valid response. Any internal
failure yields ``ok=False`` with a safe error reply and ``avatar_state=error``
— it never throws to the caller (the Node worker).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Optional

from companion.schemas import CompanionRequest, CompanionResponse
from companion.context_resolver import get_context_resolver
from companion.intent_classifier import get_intent_classifier
from companion.execution_broker import get_execution_broker
from companion.avatar_state_engine import get_avatar_state_engine
from companion.critique_engine import (
    get_critique_engine,
    STANCE_PROCEED,
    STANCE_NEED_INFO,
    STANCE_AGAINST,
)

from core.model_lanes import (
    tier_for_task,
    resolve_target,
    TARGET_LOCAL,
)

logger = logging.getLogger("companion.conversation_runtime")

_VALID_PAID_TARGETS = {"external_api", "rented_remote"}

# Modes worth a critique pass. Plain conversation/monitoring/approval are NOT
# critiqued — challenging chit-chat is noise, the opposite failure mode.
_CRITIQUE_MODES = frozenset({"execution", "planning", "debugging"})
# A command classified with low confidence also gets a critique pass.
_LOW_CONFIDENCE_THRESHOLD = 0.55


def _critique_enabled() -> bool:
    """Master critique switch (default ON; ``COMPANION_CRITIQUE=0`` disables)."""
    return os.getenv("COMPANION_CRITIQUE", "1").strip() != "0"


class ConversationRuntime:
    """Orchestrates a single companion turn end-to-end."""

    def __init__(self) -> None:
        self._resolver = get_context_resolver()
        self._classifier = get_intent_classifier()
        self._broker = get_execution_broker()
        self._avatar = get_avatar_state_engine()
        self._critic = get_critique_engine()

    def handle(self, request: CompanionRequest) -> CompanionResponse:
        """Run a turn. Never raises — failures become ok=False responses."""
        t0 = time.time()
        try:
            return self._handle_inner(request, t0)
        except Exception as exc:  # noqa: BLE001 — total failure → safe response
            logger.exception("conversation runtime failed: %s", exc)
            return CompanionResponse(
                ok=False,
                mode="conversation",
                reply="I hit an internal error handling that. Nothing was executed.",
                avatar_state=self._avatar.state_for("conversation", "error"),
                meta={"error": str(exc),
                      "latency_ms": int((time.time() - t0) * 1000)},
            )

    # ── Pipeline ─────────────────────────────────────────────────────────────────

    def _handle_inner(self, request: CompanionRequest, t0: float) -> CompanionResponse:
        ctx = dict(request.context or {})
        ctx.setdefault("text", request.text)

        # 1) Resolve vague references against live UI context.
        resolved = self._resolver.resolve(request.text, ctx)
        resolved_text = resolved.get("resolved_text") or request.text

        # 2) Classify into a conversation mode.
        intent = self._classifier.classify(resolved_text, ctx)
        mode = intent.get("mode", "conversation")

        # 3) Pick a model target. Default = free local. Paid only on explicit
        #    opt-in, and even then it comes back requiring approval.
        model_info = self._select_target(intent, ctx)

        # 3.5) Teammate critique — CHALLENGE consequential requests before acting.
        #      Advisory only (separate from the safety/approval gate). On a
        #      'need_info' stance we ask instead of executing.
        critique = self._maybe_critique(resolved_text, intent, ctx)
        if critique is not None and critique.get("stance") == STANCE_NEED_INFO:
            return self._clarification_response(
                mode, critique, model_info, intent, resolved, request, t0)

        # 4) Act by mode.
        reply = ""
        actions: list[dict[str, Any]] = []
        approvals: list[dict[str, Any]] = []
        phase = "done"

        if mode in ("conversation", "analysis"):
            reply = self._generate_reply(resolved_text, ctx, model_info, mode)
            phase = "generating"
        elif mode == "planning":
            reply = self._generate_plan(resolved_text, ctx, model_info)
            phase = "planning"
        elif mode in ("execution", "debugging"):
            out = self._broker.execute(intent, resolved, ctx)
            actions = out["results"]
            approvals = out["approvals_required"]
            reply = self._summarize_execution(out, intent)
            phase = "awaiting_approval" if approvals else (
                "executing" if out["executed"] else "generating")
        elif mode == "monitoring":
            out = self._broker.execute(intent, resolved, ctx,
                                       only_subsystems={"system"})
            actions = out["results"]
            approvals = out["approvals_required"]
            reply = self._summarize_monitoring(out)
            phase = "monitoring"
        elif mode == "approval":
            reply = ("Acknowledged. Approvals are confirmed or rejected from the "
                     "approval queue — routing this to the HITL flow.")
            phase = "awaiting_approval"
        else:  # learning + any unmapped mode → conversational reply
            reply = self._generate_reply(resolved_text, ctx, model_info, mode)
            phase = "learning" if mode == "learning" else "generating"

        # A pending paid upgrade always surfaces as an approval too.
        if model_info.get("requires_approval"):
            approvals.append(self._paid_upgrade_approval(model_info, intent))
            if phase not in ("error",):
                phase = "awaiting_approval"

        # Fold critique push-back into the spoken reply (when it has concerns).
        if critique is not None and critique.get("stance") != STANCE_PROCEED:
            reply = self._prepend_critique(reply, critique)
            if critique.get("stance") == STANCE_AGAINST:
                approvals.append(self._critique_recommendation(critique))
                if phase not in ("error",):
                    phase = "awaiting_approval"

        avatar_state = self._avatar.state_for(mode, phase)

        meta: dict[str, Any] = {
                "intent": intent,
                "resolution_confidence": resolved.get("confidence"),
                "focus": resolved.get("focus"),
                "model": {
                    "tier": model_info.get("tier"),
                    "target": model_info.get("target"),
                    "provider": model_info.get("provider"),
                    "model": model_info.get("model"),
                    "requires_approval": model_info.get("requires_approval"),
                    "requires_payment": model_info.get("requires_payment"),
                    "rationale": model_info.get("rationale"),
                },
                "channel": request.channel,
                "session_id": request.session_id,
                "tenant_id": request.tenant_id,
                "latency_ms": int((time.time() - t0) * 1000),
        }
        if critique is not None:
            meta["critique"] = critique

        # Voice channel: also carry a short, spoken-friendly summary. The full
        # `reply` still goes to chat/action panel; TTS speaks `voice_summary`.
        if (request.channel or "").lower() == "voice":
            meta["voice_summary"] = self._voice_summary(reply)

        return CompanionResponse(
            ok=True,
            mode=mode,
            reply=reply,
            actions=actions,
            approvals_required=approvals,
            avatar_state=avatar_state,
            meta=meta,
        )

    # ── Model selection ──────────────────────────────────────────────────────────

    def _select_target(self, intent: dict, ctx: dict) -> dict:
        tier = tier_for_task(intent.get("task_type"))
        allow_paid = bool(ctx.get("allow_paid", False))
        prefer = ctx.get("prefer_target") or TARGET_LOCAL
        if prefer not in _VALID_PAID_TARGETS:
            prefer = TARGET_LOCAL
        target = resolve_target(tier, prefer=prefer, allow_paid=allow_paid)
        target["tier"] = tier
        return target

    # ── Teammate critique (advisory — NOT the safety/approval gate) ─────────────

    def _maybe_critique(self, goal: str, intent: dict, ctx: dict) -> Optional[dict]:
        """Run the critique once per turn for consequential / low-confidence
        commands. Returns None when critique is disabled or not warranted."""
        if not _critique_enabled():
            return None
        mode = intent.get("mode", "")
        low_conf_cmd = bool(intent.get("is_command")) and (
            float(intent.get("confidence", 1.0) or 0.0) < _LOW_CONFIDENCE_THRESHOLD)
        if mode not in _CRITIQUE_MODES and not low_conf_cmd:
            return None
        return self._critic.critique(goal, intent, ctx)

    def _clarification_response(self, mode: str, critique: dict,
                                model_info: dict, intent: dict,
                                resolved: dict, request: CompanionRequest,
                                t0: float) -> CompanionResponse:
        """A 'need_info' turn: ask the clarifying question, run NOTHING."""
        question = (critique.get("clarifying_question")
                    or "Could you clarify the exact outcome and scope you want?")
        reply = question
        avatar_state = self._avatar.state_for(mode, "awaiting_approval")
        meta: dict[str, Any] = {
            "intent": intent,
            "resolution_confidence": resolved.get("confidence"),
            "focus": resolved.get("focus"),
            "model": {
                "tier": model_info.get("tier"),
                "target": model_info.get("target"),
                "provider": model_info.get("provider"),
                "model": model_info.get("model"),
            },
            "critique": critique,
            "awaiting_clarification": True,
            "channel": request.channel,
            "session_id": request.session_id,
            "tenant_id": request.tenant_id,
            "latency_ms": int((time.time() - t0) * 1000),
        }
        if (request.channel or "").lower() == "voice":
            meta["voice_summary"] = self._voice_summary(reply)
        return CompanionResponse(
            ok=True, mode=mode, reply=reply, actions=[], approvals_required=[],
            avatar_state=avatar_state, meta=meta,
        )

    @staticmethod
    def _prepend_critique(reply: str, critique: dict) -> str:
        """Lead the reply with a short, spoken-friendly push-back."""
        pushback = critique.get("pushback")
        alternative = critique.get("alternative")
        lead_parts: list[str] = []
        if critique.get("stance") == STANCE_AGAINST:
            lead_parts.append("I'd recommend against this as-is.")
        else:
            lead_parts.append("Before I do this — one concern:")
        if pushback:
            lead_parts.append(pushback)
        if alternative:
            lead_parts.append(f"Better path: {alternative}")
        lead_parts.append("Want me to proceed anyway?")
        lead = " ".join(p.rstrip() for p in lead_parts if p)
        return f"{lead}\n\n{reply}".strip() if reply else lead

    @staticmethod
    def _critique_recommendation(critique: dict) -> dict:
        """Surface a 'recommend_against' stance with approval-card visibility so
        the runtime never silently complies — the user can still override."""
        return {
            "cap": "companion.critique_override",
            "action": "Proceed despite teammate recommendation",
            "summary": critique.get("pushback")
                       or "The teammate recommends against this request as-is.",
            "why": "; ".join(critique.get("risks") or []) or "advisory push-back",
            "risk": "advisory",
            "affects": "the requested action",
            "side_effects": list(critique.get("risks") or []),
            "rollback": critique.get("alternative"),
            "needs_explicit_confirm": True,
            "advisory": True,
        }

    # ── LLM-backed steps (degrade to canned text when LLM unavailable) ──────────

    def _generate_reply(self, text: str, ctx: dict, model_info: dict, mode: str) -> str:
        system = ("You are the companion assistant for an AI operating system. "
                  "Be concise, factual, and never claim to have taken actions you "
                  "did not take.")
        prompt = text
        page = ctx.get("current_page")
        if page:
            prompt = f"[context: user is on the '{page}' page]\n{text}"
        return self._llm(prompt, system, model_info,
                         fallback=self._canned_reply(text, mode))

    def _generate_plan(self, text: str, ctx: dict, model_info: dict) -> str:
        system = ("You are a planning assistant. Produce a short, numbered, "
                  "actionable plan. Do NOT execute anything. 3-7 steps max.")
        return self._llm(text, system, model_info,
                         fallback=("Plan (LLM offline — outline only):\n"
                                   "1. Clarify the goal and constraints.\n"
                                   "2. Identify the subsystems involved.\n"
                                   "3. Sequence the steps, gating risky ones for approval.\n"
                                   "4. Define how to verify success."))

    def _llm(self, prompt: str, system: str, model_info: dict, fallback: str) -> str:
        """Call the engine LLM with the resolved LOCAL model. Degrade on failure.

        Paid targets are never invoked here — they require approval first, so we
        always generate with the free local model in the same turn.
        """
        try:
            from engine.api import generate
        except Exception as exc:  # engine import unavailable → canned reply
            logger.debug("engine.api unavailable: %s", exc)
            return fallback
        # Use the free local model even when a paid upgrade is pending approval.
        model = model_info.get("model") if model_info.get("target") == TARGET_LOCAL else None
        try:
            out = generate(prompt=prompt, system=system, model=model, timeout=60)
            text = (out or "").strip()
            return text or fallback
        except Exception as exc:  # noqa: BLE001 — LLM down → safe canned reply
            logger.debug("LLM generate failed, degrading: %s", exc)
            return fallback

    @staticmethod
    def _canned_reply(text: str, mode: str) -> str:
        snippet = (text or "").strip()
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        return (f"(LLM offline) I understood this as a {mode} request: "
                f"\"{snippet}\". I can't generate a full reply right now, but "
                f"nothing was executed.")

    # ── Voice summary (cheap, no extra LLM call) ───────────────────────────────────

    # Spoken summaries stay short: roughly two sentences / this many chars.
    _VOICE_SUMMARY_MAX_CHARS = 280
    _SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

    @classmethod
    def _voice_summary(cls, reply: str) -> str:
        """A 1-2 sentence spoken-friendly synopsis of ``reply``.

        Pure truncation/first-sentences heuristic — never calls an LLM, so it
        adds no latency. Short replies are returned as-is. Code fences and list
        markup are stripped so TTS doesn't read syntax aloud.
        """
        text = (reply or "").strip()
        if not text:
            return ""
        # Drop fenced code blocks and inline markup that reads badly aloud.
        text = re.sub(r"```[\s\S]*?```", " (code is on screen) ", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"[*_#>]+", "", text)
        text = re.sub(r"^\s*[-+*]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= cls._VOICE_SUMMARY_MAX_CHARS:
            return text
        sentences = cls._SENTENCE_SPLIT.split(text)
        summary = ""
        for sent in sentences[:2]:
            candidate = (summary + " " + sent).strip() if summary else sent.strip()
            if summary and len(candidate) > cls._VOICE_SUMMARY_MAX_CHARS:
                break
            summary = candidate
        if not summary:
            summary = text[: cls._VOICE_SUMMARY_MAX_CHARS].rsplit(" ", 1)[0]
        if len(summary) < len(text):
            summary = summary.rstrip(".!? ") + ". The full details are in the chat."
        return summary

    # ── Result summarisers ───────────────────────────────────────────────────────

    @staticmethod
    def _summarize_execution(out: dict, intent: dict) -> str:
        ran = out.get("executed") or []
        appr = out.get("approvals_required") or []
        parts: list[str] = []
        if ran:
            parts.append(f"Ran: {', '.join(ran)}.")
        if appr:
            names = ", ".join(a.get("action", a.get("cap", "?")) for a in appr)
            parts.append(f"Awaiting your approval before running: {names}.")
        not_impl = [r["cap"] for r in out.get("results", [])
                    if r.get("status") == "not_implemented"]
        if not_impl:
            parts.append(f"Not yet wired (no fabricated result): {', '.join(not_impl)}.")
        if not parts:
            parts.append("No capability matched that request — nothing executed.")
        return " ".join(parts)

    @staticmethod
    def _summarize_monitoring(out: dict) -> str:
        results = out.get("results", [])
        ok = [r for r in results if r.get("status") == "ok"]
        if ok:
            ids = ", ".join(r["cap"] for r in ok)
            return f"Pulled live status from: {ids}. See actions for details."
        stubs = [r["cap"] for r in results if r.get("status") == "not_implemented"]
        if stubs:
            return ("Monitoring adapters for these aren't wired yet (no fabricated "
                    f"data): {', '.join(stubs)}.")
        return "Nothing to report from the monitoring read."

    @staticmethod
    def _paid_upgrade_approval(model_info: dict, intent: dict) -> dict:
        return {
            "cap": "model.paid_upgrade",
            "action": f"Use paid {model_info.get('target')} model",
            "summary": model_info.get("rationale", "paid model upgrade"),
            "why": "paid target requires explicit approval + payment",
            "risk": "L3",
            "affects": "LLM compute budget (billable)",
            "side_effects": ["incurs cost"],
            "rollback": "decline — falls back to the free local model",
            "needs_explicit_confirm": True,
            "target": model_info.get("target"),
            "provider": model_info.get("provider"),
            "model": model_info.get("model"),
            "requires_payment": model_info.get("requires_payment"),
        }


# ── Singleton + convenience entry point ──────────────────────────────────────────

_instance: Optional[ConversationRuntime] = None
_instance_lock = threading.Lock()


def get_conversation_runtime() -> ConversationRuntime:
    """Return the process-wide ``ConversationRuntime`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ConversationRuntime()
    return _instance


def handle_message(payload: dict) -> dict:
    """Convenience entry the Node worker calls (``companion.message``).

    Builds a ``CompanionRequest`` from a dict, runs the runtime, and returns
    ``response.to_dict()``. Never raises — bad input yields an ok=False dict.
    """
    try:
        request = CompanionRequest.from_dict(payload or {})
    except Exception as exc:  # noqa: BLE001 — malformed payload → safe response
        return CompanionResponse(
            ok=False,
            mode="conversation",
            reply="Malformed request payload.",
            avatar_state="error",
            meta={"error": str(exc)},
        ).to_dict()
    return get_conversation_runtime().handle(request).to_dict()

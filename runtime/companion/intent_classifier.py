"""Intent / conversation-mode classifier for the Companion Gateway.

Maps a raw user message to a conversation MODE so the companion knows whether
to chat, analyse, plan, execute, monitor, debug, learn, or process an approval.

Design — two-stage, hot-path-cheap:
  1. FAST heuristic pass (keyword / verb patterns). Deterministic, no I/O.
     Returns immediately for clear cases. This is the only path tests exercise.
  2. OPTIONAL LLM escalation (env ``COMPANION_LLM_INTENT=1``) used *only* when
     the heuristic is low-confidence. Goes through ``engine.api`` (never a raw
     provider) and degrades silently back to the heuristic on any failure.

Public surface::

    from companion.intent_classifier import get_intent_classifier
    out = get_intent_classifier().classify("fix the avatar lag")
    # -> {mode, task_type, confidence, is_command, reason}
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger("companion.intent_classifier")

# ── Mode taxonomy (exact strings — do not rename) ──────────────────────────────
MODE_CONVERSATION = "conversation"
MODE_ANALYSIS = "analysis"
MODE_PLANNING = "planning"
MODE_EXECUTION = "execution"
MODE_MONITORING = "monitoring"
MODE_DEBUGGING = "debugging"
MODE_LEARNING = "learning"
MODE_APPROVAL = "approval"

ALL_MODES = (
    MODE_CONVERSATION, MODE_ANALYSIS, MODE_PLANNING, MODE_EXECUTION,
    MODE_MONITORING, MODE_DEBUGGING, MODE_LEARNING, MODE_APPROVAL,
)

# task_type is a free-form downstream hint for model-tier selection.
_TASK_TYPE_DEFAULT = "chat"

# ── Approval / rejection (highest priority — short, unambiguous) ───────────────
_APPROVE = (
    "approve", "approved", "go ahead", "do it", "yes do it", "yes please",
    "proceed", "confirm", "confirmed", "ship it", "make it so", "sounds good",
    "lgtm", "looks good", "accept", "accepted", "ok do it", "okay do it",
)
_REJECT = (
    "reject", "rejected", "deny", "denied", "cancel", "abort", "stop",
    "don't", "do not", "no don't", "nope, ", "decline", "declined",
)
# bare yes/no only count as approval if the whole message is essentially that.
_BARE_YES = {"yes", "yep", "yeah", "y", "sure", "ok", "okay", "👍"}
_BARE_NO = {"no", "nope", "nah", "n"}

# ── Monitoring (status / what-is-running questions) ────────────────────────────
_MONITOR = (
    "what is running", "what's running", "whats running", "what is the system doing",
    "what's the system doing", "what are you doing", "what is going on",
    "what's going on", "status", "health", "uptime", "how are things",
    "is it done", "are we done", "current state", "show me the dashboard",
    "system status", "any errors", "what's happening", "whats happening",
    "live metrics", "active tasks", "running tasks", "what is active",
)

# ── Debugging (root-cause / why-failed) ────────────────────────────────────────
_DEBUG = (
    "why did", "why does", "why is", "why won't", "why wont", "why can't",
    "why cant", "what went wrong", "what's wrong", "whats wrong",
    "diagnose", "root cause", "root-cause", "traceback", "stack trace",
    "stacktrace", "exception", "crashed", "is broken", "not working",
    "doesn't work", "doesnt work", "keeps failing", "why failed",
    "why did that fail", "what caused",
)

# ── Execution (imperative DO-this verbs → is_command) ──────────────────────────
# Mapped to a task_type hint for downstream model-tier routing.
_EXEC_CODE = (
    "fix", "build", "implement", "refactor", "patch", "debug", "code",
    "rewrite", "compile", "merge", "rebase", "commit", "push", "scaffold",
)
_EXEC_DEPLOY = (
    "deploy", "release", "ship", "restart", "reboot", "rollback", "roll back",
    "start", "stop", "kill", "launch", "run", "execute", "trigger", "spin up",
    "scale", "provision",
)
_EXEC_GENERIC = (
    "create", "make", "add", "remove", "delete", "update", "change", "set up",
    "setup", "configure", "enable", "disable", "send", "generate", "write",
    "schedule", "install", "uninstall", "clean up", "cleanup", "optimize",
    "optimise", "apply",
)

# ── Planning ───────────────────────────────────────────────────────────────────
_PLAN = (
    "plan", "roadmap", "strategy", "how should we", "how do we", "how to",
    "steps to", "outline", "break down", "break it down", "design a",
    "architect", "approach for", "what's the plan", "lay out", "milestones",
)

# ── Analysis ───────────────────────────────────────────────────────────────────
_ANALYSIS = (
    "analyze", "analyse", "summarize", "summarise", "compare", "evaluate",
    "assess", "review", "explain", "interpret", "what is", "what are",
    "tell me about", "give me an overview", "tldr", "insights", "report on",
    "metrics for", "trends", "let's discuss", "lets discuss", "let's talk about",
    "thoughts on", "deep dive", "breakdown of",
)

# ── Learning ───────────────────────────────────────────────────────────────────
_LEARN = (
    "remember", "learn", "keep in mind", "note that", "from now on",
    "take note", "memorize", "memorise", "save this preference",
    "remember that", "going forward",
)

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def _hit(text: str, patterns) -> Optional[str]:
    """Return the first matching pattern (substring) or None."""
    for p in patterns:
        if p in text:
            return p
    return None


def _starts_with_verb(text: str, verbs) -> Optional[str]:
    """Match an imperative only when the message *starts* with the verb.

    Prevents 'why did the build fail' being treated as a build command.
    """
    first = text.split(" ", 1)[0].strip(".,!?:;")
    if first in verbs:
        return first
    # also catch leading polite filler: "please fix it", "can you build x"
    for lead in ("please ", "pls ", "can you ", "could you ", "would you ", "go "):
        if text.startswith(lead):
            rest = text[len(lead):].split(" ", 1)[0].strip(".,!?:;")
            if rest in verbs:
                return rest
    return None


class IntentClassifier:
    """Heuristic-first conversation-mode classifier (LLM escalation optional)."""

    def classify(self, text: str, context: Optional[dict] = None) -> dict:
        t = _norm(text)
        if not t:
            return self._result(MODE_CONVERSATION, "chat", 0.2, False,
                                 "empty input")

        heur = self._heuristic(t, context or {})
        # Escalate only when allowed AND the heuristic is shaky.
        if heur["confidence"] < 0.55 and os.getenv("COMPANION_LLM_INTENT") == "1":
            llm = self._llm_escalate(text, context or {})
            if llm is not None:
                llm["reason"] = f"llm-escalated ({llm.get('reason', '')})".strip()
                return llm
        return heur

    # ── Stage 1: fast heuristic ────────────────────────────────────────────────
    def _heuristic(self, t: str, context: dict) -> dict:
        words = t.split()
        n_words = len(words)

        # 1) Approval / rejection — highest priority, short messages.
        if t in _BARE_YES or (n_words <= 4 and _hit(t, _APPROVE)):
            return self._result(MODE_APPROVAL, "chat", 0.95, False,
                                 "approval phrase")
        if t in _BARE_NO or (n_words <= 6 and _hit(t, _REJECT)):
            return self._result(MODE_APPROVAL, "chat", 0.9, False,
                                 "rejection phrase")

        # 2) Monitoring — status questions.
        if (m := _hit(t, _MONITOR)):
            return self._result(MODE_MONITORING, "monitoring", 0.9, False,
                                 f"monitoring cue: '{m}'")

        # 3) Debugging — why/what-went-wrong. Checked before execution so that
        #    'why did the deploy fail' is debugging, not a deploy command.
        if (d := _hit(t, _DEBUG)):
            return self._result(MODE_DEBUGGING, "analysis", 0.9, False,
                                 f"debugging cue: '{d}'")

        # 4) Execution — imperative leading verb ⇒ is_command.
        for verbs, ttype in ((_EXEC_CODE, "code"),
                             (_EXEC_DEPLOY, "monitoring"),
                             (_EXEC_GENERIC, "chat")):
            if (v := _starts_with_verb(t, verbs)):
                # code verbs imply a code task; deploy/run imply ops.
                tt = "code" if verbs is _EXEC_CODE else (
                    "monitoring" if verbs is _EXEC_DEPLOY else "chat")
                return self._result(MODE_EXECUTION, tt, 0.85, True,
                                    f"imperative verb: '{v}'")

        # 5) Planning.
        if (p := _hit(t, _PLAN)):
            return self._result(MODE_PLANNING, "analysis", 0.8, False,
                                 f"planning cue: '{p}'")

        # 6) Learning.
        if (l := _hit(t, _LEARN)):
            return self._result(MODE_LEARNING, "chat", 0.8, False,
                                 f"learning cue: '{l}'")

        # 7) Analysis / discussion.
        if (a := _hit(t, _ANALYSIS)):
            ttype = "research" if a in ("what is", "tell me about",
                                        "deep dive") else "analysis"
            return self._result(MODE_ANALYSIS, ttype, 0.75, False,
                                f"analysis cue: '{a}'")

        # 8) Bare imperative anywhere (weaker) — verb not at the very start.
        if _hit(t, _EXEC_CODE) or _hit(t, _EXEC_DEPLOY):
            return self._result(MODE_EXECUTION, "code", 0.55, True,
                                "imperative verb present")

        # 9) Default — open conversation.
        return self._result(MODE_CONVERSATION, "chat", 0.4, False,
                            "no strong cue — defaulting to conversation")

    # ── Stage 2: optional LLM escalation (guarded) ─────────────────────────────
    def _llm_escalate(self, text: str, context: dict) -> Optional[dict]:
        """Ask the engine LLM for a JSON intent. Returns None on any failure."""
        try:
            from engine.api import process_input, generate  # local import
            # Route through the engine normaliser first (per gateway contract).
            try:
                process_input(text)
            except Exception:  # noqa: BLE001 — normaliser is best-effort
                pass
            modes = ", ".join(ALL_MODES)
            prompt = (
                "Classify the user's message into exactly one conversation mode.\n"
                f"Allowed modes: {modes}.\n"
                "is_command=true only if the user is telling the system to DO "
                "something (execution).\n"
                "task_type is one of: code, research, analysis, chat, monitoring.\n"
                "Reply with ONLY a JSON object: "
                '{"mode":"","task_type":"","is_command":false,"confidence":0.0}.\n\n'
                f"Message: {text!r}"
            )
            raw = generate(
                prompt=prompt,
                system="You are a strict JSON intent classifier. Output JSON only.",
                timeout=20,
            )
            return self._parse_llm(raw)
        except Exception as exc:  # noqa: BLE001 — degrade to heuristic
            logger.debug("LLM intent escalation failed: %s", exc)
            return None

    def _parse_llm(self, raw: str) -> Optional[dict]:
        import json
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
        mode = str(data.get("mode", "")).strip().lower()
        if mode not in ALL_MODES:
            return None
        ttype = str(data.get("task_type", "") or _TASK_TYPE_DEFAULT).strip().lower()
        try:
            conf = float(data.get("confidence", 0.6))
        except (ValueError, TypeError):
            conf = 0.6
        conf = max(0.0, min(1.0, conf))
        is_cmd = bool(data.get("is_command", mode == MODE_EXECUTION))
        return self._result(mode, ttype, conf, is_cmd, "llm")

    @staticmethod
    def _result(mode: str, task_type: str, confidence: float,
                is_command: bool, reason: str) -> dict:
        return {
            "mode": mode,
            "task_type": task_type,
            "confidence": round(float(confidence), 3),
            "is_command": bool(is_command),
            "reason": reason,
        }


_SINGLETON: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """Return the process-wide IntentClassifier singleton."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = IntentClassifier()
    return _SINGLETON

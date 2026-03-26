"""Feedback Loop — tracks reply rates, scores message templates, auto-improves prompts.

Monitors outreach performance by recording send/reply events per message template,
computing template scores, and using AI to suggest improved prompt variants for
underperforming templates.

Storage:
    ~/.ai-employee/state/feedback_loop.json
        {
          "templates": {
            "<template_id>": {
              "template_id": "...",
              "category":    "cold_email" | "followup" | "dm" | ...,
              "text":        "...",
              "sends":       12,
              "replies":     3,
              "score":       0.25,
              "created_at":  "...",
              "updated_at":  "..."
            }
          },
          "events": [
            {"event": "send"|"reply", "template_id": "...", "lead_id": "...", "ts": "..."}
          ]
        }

Commands (via chatlog):
    feedback status           — show top/bottom performing templates
    feedback improve <cat>    — generate AI-improved prompt for a category
    feedback report           — full performance report

Usage from other bots:
    from feedback_loop import FeedbackLoop
    fb = FeedbackLoop()
    fb.record_send(template_id="t1", lead_id="abc")
    fb.record_reply(template_id="t1", lead_id="abc")
    best = fb.best_template("cold_email")
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "feedback_loop.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"

POLL_INTERVAL = int(os.environ.get("FEEDBACK_LOOP_POLL_INTERVAL", "30"))
# Minimum sends before a template is eligible for improvement suggestions
MIN_SENDS_FOR_IMPROVEMENT = int(os.environ.get("FEEDBACK_MIN_SENDS", "5"))
# Reply rate below this threshold triggers auto-improvement
LOW_REPLY_RATE_THRESHOLD = float(os.environ.get("FEEDBACK_LOW_REPLY_RATE", "0.10"))
# Keep at most this many raw events (oldest removed first)
MAX_EVENTS = int(os.environ.get("FEEDBACK_MAX_EVENTS", "1000"))

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai as _query_ai  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"templates": {}, "events": []}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []


def _append_chatlog(e: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")


# ── FeedbackLoop class ────────────────────────────────────────────────────────

class FeedbackLoop:
    """Track reply rates, score templates, and auto-improve underperforming prompts."""

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self._file = state_file or STATE_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text())
            except Exception:
                pass
        return {"templates": {}, "events": []}

    def _save(self, state: dict) -> None:
        self._file.write_text(json.dumps(state, indent=2))

    def _recompute_score(self, tmpl: dict) -> float:
        sends = tmpl.get("sends", 0)
        replies = tmpl.get("replies", 0)
        if sends == 0:
            return 0.0
        return round(replies / sends, 4)

    # ── Template management ───────────────────────────────────────────────────

    def register_template(
        self,
        text: str,
        category: str = "general",
        template_id: Optional[str] = None,
    ) -> str:
        """Register a new message template and return its ID."""
        state = self._load()
        tid = template_id or str(uuid.uuid4())[:12]
        state["templates"][tid] = {
            "template_id": tid,
            "category": category,
            "text": text,
            "sends": 0,
            "replies": 0,
            "score": 0.0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self._save(state)
        return tid

    def record_send(self, template_id: str, lead_id: str = "") -> None:
        """Record that a message was sent using this template."""
        state = self._load()
        tmpl = state["templates"].get(template_id)
        if tmpl:
            tmpl["sends"] += 1
            tmpl["score"] = self._recompute_score(tmpl)
            tmpl["updated_at"] = _now_iso()
        # Append event
        state["events"].append({
            "event": "send", "template_id": template_id,
            "lead_id": lead_id, "ts": _now_iso(),
        })
        if len(state["events"]) > MAX_EVENTS:
            state["events"] = state["events"][-MAX_EVENTS:]
        self._save(state)

    def record_reply(self, template_id: str, lead_id: str = "") -> None:
        """Record that a lead replied to a message sent with this template."""
        state = self._load()
        tmpl = state["templates"].get(template_id)
        if tmpl:
            tmpl["replies"] += 1
            tmpl["score"] = self._recompute_score(tmpl)
            tmpl["updated_at"] = _now_iso()
        state["events"].append({
            "event": "reply", "template_id": template_id,
            "lead_id": lead_id, "ts": _now_iso(),
        })
        if len(state["events"]) > MAX_EVENTS:
            state["events"] = state["events"][-MAX_EVENTS:]
        self._save(state)

    def best_template(self, category: str) -> Optional[dict]:
        """Return the highest-scoring template for a category (or None)."""
        state = self._load()
        candidates = [
            t for t in state["templates"].values()
            if t.get("category") == category and t.get("sends", 0) > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda t: t["score"])

    def worst_templates(self, category: str, limit: int = 3) -> list:
        """Return the lowest-scoring templates for a category."""
        state = self._load()
        candidates = [
            t for t in state["templates"].values()
            if t.get("category") == category
            and t.get("sends", 0) >= MIN_SENDS_FOR_IMPROVEMENT
            and t.get("score", 1.0) < LOW_REPLY_RATE_THRESHOLD
        ]
        return sorted(candidates, key=lambda t: t["score"])[:limit]

    def get_stats(self, category: Optional[str] = None) -> dict:
        """Return aggregate send/reply stats (optionally filtered by category)."""
        state = self._load()
        templates = list(state["templates"].values())
        if category:
            templates = [t for t in templates if t.get("category") == category]
        total_sends = sum(t.get("sends", 0) for t in templates)
        total_replies = sum(t.get("replies", 0) for t in templates)
        return {
            "category": category or "all",
            "templates": len(templates),
            "total_sends": total_sends,
            "total_replies": total_replies,
            "reply_rate": round(total_replies / total_sends, 4) if total_sends else 0.0,
            "top_template": self.best_template(category or "") if category else None,
        }

    # ── AI prompt improvement ─────────────────────────────────────────────────

    def improve_template(self, template_id: str) -> Optional[str]:
        """Use AI to generate an improved version of a low-performing template.

        Returns the improved text, or None if AI is unavailable.
        """
        if not _AI_AVAILABLE:
            return None
        state = self._load()
        tmpl = state["templates"].get(template_id)
        if not tmpl:
            return None

        reply_rate = tmpl.get("score", 0.0)
        prompt = (
            f"This outreach message has a {reply_rate:.0%} reply rate — improve it.\n\n"
            f"Category: {tmpl.get('category', 'outreach')}\n"
            f"Original message:\n{tmpl.get('text', '')}\n\n"
            "Rewrite the message to be more engaging, specific, and likely to get a reply. "
            "Keep it short (under 150 words). Do not change the core offer."
        )
        system = (
            "You are an expert cold-email copywriter with a track record of >30% reply rates. "
            "Rewrite the provided message to dramatically improve its reply rate. "
            "Be conversational, specific, and end with a frictionless CTA."
        )
        result = (_query_ai(prompt, system_prompt=system) or {})
        return result.get("answer", "")

    def auto_improve_category(self, category: str) -> list:
        """Auto-improve all underperforming templates in a category.

        Returns a list of dicts: [{"template_id": ..., "improved_text": ...}]
        """
        improvements = []
        for tmpl in self.worst_templates(category):
            improved = self.improve_template(tmpl["template_id"])
            if improved:
                improvements.append({
                    "template_id": tmpl["template_id"],
                    "original_text": tmpl["text"],
                    "improved_text": improved,
                    "old_score": tmpl["score"],
                })
        return improvements

    # ── Reports ───────────────────────────────────────────────────────────────

    def status_report(self) -> str:
        """Return a human-readable performance report."""
        state = self._load()
        templates = list(state["templates"].values())
        if not templates:
            return "No templates tracked yet."

        total_sends = sum(t.get("sends", 0) for t in templates)
        total_replies = sum(t.get("replies", 0) for t in templates)
        overall_rate = total_replies / total_sends if total_sends else 0.0

        top = sorted(
            [t for t in templates if t.get("sends", 0) > 0],
            key=lambda t: t["score"],
            reverse=True,
        )[:3]
        bottom = sorted(
            [t for t in templates if t.get("sends", 0) >= MIN_SENDS_FOR_IMPROVEMENT],
            key=lambda t: t["score"],
        )[:3]

        lines = [
            f"📊 *Feedback Loop Report*",
            f"Templates: {len(templates)} | Sends: {total_sends} | "
            f"Replies: {total_replies} | Overall rate: {overall_rate:.1%}",
            "",
        ]
        if top:
            lines.append("🏆 Top performers:")
            for t in top:
                lines.append(
                    f"  [{t['template_id']}] {t.get('category','')} — "
                    f"{t['score']:.0%} ({t.get('replies',0)}/{t.get('sends',0)})"
                )
        if bottom:
            lines.append("\n⚠️ Underperformers (eligible for AI improvement):")
            for t in bottom:
                lines.append(
                    f"  [{t['template_id']}] {t.get('category','')} — "
                    f"{t['score']:.0%} ({t.get('replies',0)}/{t.get('sends',0)})"
                )
        return "\n".join(lines)


# ── Module-level singleton ────────────────────────────────────────────────────

_feedback = FeedbackLoop()


def record_send(template_id: str, lead_id: str = "") -> None:
    _feedback.record_send(template_id, lead_id)


def record_reply(template_id: str, lead_id: str = "") -> None:
    _feedback.record_reply(template_id, lead_id)


def register_template(text: str, category: str = "general", template_id: Optional[str] = None) -> str:
    return _feedback.register_template(text, category, template_id)


def best_template(category: str) -> Optional[dict]:
    return _feedback.best_template(category)


# ── Chatlog command loop ──────────────────────────────────────────────────────

def _process_chatlog(last_idx: int) -> int:
    chatlog = _load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        response: Optional[str] = None

        if msg_lower == "feedback status":
            response = _feedback.status_report()

        elif msg_lower.startswith("feedback improve "):
            category = msg[len("feedback improve "):].strip()
            improvements = _feedback.auto_improve_category(category)
            if not improvements:
                response = f"No underperforming templates found for category '{category}'."
            else:
                parts = [f"🔧 Improved {len(improvements)} template(s) for '{category}':"]
                for imp in improvements:
                    parts.append(
                        f"\n[{imp['template_id']}] Score was {imp['old_score']:.0%}\n"
                        f"Improved:\n{imp['improved_text']}"
                    )
                response = "\n".join(parts)

        elif msg_lower == "feedback report":
            response = _feedback.status_report()

        if response:
            print(response)
            _append_chatlog({
                "type": "bot", "bot": "feedback-loop",
                "message": response, "ts": _now_iso(),
            })

    return new_idx


def main() -> None:
    print(f"[{_now_iso()}] feedback-loop started; poll={POLL_INTERVAL}s")
    last_idx = len(_load_chatlog())

    while True:
        try:
            last_idx = _process_chatlog(last_idx)
        except Exception as exc:
            print(f"[{_now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

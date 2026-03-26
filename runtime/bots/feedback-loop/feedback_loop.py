"""Feedback Loop — automatic prompt optimisation for AI agents.

Tracks which outreach messages get replies and which are ignored, scores
message templates by effectiveness, and surfaces the best-performing
templates for reuse. Runs as a standalone service that polls the CRM for
state changes, but its core helpers can also be imported directly by any
bot.

How it works
────────────
1. Every outreach message is registered with record_message().
2. When a lead's status changes to "replied" the score for that template
   is bumped up (+1.0). When a lead is marked "lost" all of its messages
   get a small negative score (-0.2).
3. get_best_templates() returns the highest-scoring messages for a given
   niche/context — ready to be used as examples in AI prompts.
4. The service loop runs every FEEDBACK_POLL_INTERVAL seconds, scans the
   CRM for recent status changes, and updates scores automatically.

Storage:
    ~/.ai-employee/state/feedback_loop.json

Commands (via chatlog):
    feedback status           — show top-performing templates + reply rates
    feedback top <niche>      — show best templates for a specific niche
    feedback reset            — reset all scores (start fresh)

Config env vars:
    FEEDBACK_POLL_INTERVAL    — poll interval in seconds (default: 30)
    FEEDBACK_TOP_N            — number of top templates to surface (default: 5)
"""
import json
import logging
import os
import sys
import time
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
FEEDBACK_FILE = AI_HOME / "state" / "feedback_loop.json"
CRM_FILE = AI_HOME / "state" / "lead-generator-crm.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
STATE_FILE = AI_HOME / "state" / "feedback-loop.state.json"

POLL_INTERVAL = int(os.environ.get("FEEDBACK_POLL_INTERVAL", "30"))
TOP_N = int(os.environ.get("FEEDBACK_TOP_N", "5"))

# Positive score bump when a lead replies
_SCORE_REPLY = 1.0
# Negative score when a lead is marked lost (message didn't convert)
_SCORE_LOST = -0.2
# Bonus for leads that reached "qualified" or "appointment"
_SCORE_QUALIFIED = 2.0
_SCORE_WON = 3.0

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("feedback-loop")
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


def _load_feedback() -> dict:
    if FEEDBACK_FILE.exists():
        try:
            return json.loads(FEEDBACK_FILE.read_text())
        except Exception:
            pass
    return {
        "templates": {},
        "stats": {"total_messages": 0, "total_replies": 0, "reply_rate": 0.0},
        "last_updated": _now_iso(),
    }


def _save_feedback(data: dict) -> None:
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = _now_iso()
    FEEDBACK_FILE.write_text(json.dumps(data, indent=2))


def _load_crm() -> dict:
    if CRM_FILE.exists():
        try:
            return json.loads(CRM_FILE.read_text())
        except Exception:
            pass
    return {"items": []}
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


def _append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Core API ──────────────────────────────────────────────────────────────────

def record_message(
    lead_id: str,
    message: str,
    niche: str = "",
    channel: str = "email",
    tone: str = "",
) -> str:
    """Register an outreach message for tracking.

    Call this whenever a new message is sent to a lead. Returns a
    template_id that can be used to look up or update the template later.

    Args:
        lead_id:  CRM lead identifier.
        message:  The full message text.
        niche:    Lead niche/industry (used for grouping).
        channel:  Delivery channel ("email", "followup", "whatsapp", etc.).
        tone:     Tone label (e.g. "friendly", "persuasive").

    Returns:
        template_id string.
    """
    import hashlib
    # Use a hash of the message as a deduplication key so that identical
    # messages share the same template record and accumulate scores.
    template_id = hashlib.sha256(message.encode()).hexdigest()[:12]

    data = _load_feedback()
    templates = data.setdefault("templates", {})

    if template_id not in templates:
        templates[template_id] = {
            "id": template_id,
            "message": message,
            "niche": niche,
            "channel": channel,
            "tone": tone,
            "score": 0.0,
            "sends": 0,
            "replies": 0,
            "leads": [],
            "created_at": _now_iso(),
            "last_used": _now_iso(),
        }

    tpl = templates[template_id]
    tpl["sends"] = tpl.get("sends", 0) + 1
    tpl["last_used"] = _now_iso()
    if lead_id not in tpl.get("leads", []):
        tpl.setdefault("leads", []).append(lead_id)

    # Update global stats
    stats = data.setdefault("stats", {})
    stats["total_messages"] = stats.get("total_messages", 0) + 1

    _save_feedback(data)
    logger.debug("feedback_loop: registered message %s for lead %s", template_id, lead_id)
    return template_id


def record_outcome(lead_id: str, outcome: str) -> None:
    """Update template scores based on lead outcome.

    Args:
        lead_id: CRM lead identifier.
        outcome: "replied" | "qualified" | "appointment" | "won" | "lost"
    """
    score_map = {
        "replied": _SCORE_REPLY,
        "qualified": _SCORE_QUALIFIED,
        "appointment": _SCORE_QUALIFIED,
        "won": _SCORE_WON,
        "lost": _SCORE_LOST,
    }
    delta = score_map.get(outcome, 0.0)
    if delta == 0.0:
        return

    data = _load_feedback()
    templates = data.get("templates", {})
    updated = 0

    for tpl in templates.values():
        if lead_id in tpl.get("leads", []):
            tpl["score"] = round(tpl.get("score", 0.0) + delta, 3)
            if outcome in ("replied", "qualified", "appointment", "won"):
                tpl["replies"] = tpl.get("replies", 0) + 1
            updated += 1

    if updated:
        # Update global reply rate
        stats = data.setdefault("stats", {})
        total = stats.get("total_messages", 1)
        total_replies = sum(
            t.get("replies", 0) for t in templates.values()
        )
        stats["total_replies"] = total_replies
        stats["reply_rate"] = round(total_replies / max(total, 1), 3)

        _save_feedback(data)
        logger.info(
            "feedback_loop: outcome=%s lead=%s → updated %d templates (delta=%.1f)",
            outcome, lead_id, updated, delta,
        )


def get_best_templates(
    niche: str = "",
    channel: str = "",
    limit: int = TOP_N,
) -> list:
    """Return the highest-scoring message templates for a given context.

    Args:
        niche:   Optional niche filter (e.g. "SaaS", "real estate").
        channel: Optional channel filter (e.g. "email", "followup").
        limit:   Max templates to return.

    Returns:
        List of template dicts sorted by score descending.
        Each dict has: id, message, niche, channel, tone, score, sends, replies.
    """
    data = _load_feedback()
    templates = list(data.get("templates", {}).values())

    if niche:
        niche_lower = niche.lower()
        templates = [
            t for t in templates
            if niche_lower in t.get("niche", "").lower() or not t.get("niche")
        ]
    if channel:
        templates = [t for t in templates if t.get("channel", "") == channel]

    # Sort by score desc, then by reply rate (replies/sends)
    def _sort_key(t: dict) -> tuple:
        sends = max(t.get("sends", 1), 1)
        reply_rate = t.get("replies", 0) / sends
        return (-t.get("score", 0.0), -reply_rate)

    templates.sort(key=_sort_key)
    return templates[:limit]


def get_best_template_as_example(niche: str = "", channel: str = "email") -> str:
    """Return the best-performing template as a prompt example string.

    Suitable for injecting into AI system prompts as a "best example" so the
    model produces similar high-performing messages.

    Returns:
        A formatted string, or empty string if no templates exist yet.
    """
    best = get_best_templates(niche=niche, channel=channel, limit=1)
    if not best:
        return ""
    tpl = best[0]
    sends = max(tpl.get("sends", 1), 1)
    reply_pct = round(tpl.get("replies", 0) / sends * 100)
    return (
        f"[Best-performing {channel} template — {reply_pct}% reply rate]\n"
        f"{tpl.get('message', '')}"
    )


def get_stats() -> dict:
    """Return aggregate feedback statistics."""
    data = _load_feedback()
    templates = list(data.get("templates", {}).values())
    stats = data.get("stats", {})
    top = get_best_templates(limit=3)
    return {
        "total_templates": len(templates),
        "total_messages": stats.get("total_messages", 0),
        "total_replies": stats.get("total_replies", 0),
        "reply_rate": stats.get("reply_rate", 0.0),
        "top_templates": [
            {
                "id": t["id"],
                "score": t["score"],
                "sends": t["sends"],
                "replies": t.get("replies", 0),
                "niche": t.get("niche", ""),
                "preview": t.get("message", "")[:80],
            }
            for t in top
        ],
        "last_updated": data.get("last_updated", ""),
    }


def reset_scores() -> None:
    """Reset all template scores to zero (keep templates, clear scores)."""
    data = _load_feedback()
    for tpl in data.get("templates", {}).values():
        tpl["score"] = 0.0
        tpl["replies"] = 0
    data["stats"] = {"total_messages": 0, "total_replies": 0, "reply_rate": 0.0}
    _save_feedback(data)
    logger.info("feedback_loop: all scores reset")


# ── CRM Scanner (automatic score updates) ─────────────────────────────────────

def _scan_crm_for_outcomes(seen_outcomes: dict) -> dict:
    """Scan the CRM and record outcomes for leads that have changed status.

    Args:
        seen_outcomes: Dict of {lead_id: last_known_status} from previous scan.

    Returns:
        Updated seen_outcomes dict.
    """
    crm = _load_crm()
    for lead in crm.get("items", []):
        lead_id = lead.get("id", "")
        status = lead.get("status", "")
        if not lead_id:
            continue

        prev_status = seen_outcomes.get(lead_id)

        if prev_status != status:
            # Register all outreach messages in the template store
            for msg_obj in lead.get("outreach_messages", []):
                msg_text = msg_obj.get("message", "")
                if msg_text and prev_status is None:
                    # First time seeing this lead — register existing messages
                    record_message(
                        lead_id=lead_id,
                        message=msg_text,
                        niche=lead.get("niche", ""),
                        channel=msg_obj.get("channel", "email"),
                        tone=msg_obj.get("tone", ""),
                    )

            # Record the outcome for score updates
            if prev_status is not None and status in (
                "replied", "qualified", "appointment", "won", "lost"
            ):
                record_outcome(lead_id, status)
                logger.info(
                    "feedback_loop: lead %s (%s) status %s → %s",
                    lead_id, lead.get("name", "?"), prev_status, status,
                )

            seen_outcomes[lead_id] = status

    return seen_outcomes


# ── Command Handling ──────────────────────────────────────────────────────────

def _handle_command(message: str) -> Optional[str]:
    msg = message.strip().lower()

    if msg == "feedback status":
        stats = get_stats()
        lines = [
            "📊 *Feedback Loop Status*",
            f"Templates tracked: {stats['total_templates']}",
            f"Messages sent: {stats['total_messages']}",
            f"Replies received: {stats['total_replies']}",
            f"Reply rate: {stats['reply_rate']*100:.1f}%",
            "",
            "🏆 Top templates:",
        ]
        for i, t in enumerate(stats["top_templates"], 1):
            lines.append(
                f"  {i}. [{t['id']}] score={t['score']} | "
                f"{t['replies']}/{t['sends']} replies | "
                f"{t.get('niche','?')} | {t.get('preview','')[:60]}…"
            )
        return "\n".join(lines)

    if msg.startswith("feedback top "):
        niche = message.strip()[len("feedback top "):].strip()
        best = get_best_templates(niche=niche, limit=5)
        if not best:
            return f"No templates found for niche '{niche}' yet."
        lines = [f"🏆 *Best templates for '{niche}':*"]
        for t in best:
            sends = max(t.get("sends", 1), 1)
            reply_pct = round(t.get("replies", 0) / sends * 100)
            lines.append(
                f"\n[{t['id']}] score={t['score']} | {reply_pct}% reply rate\n"
                f"{t.get('message','')[:200]}"
            )
        return "\n".join(lines)

    if msg == "feedback reset":
        reset_scores()
        return "✅ Feedback scores reset. Templates kept, scores zeroed."

    return None


# ── Main service loop ─────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{_now_iso()}] feedback-loop started; poll={POLL_INTERVAL}s")
    seen_outcomes: dict = {}
    last_processed_idx = len(_load_chatlog())

    while True:
        # Process new chatlog commands
        chatlog = _load_chatlog()
        new_entries = chatlog[last_processed_idx:]
        last_processed_idx = len(chatlog)

        for entry in new_entries:
            if entry.get("type") != "user":
                continue
            message = entry.get("message", "").strip()
            if not message:
                continue
            response = _handle_command(message)
            if response:
                _append_chatlog({
                    "ts": _now_iso(),
                    "type": "bot",
                    "bot": "feedback-loop",
                    "message": response,
                })

        # Auto-scan CRM for outcome changes
        seen_outcomes = _scan_crm_for_outcomes(seen_outcomes)

        # Write state
        stats = get_stats()
        _write_state({
            "bot": "feedback-loop",
            "ts": _now_iso(),
            "status": "running",
            "total_templates": stats["total_templates"],
            "reply_rate": stats["reply_rate"],
        })

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

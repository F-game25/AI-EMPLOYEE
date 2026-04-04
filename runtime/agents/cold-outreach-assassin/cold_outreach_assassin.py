"""ColdOutreachAssassin Bot — Multi-channel cold sequence builder.

Builds and manages high-converting cold outreach sequences across channels:
  - Multi-channel sequence builder (email/LinkedIn/WhatsApp)
  - A/B test variant generation for sequences
  - Reply status tracking per lead
  - Auto follow-up scheduling
  - Full outreach blasts per niche
  - Sequence and reply rate reporting

Commands (via chatlog / WhatsApp / Dashboard):
  outreach sequence <target> <channel>  — build multi-channel cold sequence
  outreach abtest <sequence_id>         — A/B test variants for a sequence
  outreach track <lead_id>              — track reply status for a lead
  outreach followup <sequence_id>       — auto follow-up scheduler
  outreach blast <niche>                — full outreach blast for a niche
  outreach status                       — show sequences and reply rates

State files:
  ~/.ai-employee/state/cold-outreach-assassin.state.json
  ~/.ai-employee/state/outreach-sequences.json
"""
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "cold-outreach-assassin.state.json"
SEQUENCES_FILE = AI_HOME / "state" / "outreach-sequences.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("COLD_OUTREACH_ASSASSIN_POLL_INTERVAL", "5"))

DEFAULT_CHANNEL = "email"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("cold-outreach-assassin")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_sequences() -> list:
    if not SEQUENCES_FILE.exists():
        return []
    try:
        return json.loads(SEQUENCES_FILE.read_text())
    except Exception:
        return []


def save_sequences(sequences: list) -> None:
    SEQUENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEQUENCES_FILE.write_text(json.dumps(sequences, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    entries = []
    try:
        for line in CHATLOG.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except Exception:
        pass
    return entries


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def ai_query(prompt: str, system_prompt: str = "") -> str:
    if not _AI_AVAILABLE:
        return "AI router not available."
    try:
        result = _query_ai_for_agent("cold-outreach-assassin", prompt, system_prompt=system_prompt)
        return result.get("answer", "No response generated.")
    except Exception as exc:
        return f"AI query failed: {exc}"


def write_orchestrator_result(subtask_id: str, result_text: str, status: str = "done") -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{subtask_id}.json"
    result_file.write_text(json.dumps({
        "subtask_id": subtask_id,
        "status": status,
        "result": result_text,
        "completed_at": now_iso(),
    }))


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "cold-outreach-assassin.queue.jsonl"
    if not queue_file.exists():
        return []
    lines = queue_file.read_text().splitlines()
    pending = []
    for line in lines:
        if line.strip():
            try:
                pending.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if pending:
        queue_file.write_text("")
    return pending


def process_subtask(subtask: dict) -> None:
    subtask_id = subtask.get("subtask_id", "")
    instructions = subtask.get("instructions", "")
    result = ai_query(instructions, SYSTEM_PROMPT)
    write_orchestrator_result(subtask_id, result)
    logger.info("cold-outreach-assassin: completed subtask '%s'", subtask_id)


SYSTEM_PROMPT = (
    "You are ColdOutreachAssassin, a cold outreach expert who has sent millions of emails and "
    "LinkedIn messages with above-average reply rates. You build perfectly timed multi-channel "
    "sequences with personalized hooks, objection pre-emptions, and A/B tested subject lines. "
    "You know exactly when to follow up and what to say to get a reply."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_sequence(target: str, channel: str) -> str:
    sequences = load_sequences()
    result = ai_query(
        f"Build a multi-channel cold outreach sequence for target: {target} on channel: {channel}\n\n"
        "## Sequence Overview\n"
        f"Channel mix: {channel} (primary) + complementary channels\n"
        "Total touchpoints: 7–9 over 21 days\n\n"
        "## Full Sequence (day-by-day)\n"
        "For each touchpoint:\n"
        "- **Day**: [number]\n"
        "- **Channel**: [email/LinkedIn/WhatsApp]\n"
        "- **Type**: [first touch / follow-up / breakup]\n"
        "- **Subject** (email only): [subject line]\n"
        "- **Body**: [full message, word-for-word]\n"
        "- **Send time**: [best time of day + timezone logic]\n\n"
        "## Personalization Tokens\n"
        "{{first_name}}, {{company}}, {{role}}, {{pain_point}}, {{trigger}} — instructions for each\n\n"
        "## Objection Pre-emptions\n"
        "Weave these 3 objections into the sequence proactively\n\n"
        "## Exit Conditions\n"
        "When to stop the sequence (reply, bounce, unsubscribe)\n\n"
        "## Expected Metrics\n"
        "Open rate, reply rate, meeting rate benchmarks",
        SYSTEM_PROMPT,
    )
    seq_entry = {
        "id": str(uuid.uuid4())[:8],
        "target": target,
        "channel": channel,
        "created_at": now_iso(),
        "status": "active",
        "replies": 0,
    }
    sequences.insert(0, seq_entry)
    save_sequences(sequences[:100])
    return result


def cmd_abtest(sequence_id: str) -> str:
    return ai_query(
        f"Create A/B test variants for outreach sequence ID: {sequence_id}\n\n"
        "## Elements to A/B Test\n"
        "Rank by impact potential:\n"
        "1. Subject line\n"
        "2. First sentence hook\n"
        "3. CTA phrasing\n"
        "4. Send day/time\n"
        "5. Email length (short vs long)\n\n"
        "## Variant Matrix (5 tests)\n"
        "For each test:\n"
        "- **Test name**: [descriptive]\n"
        "- **Hypothesis**: If we change [X], reply rate will increase by [Y%] because [reason]\n"
        "- **Control (A)**: [exact current copy]\n"
        "- **Variant (B)**: [exact new copy]\n"
        "- **Split**: 50/50 or [other ratio with reason]\n"
        "- **Duration**: [days needed for significance]\n"
        "- **Success metric**: [primary KPI]\n\n"
        "## Statistical Significance\n"
        "Minimum sample size per variant for 95% confidence\n\n"
        "## Interpretation Guide\n"
        "How to read results and decide winner\n\n"
        "## Winning Formula\n"
        "Expected best-performing combination based on cold outreach data",
        SYSTEM_PROMPT,
    )


def cmd_track(lead_id: str) -> str:
    return ai_query(
        f"Analyze reply tracking for lead ID: {lead_id}\n\n"
        "## Reply Status Analysis\n"
        "- No reply scenarios: which step they stalled at\n"
        "- Reply classification: interested / not interested / referral / auto-reply\n\n"
        "## Next Best Action\n"
        "Based on silence or reply type, exact next message to send\n\n"
        "## Lead Scoring Update\n"
        "How engagement (opens, clicks, replies) updates ICP score\n\n"
        "## Re-engagement Window\n"
        "When to try again after no reply (30/60/90 day rules)\n\n"
        "## CRM Update Template\n"
        "JSON fields to update in CRM based on tracking data",
        SYSTEM_PROMPT,
    )


def cmd_followup(sequence_id: str) -> str:
    return ai_query(
        f"Design auto follow-up scheduler for sequence ID: {sequence_id}\n\n"
        "## Follow-Up Logic\n"
        "Decision tree: [reply type] → [next action]\n\n"
        "## Follow-Up Messages (5 variants by scenario)\n\n"
        "**Scenario 1 — No reply after email #1** (Day 3):\n"
        "[exact message]\n\n"
        "**Scenario 2 — Opened but no reply** (Day 5):\n"
        "[exact message — reference their open signal subtly]\n\n"
        "**Scenario 3 — 'Not interested' reply**:\n"
        "[graceful pivot message to keep door open]\n\n"
        "**Scenario 4 — 'Maybe later' reply**:\n"
        "[future follow-up schedule with messages]\n\n"
        "**Scenario 5 — Breakup message** (Day 21):\n"
        "[final message that often gets replies]\n\n"
        "## Timing Optimization\n"
        "Best days and times for follow-ups by industry\n\n"
        "## Automation Setup\n"
        "How to configure this in Lemlist / Instantly / Apollo",
        SYSTEM_PROMPT,
    )


def cmd_blast(niche: str) -> str:
    sequences = load_sequences()
    result = ai_query(
        f"Design a full outreach blast campaign for niche: {niche}\n\n"
        "## Campaign Architecture\n"
        "- Total leads: [target number]\n"
        "- Channels: email + LinkedIn + [optional 3rd]\n"
        "- Duration: [total days]\n"
        "- Daily send volume: [number with warm-up schedule]\n\n"
        "## Segmentation\n"
        "3 lead segments with different messaging angles\n\n"
        "## Master Copy Kit\n"
        "For each segment: subject lines (5), email body (2 variants), LinkedIn message\n\n"
        "## Infrastructure Setup\n"
        "- Domain warm-up schedule\n"
        "- Sending limits by day\n"
        "- SPF/DKIM/DMARC checklist\n\n"
        "## Launch Checklist\n"
        "20-item checklist before hitting send\n\n"
        "## Tracking Dashboard\n"
        "Metrics to monitor daily during the blast\n\n"
        "## Risk Mitigation\n"
        "How to avoid spam filters and domain blacklisting",
        SYSTEM_PROMPT,
    )
    blast_entry = {
        "id": str(uuid.uuid4())[:8],
        "niche": niche,
        "created_at": now_iso(),
        "status": "blast",
        "replies": 0,
    }
    sequences.insert(0, blast_entry)
    save_sequences(sequences[:100])
    return result


def cmd_status() -> str:
    sequences = load_sequences()
    if not sequences:
        return "No outreach sequences yet. Try: `outreach sequence <target> <channel>`"
    lines = ["💀 *ColdOutreachAssassin — Sequences:*"]
    lines.append(f"  Total sequences: {len(sequences)}")
    active = sum(1 for s in sequences if s.get("status") == "active")
    total_replies = sum(s.get("replies", 0) for s in sequences)
    lines.append(f"  Active: {active} | Total replies logged: {total_replies}")
    lines.append("\n*Recent sequences:*")
    for s in sequences[:5]:
        target = s.get("target", s.get("niche", "?"))
        lines.append(
            f"  • `{s.get('id','?')}` — {str(target)[:40]} [{s.get('channel','?')}] "
            f"({s.get('status','?')})"
        )
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("outreach ") and msg_lower != "outreach":
        return None

    rest = msg[9:].strip() if msg_lower.startswith("outreach ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("sequence "):
        parts = rest[9:].strip().split(None, 1)
        target = parts[0] if parts else "general"
        channel = parts[1] if len(parts) > 1 else DEFAULT_CHANNEL
        return cmd_sequence(target, channel)
    if rest_lower.startswith("abtest "):
        return cmd_abtest(rest[7:].strip())
    if rest_lower.startswith("track "):
        return cmd_track(rest[6:].strip())
    if rest_lower.startswith("followup "):
        return cmd_followup(rest[9:].strip())
    if rest_lower.startswith("blast "):
        return cmd_blast(rest[6:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "💀 *ColdOutreachAssassin Commands:*\n"
            "  `outreach sequence <target> <channel>` — build multi-channel sequence\n"
            "  `outreach abtest <sequence_id>` — A/B test variants\n"
            "  `outreach track <lead_id>` — track reply status\n"
            "  `outreach followup <sequence_id>` — auto follow-up scheduler\n"
            "  `outreach blast <niche>` — full outreach blast\n"
            "  `outreach status` — sequences and reply rates"
        )

    return "Unknown outreach command. Try `outreach help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] cold-outreach-assassin started; poll_interval={POLL_INTERVAL}s; {ai_status}")

    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)

    last_processed_idx = len(load_chatlog())

    while True:
        for subtask in check_agent_queue():
            process_subtask(subtask)

        chatlog = load_chatlog()
        new_entries = chatlog[last_processed_idx:]
        last_processed_idx = len(chatlog)

        for entry in new_entries:
            if entry.get("type") != "user":
                continue
            message = entry.get("message", "").strip()
            if not message:
                continue
            response = handle_command(message)
            if response:
                append_chatlog({
                    "ts": now_iso(),
                    "type": "bot",
                    "bot": "cold-outreach-assassin",
                    "message": response,
                })
                logger.info("cold-outreach-assassin: handled command: %s", message[:60])

        sequences = load_sequences()
        write_state({
            "bot": "cold-outreach-assassin",
            "ts": now_iso(),
            "status": "running",
            "total_sequences": len(sequences),
            "active_sequences": sum(1 for s in sequences if s.get("status") == "active"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

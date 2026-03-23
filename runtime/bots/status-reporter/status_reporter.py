"""Status Reporter bot.

Generates compact hourly status summaries and can send them via WhatsApp
through the OpenClaw gateway (if configured). Also writes status to state files.

Usage: can be triggered by openclaw cron hourly, or run as a long-running daemon.
"""
import json
import os
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
STATUS_FILE = AI_HOME / "state" / "status-reporter.state.json"

REPORT_INTERVAL = int(os.environ.get("STATUS_REPORT_INTERVAL_SECONDS", "3600"))
PHONE = os.environ.get("WHATSAPP_PHONE", "")
GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_bot_states() -> list:
    states = []
    if not STATE_DIR.exists():
        return states
    for f in STATE_DIR.glob("*.state.json"):
        try:
            data = json.loads(f.read_text())
            if "bot" in data or "bots" in data:
                states.append(data)
        except Exception:
            pass
    return states


def build_compact_status() -> str:
    """Build a compact WhatsApp-friendly status message."""
    lines = [f"🤖 *AI Employee Status* — {now_iso()}"]
    lines.append("─────────────────")

    # Bot status
    bot_statuses = []
    state_file = STATE_DIR / "problem-solver.state.json"
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            for b in data.get("bots", []):
                icon = "🟢" if b.get("running") else "🔴"
                bot_statuses.append(f"{icon} {b['bot']}")
        except Exception:
            pass

    if bot_statuses:
        lines.append("*Bots:*")
        lines.extend(f"  {s}" for s in bot_statuses)
    else:
        lines.append("*Bots:* no data yet")

    # Polymarket state
    pm_state = STATE_DIR / "polymarket-trader.state.json"
    if pm_state.exists():
        try:
            pm = json.loads(pm_state.read_text())
            mode = "LIVE" if pm.get("live") else "PAPER"
            found = pm.get("actions_found", 0)
            lines.append(f"*Trading:* {mode} | signals: {found}")
        except Exception:
            pass

    # Scheduler state
    sched_state = STATE_DIR / "scheduler-runner.state.json"
    if sched_state.exists():
        try:
            sched = json.loads(sched_state.read_text())
            ran = sched.get("tasks_run_last_cycle", 0)
            lines.append(f"*Scheduler:* tasks last cycle: {ran}")
        except Exception:
            pass

    # Improvements
    improvements_file = AI_HOME / "state" / "improvements.json"
    if improvements_file.exists():
        try:
            imps = json.loads(improvements_file.read_text())
            pending = sum(1 for i in imps if i.get("status") == "pending")
            if pending:
                lines.append(f"*Improvements:* {pending} pending approval ⚠️")
        except Exception:
            pass

    lines.append("─────────────────")
    lines.append("Reply *status*, *workers*, *schedule*, *improvements*")
    return "\n".join(lines)


def send_whatsapp(message: str) -> bool:
    """Send a WhatsApp message via OpenClaw gateway REST API."""
    if not PHONE or not GATEWAY_TOKEN:
        return False
    try:
        import urllib.request
        payload = json.dumps({"to": PHONE, "text": message}).encode()
        req = urllib.request.Request(
            f"{GATEWAY_URL}/api/v1/send",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception as e:
        print(f"[status-reporter] send_whatsapp failed: {e}")
        return False


def append_chatlog(entry: dict):
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def write_state(state: dict):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(state, indent=2))


def main():
    print(f"[{now_iso()}] status-reporter started; interval={REPORT_INTERVAL}s")

    # Send welcome/startup message once if installer queued one
    startup_file = AI_HOME / "state" / "startup_message.json"
    if startup_file.exists():
        try:
            data = json.loads(startup_file.read_text())
            if data.get("pending"):
                msg = data.get("message", "")
                if msg:
                    print(f"[{now_iso()}] sending startup welcome message…")
                    sent = send_whatsapp(msg)
                    if sent:
                        data["pending"] = False
                        data["sent_at"] = now_iso()
                        startup_file.write_text(json.dumps(data, indent=2))
                        append_chatlog({"ts": now_iso(), "type": "bot", "message": msg})
                        print(f"[{now_iso()}] welcome message sent")
                    else:
                        print(f"[{now_iso()}] welcome message queued but gateway not reachable yet; will retry next cycle")
        except Exception as e:
            print(f"[{now_iso()}] startup message error: {e}")

    while True:
        msg = build_compact_status()
        print(f"[{now_iso()}] status report:\n{msg}\n")

        sent = send_whatsapp(msg)
        entry = {
            "ts": now_iso(),
            "type": "status_report",
            "message": msg,
            "sent_whatsapp": sent,
        }
        append_chatlog(entry)
        write_state(
            {
                "bot": "status-reporter",
                "last_report": now_iso(),
                "last_sent_whatsapp": sent,
                "status": "running",
            }
        )

        time.sleep(REPORT_INTERVAL)


if __name__ == "__main__":
    main()

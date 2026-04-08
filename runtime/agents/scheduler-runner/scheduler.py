"""Scheduler Runner bot.

Reads ~/.ai-employee/config/schedules.json and triggers scheduled tasks
at their defined times. Tasks can be bot starts, WhatsApp messages, or
shell commands (safe: no arbitrary exec by default).

State is written to ~/.ai-employee/state/scheduler-runner.state.json
"""
import json
import os
import signal
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
SCHEDULES_FILE = AI_HOME / "config" / "schedules.json"
STATE_FILE = AI_HOME / "state" / "scheduler-runner.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"

CHECK_INTERVAL = int(os.environ.get("SCHEDULER_CHECK_INTERVAL", "60"))
UI_HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")
UI_PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787"))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def load_schedules() -> list:
    if not SCHEDULES_FILE.exists():
        return []
    try:
        return json.loads(SCHEDULES_FILE.read_text())
    except Exception as e:
        print(f"[scheduler] load error: {e}")
        return []


def _parse_interval_minutes(task: dict) -> int:
    """Parse interval from several schedule formats.

    Supported values:
      - interval_minutes: <int>
      - interval: 1min | 5min | hourly | daily | weekly
      - type=daily/weekly with run_at_utc support (handled in should_run)
    """
    if task.get("interval_minutes"):
        try:
            return max(1, int(task.get("interval_minutes", 60)))
        except Exception:
            return 60

    interval = str(task.get("interval", "")).strip().lower()
    if not interval:
        return 60

    if interval in ("hourly", "hour"):
        return 60
    if interval == "daily":
        return 24 * 60
    if interval == "weekly":
        return 7 * 24 * 60

    if interval.endswith("min"):
        try:
            return max(1, int(interval[:-3]))
        except Exception:
            return 60

    if interval.endswith("m"):
        try:
            return max(1, int(interval[:-1]))
        except Exception:
            return 60

    try:
        return max(1, int(interval))
    except Exception:
        return 60


def should_run(task: dict, last_run_map: dict) -> bool:
    """Determine if a task should run now based on its schedule."""
    task_id = task.get("id", "")
    enabled = task.get("enabled", True)
    if not enabled:
        return False

    schedule_type = str(task.get("type", "interval")).lower()
    interval = str(task.get("interval", "")).strip().lower()
    if interval in ("daily", "weekly"):
        schedule_type = interval
    now = now_dt()

    if schedule_type == "interval":
        interval_minutes = _parse_interval_minutes(task)
        last = last_run_map.get(task_id)
        if last is None:
            return True
        diff = (now - last).total_seconds() / 60
        return diff >= interval_minutes

    elif schedule_type == "daily":
        # Run at a specific HH:MM UTC time
        run_at = task.get("run_at_utc", "00:00")
        last = last_run_map.get(task_id)
        try:
            h, m = map(int, run_at.split(":"))
            if now.hour == h and now.minute == m:
                if last is None or (now - last).total_seconds() > 50:
                    return True
        except Exception:
            pass

    elif schedule_type == "weekly":
        run_at = task.get("run_at_utc", "00:00")
        run_day = str(task.get("weekday", "monday")).strip().lower()
        day_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target_day = day_map.get(run_day, 0)
        last = last_run_map.get(task_id)
        try:
            h, m = map(int, run_at.split(":"))
            if now.weekday() == target_day and now.hour == h and now.minute == m:
                if last is None or (now - last).total_seconds() > 50:
                    return True
        except Exception:
            pass

    return False


def _post_chat_task(message: str) -> dict:
    url = f"http://{UI_HOST}:{UI_PORT}/api/chat"
    payload = json.dumps({"message": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8", errors="replace"))
        return {"status": "ok", "response": body.get("response", "")[:300]}


def execute_task(task: dict) -> dict:
    """Execute a scheduled task. Returns execution result."""
    action = task.get("action", "log")
    if task.get("task") and action == "log":
        action = "chat"
    result: dict = {"task_id": task.get("id"), "ts": now_iso(), "action": action}

    if action == "log":
        msg = task.get("message", "(no message)")
        print(f"[scheduler] [{now_iso()}] LOG task: {msg}")
        result["status"] = "ok"

    elif action == "start_bot":
        bot = task.get("bot", "")
        if bot:
            try:
                p = subprocess.run(
                    [str(AI_HOME / "bin" / "ai-employee"), "start", bot],
                    capture_output=True, text=True, timeout=15
                )
                result["status"] = "ok" if p.returncode == 0 else "error"
                result["output"] = (p.stdout + p.stderr)[-300:]
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
        else:
            result["status"] = "error"
            result["error"] = "no bot specified"

    elif action == "stop_bot":
        bot = task.get("bot", "")
        if bot:
            try:
                p = subprocess.run(
                    [str(AI_HOME / "bin" / "ai-employee"), "stop", bot],
                    capture_output=True, text=True, timeout=15
                )
                result["status"] = "ok" if p.returncode == 0 else "error"
                result["output"] = (p.stdout + p.stderr)[-300:]
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)

    elif action == "status_report":
        # Trigger status reporter immediately
        try:
            p = subprocess.run(
                [str(AI_HOME / "bin" / "ai-employee"), "start", "status-reporter"],
                capture_output=True, text=True, timeout=15
            )
            result["status"] = "ok"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

    elif action == "chat":
        task_message = (task.get("task") or task.get("message") or "").strip()
        if not task_message:
            result["status"] = "error"
            result["error"] = "no task message provided"
        else:
            try:
                chat_res = _post_chat_task(task_message)
                result["status"] = chat_res.get("status", "ok")
                result["output"] = chat_res.get("response", "")
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)

    else:
        result["status"] = "skipped"
        result["note"] = f"unknown action: {action}"

    return result


def append_chatlog(entry: dict):
    try:
        CHATLOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHATLOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[scheduler] chatlog write warning: {e}")


def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    print(f"[{now_iso()}] scheduler-runner started; check_interval={CHECK_INTERVAL}s")

    # ── Graceful shutdown on SIGTERM / SIGINT ────────────────────────────────
    _stop_event = threading.Event()

    def _handle_signal(signum, frame):  # noqa: ARG001
        print(f"[{now_iso()}] scheduler-runner received signal {signum}, shutting down …")
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    last_run_map: dict = {}
    tasks_run_total = 0

    while not _stop_event.is_set():
        schedules = load_schedules()
        tasks_run_this_cycle = 0

        for task in schedules:
            task_id = task.get("id", "")
            if not task_id:
                continue

            if should_run(task, last_run_map):
                print(f"[{now_iso()}] scheduler firing task: {task_id}")
                result = execute_task(task)
                last_run_map[task_id] = now_dt()
                tasks_run_this_cycle += 1
                tasks_run_total += 1
                append_chatlog({"type": "scheduled_task", **result})

        write_state(
            {
                "bot": "scheduler-runner",
                "ts": now_iso(),
                "status": "running",
                "tasks_loaded": len(schedules),
                "tasks_run_last_cycle": tasks_run_this_cycle,
                "tasks_run_total": tasks_run_total,
            }
        )

        # Use event wait so SIGTERM wakes us immediately instead of after a full sleep
        _stop_event.wait(CHECK_INTERVAL)

    write_state({"bot": "scheduler-runner", "ts": now_iso(), "status": "stopped"})
    print(f"[{now_iso()}] scheduler-runner stopped.")


if __name__ == "__main__":
    main()

"""Scheduler Runner bot.

Reads ~/.ai-employee/config/schedules.json and triggers scheduled tasks
at their defined times. Tasks can be bot starts, WhatsApp messages, or
shell commands (safe: no arbitrary exec by default).

State is written to ~/.ai-employee/state/scheduler-runner.state.json
"""
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
SCHEDULES_FILE = AI_HOME / "config" / "schedules.json"
STATE_FILE = AI_HOME / "state" / "scheduler-runner.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"

CHECK_INTERVAL = int(os.environ.get("SCHEDULER_CHECK_INTERVAL", "60"))


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


def should_run(task: dict, last_run_map: dict) -> bool:
    """Determine if a task should run now based on its schedule."""
    task_id = task.get("id", "")
    enabled = task.get("enabled", True)
    if not enabled:
        return False

    schedule_type = task.get("type", "interval")
    now = now_dt()

    if schedule_type == "interval":
        interval_minutes = int(task.get("interval_minutes", 60))
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

    return False


def execute_task(task: dict) -> dict:
    """Execute a scheduled task. Returns execution result."""
    action = task.get("action", "log")
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

    else:
        result["status"] = "skipped"
        result["note"] = f"unknown action: {action}"

    return result


def append_chatlog(entry: dict):
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    print(f"[{now_iso()}] scheduler-runner started; check_interval={CHECK_INTERVAL}s")
    last_run_map: dict = {}
    tasks_run_total = 0

    while True:
        schedules = load_schedules()
        tasks_run_this_cycle = 0

        for task in schedules:
            task_id = task.get("id", "")
            if not task_id:
                continue

            if should_run(task, last_run_map):
                print(f"[scheduler] Running task: {task_id}")
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

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()

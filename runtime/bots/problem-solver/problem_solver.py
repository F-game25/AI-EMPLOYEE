"""Problem Solver / Watchdog bot.

Monitors other bots and restarts them if they crash.
Writes state to ~/.ai-employee/state/problem-solver.state.json
"""
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "problem-solver.state.json"

CHECK_INTERVAL = int(os.environ.get("PROBLEM_SOLVER_CHECK_INTERVAL", "10"))
AUTO_RESTART = os.environ.get("PROBLEM_SOLVER_AUTO_RESTART", "true").lower() == "true"
BOTS = [
    b.strip()
    for b in os.environ.get(
        "PROBLEM_SOLVER_WATCH_BOTS",
        "problem-solver-ui,polymarket-trader,status-reporter,scheduler-runner",
    ).split(",")
    if b.strip()
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list) -> tuple:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout


def bot_running(bot: str) -> bool:
    pid_file = AI_HOME / "run" / f"{bot}.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def ai_employee(*args: str) -> tuple:
    return run([str(AI_HOME / "bin" / "ai-employee"), *args])


def write_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        print(f"[{now_iso()}] warning: failed to write watchdog state: {e}")


def main():
    print(
        f"[{now_iso()}] problem-solver started; watching: {BOTS}; auto_restart={AUTO_RESTART}"
    )
    restart_counts: dict = {}

    while True:
        state = {"ts": now_iso(), "bots": [], "last_run": now_iso()}
        for bot in BOTS:
            ok = bot_running(bot)
            entry: dict = {"bot": bot, "running": ok, "ts": now_iso()}
            if not ok and AUTO_RESTART:
                print(f"[{now_iso()}] restarting {bot}")
                rc, out = ai_employee("start", bot)
                restart_counts[bot] = restart_counts.get(bot, 0) + 1
                entry["action"] = "restarted"
                entry["restart_count"] = restart_counts[bot]
                entry["rc"] = rc
                entry["out"] = out[-400:].strip()
                print(
                    f"[{now_iso()}] auto-restarted {bot} (count={restart_counts[bot]}) rc={rc}"
                )
            state["bots"].append(entry)

        write_state(state)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()

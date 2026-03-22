import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "run" / "problem-solver.state.json"

CHECK_INTERVAL = int(os.environ.get("PROBLEM_SOLVER_CHECK_INTERVAL", "5"))
AUTO_RESTART = os.environ.get("PROBLEM_SOLVER_AUTO_RESTART", "true").lower() == "true"
BOTS = os.environ.get("PROBLEM_SOLVER_WATCH_BOTS", "problem-solver-ui,polymarket-trader").split(",")

def now():
    return datetime.utcnow().isoformat() + "Z"

def run(cmd: list[str]) -> tuple[int, str]:
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

def ai_employee(*args: str) -> tuple[int, str]:
    return run([str(AI_HOME / "bin" / "ai-employee"), *args])

def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def main():
    print(f"[{now()}] problem-solver started; watching bots: {BOTS}; auto_restart={AUTO_RESTART}")
    while True:
        state = {"ts": now(), "bots": []}
        for bot in [b.strip() for b in BOTS if b.strip()]:
            ok = bot_running(bot)
            entry = {"bot": bot, "running": ok}
            if not ok and AUTO_RESTART:
                rc, out = ai_employee("start", bot)
                entry["action"] = "start"
                entry["action_rc"] = rc
                entry["action_out_tail"] = out[-800:]
            state["bots"].append(entry)

        write_state(state)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

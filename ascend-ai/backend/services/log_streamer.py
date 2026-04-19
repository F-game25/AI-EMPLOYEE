"""
ASCEND AI — Log Streamer
Tails log files from ~/.ai-employee/logs/ for real-time display.
"""

import os

AI_EMPLOYEE_DIR = os.path.expanduser("~/.ai-employee")
LOGS_DIR = os.path.join(AI_EMPLOYEE_DIR, "logs")


def get_log_tail(agent_name: str, lines: int = 50) -> dict:
    """Return the last N lines from an agent's log file."""
    log_path = os.path.join(LOGS_DIR, f"{agent_name}.log")
    if not os.path.exists(log_path):
        return {"agent": agent_name, "lines": [], "error": "Log file not found"}

    try:
        with open(log_path, "r", errors="replace") as f:
            all_lines = f.readlines()
        tail = [line.rstrip("\n") for line in all_lines[-lines:]]
        return {"agent": agent_name, "lines": tail}
    except Exception as e:
        return {"agent": agent_name, "lines": [], "error": str(e)}


def list_available_logs() -> list[str]:
    """Return names of agents that have log files."""
    if not os.path.isdir(LOGS_DIR):
        return []
    return [
        f.replace(".log", "")
        for f in os.listdir(LOGS_DIR)
        if f.endswith(".log")
    ]

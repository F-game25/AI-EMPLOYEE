"""
ASCEND AI — Process Wrapper
Manages start / stop of individual bot processes under ~/.ai-employee/bots/.
Never modifies the bot directories — only reads and launches.
"""

import os
import signal
import subprocess

AI_EMPLOYEE_DIR = os.path.expanduser("~/.ai-employee")

BOT_START_CMDS: dict[str, list[str]] = {
    "task-orchestrator":    ["python3", "main.py"],
    "company-builder":      ["python3", "main.py"],
    "hr-manager":           ["python3", "main.py"],
    "finance-wizard":       ["python3", "main.py"],
    "brand-strategist":     ["python3", "main.py"],
    "growth-hacker":        ["python3", "main.py"],
    "project-manager":      ["python3", "main.py"],
    "lead-hunter":          ["python3", "main.py"],
    "content-master":       ["python3", "main.py"],
    "social-guru":          ["python3", "main.py"],
    "intel-agent":          ["python3", "main.py"],
    "email-ninja":          ["python3", "main.py"],
    "support-bot":          ["python3", "main.py"],
    "data-analyst":         ["python3", "main.py"],
    "creative-studio":      ["python3", "main.py"],
    "web-sales":            ["python3", "main.py"],
    "skills-manager":       ["python3", "main.py"],
    "polymarket-trader":    ["python3", "main.py"],
    "mirofish-researcher":  ["python3", "main.py"],
    "discovery":            ["python3", "main.py"],
    "problem-solver":       ["python3", "main.py"],
    "problem-solver-ui":    ["python3", "server.py"],
}

_processes: dict[str, subprocess.Popen] = {}


def start_bot(name: str) -> dict:
    """Launch a bot subprocess. Returns success/failure dict."""
    bot_dir = os.path.join(AI_EMPLOYEE_DIR, "bots", name)
    if not os.path.exists(bot_dir):
        return {"success": False, "error": f"Bot dir not found: {bot_dir}"}

    cmd = BOT_START_CMDS.get(name, ["python3", "main.py"])
    log_dir = os.path.join(AI_EMPLOYEE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{name}.log")

    try:
        with open(log_path, "a") as log_file:
            p = subprocess.Popen(
                cmd,
                cwd=bot_dir,
                stdout=log_file,
                stderr=log_file,
                shell=False,
            )
        _processes[name] = p
        return {"success": True, "pid": p.pid}
    except Exception as e:
        return {"success": False, "error": str(e)}


def stop_bot(name: str) -> dict:
    """Gracefully stop a running bot process."""
    p = _processes.get(name)
    if not p:
        return {"success": False, "error": "Not running"}
    try:
        os.kill(p.pid, signal.SIGTERM)
        del _processes[name]
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_pid(name: str):
    """Return the PID if the bot is still running, else None."""
    p = _processes.get(name)
    return p.pid if p and p.poll() is None else None

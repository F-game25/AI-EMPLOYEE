"""
ASCEND AI — Log Streamer
Tails log files from ~/.ai-employee/logs/ and broadcasts new lines.
"""

import asyncio
import os
from collections import deque

AI_EMPLOYEE_DIR = os.path.expanduser("~/.ai-employee")
_buffers: dict[str, deque] = {}  # name -> deque(maxlen=500)


async def tail_logs_forever(broadcast_fn):
    """Background loop — reads new log lines and broadcasts them."""
    log_dir = os.path.join(AI_EMPLOYEE_DIR, "logs")
    if not os.path.exists(log_dir):
        return
    while True:
        for fname in os.listdir(log_dir):
            if not fname.endswith(".log"):
                continue
            bot_name = fname.replace(".log", "")
            path = os.path.join(log_dir, fname)
            if bot_name not in _buffers:
                _buffers[bot_name] = deque(maxlen=500)
            try:
                with open(path, "r", errors="replace") as f:
                    lines = f.readlines()[-10:]
                    for line in lines:
                        line = line.strip()
                        if line and line not in _buffers[bot_name]:
                            _buffers[bot_name].append(line)
                            await broadcast_fn({
                                "type": "log_line",
                                "data": {"bot": bot_name, "message": line},
                            })
            except Exception:
                pass
        await asyncio.sleep(2)


def get_logs(bot_name: str, lines: int = 100) -> list[str]:
    """Return the last N buffered log lines for a bot."""
    buf = _buffers.get(bot_name, deque())
    return list(buf)[-lines:]

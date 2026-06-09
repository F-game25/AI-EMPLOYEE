"""File operations tool implementations.

read_file: risk 0 — read any accessible path (up to 50 KB)
write_file: risk 1 — write/create files
list_dir: risk 0 — list directory entries
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("tools.file_ops")

_MAX_READ_BYTES = 50_000


def read_file(path: str, encoding: str = "utf-8", **_) -> dict:
    if not os.path.isfile(path):
        return {"content": None, "ok": False, "error": f"Not a file: {path}"}
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding=encoding, errors="replace") as f:
            content = f.read(_MAX_READ_BYTES)
        return {"content": content, "ok": True, "path": path, "truncated": size > _MAX_READ_BYTES}
    except Exception as exc:
        return {"content": None, "ok": False, "error": str(exc)}


def write_file(path: str, content: str, encoding: str = "utf-8", **_) -> dict:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return {"ok": True, "path": path, "bytes_written": len(content.encode(encoding))}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def list_dir(path: str, **_) -> dict:
    if not os.path.isdir(path):
        return {"entries": [], "ok": False, "error": f"Not a directory: {path}"}
    try:
        entries = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            entries.append({"name": name, "type": "dir" if os.path.isdir(full) else "file"})
        return {"entries": entries, "ok": True, "path": path}
    except Exception as exc:
        return {"entries": [], "ok": False, "error": str(exc)}

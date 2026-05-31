"""Append-only JSONL writer used for reasoning traces and event logs."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_LOCKS: dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    if key not in _LOCKS:
        _LOCKS[key] = threading.Lock()
    return _LOCKS[key]


def append(path: Path | str, record: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _lock_for(p):
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def read_all(path: Path | str, *, limit: int | None = None) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    if limit is not None and limit > 0:
        out = out[-limit:]
    return out

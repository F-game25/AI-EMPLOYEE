"""JSONL replay recorder — action log + screenshot archive."""
from __future__ import annotations
import json
import logging
import os
import re
import hashlib
import time
from pathlib import Path
from typing import Optional

from .schema import ActionResult, ReplayFrame

logger = logging.getLogger(__name__)

_BASE = Path(os.path.expanduser("~/.ai-employee"))
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_SAFE_SCREENSHOT_KEY = re.compile(r"^screenshots/([0-9]{5})\.png$")


def _safe_component(value: str, label: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _session_dir(tenant_id: str, session_id: str) -> Path:
    root = os.path.realpath(_BASE / "tenants")
    tenant = _safe_component(tenant_id, "tenant_id")
    session = _safe_component(session_id, "session_id")
    session_key = hashlib.sha256(f"{tenant}:{session}".encode("utf-8")).hexdigest()[:32]
    d = os.path.realpath(os.path.join(
        root,
        "sessions",
        session_key[:2],
        session_key,
        "rpa",
    ))
    if os.path.commonpath([root, d]) != root:
        raise ValueError("session path escapes tenant root")
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


class ReplayRecorder:
    def __init__(self, tenant_id: str, session_id: str):
        self._dir = _session_dir(tenant_id, session_id)
        self._log = self._dir / "replay.jsonl"
        self._frame = 0

    def record(self, result: ActionResult, screenshot: Optional[bytes] = None) -> ReplayFrame:
        key = None
        if screenshot:
            key = f"screenshots/{self._frame:05d}.png"
            shot_path = self._dir / key
            shot_path.parent.mkdir(exist_ok=True)
            shot_path.write_bytes(screenshot)

        frame = ReplayFrame(
            frame_idx=self._frame,
            ts=result.ts,
            action_type=result.action.value if hasattr(result.action, "value") else str(result.action),
            selector=result.selector,
            value=None,
            before_hash=result.before_hash,
            after_hash=result.after_hash,
            screenshot_key=key,
            ok=result.ok,
            error=result.error,
        )
        with open(self._log, "a") as f:
            f.write(json.dumps(frame.__dict__) + "\n")
        self._frame += 1
        return frame

    def read_frames(self) -> list[ReplayFrame]:
        if not self._log.exists():
            return []
        frames = []
        with open(self._log) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    frames.append(ReplayFrame(**d))
                except Exception:
                    pass
        return frames

    def screenshot_bytes(self, key: str) -> Optional[bytes]:
        match = _SAFE_SCREENSHOT_KEY.fullmatch(key)
        if not match:
            return None
        safe_key = f"screenshots/{int(match.group(1)):05d}.png"
        root = os.path.realpath(self._dir)
        p = os.path.realpath(os.path.join(root, safe_key))
        if os.path.commonpath([root, p]) != root:
            return None
        p = Path(p)
        return p.read_bytes() if p.exists() else None

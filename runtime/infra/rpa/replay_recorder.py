"""JSONL replay recorder — action log + screenshot archive."""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from .schema import ActionResult, ReplayFrame

logger = logging.getLogger(__name__)

_BASE = Path(os.path.expanduser("~/.ai-employee"))


def _session_dir(tenant_id: str, session_id: str) -> Path:
    d = _BASE / "tenants" / tenant_id / "rpa" / "sessions" / session_id
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
        p = self._dir / key
        return p.read_bytes() if p.exists() else None

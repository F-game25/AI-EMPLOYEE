"""video_render — atomic tool: render an HTML composition to an MP4 via HeyGen
HyperFrames (https://github.com/heygen-com/hyperframes).

The agent composes a video AS HTML/CSS (which LLMs are good at); this tool renders
it deterministically to MP4 for the content/ads pipeline (money_mode).

Input::

    {"html": "<!doctype html>...", "name": "promo", "dry_run": false}

Output::

    {"status": "rendered|planned|not_available|disabled|error", "mp4_path"?, "reason"?}

SECURITY (this runs an external CLI + a headless browser, so deny-by-default):
  - Feature flag VIDEO_RENDER_ENABLED=1 required (off by default).
  - HTML is UNTRUSTED data: size-capped, written to a fresh per-render temp dir
    inside the artifacts tree (no path traversal), never executed by us.
  - The CLI is invoked via argv (no shell) with a hard timeout and cwd confined to
    that temp dir — no shell-metacharacter injection, no arbitrary path access.
  - If hyperframes isn't installed we return 'not_available' (never crash, never
    auto-install — that stays an explicit owner action).
  - Output MP4 lands in state/artifacts/ for the existing artifact surface.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .registry import register_tool

_MAX_HTML_BYTES = int(os.getenv("VIDEO_RENDER_MAX_HTML_BYTES", "2000000"))  # 2MB
_RENDER_TIMEOUT_S = int(os.getenv("VIDEO_RENDER_TIMEOUT_S", "180"))


def _enabled() -> bool:
    return os.getenv("VIDEO_RENDER_ENABLED") == "1"


def _state_dir() -> Path:
    base = os.getenv("STATE_DIR") or os.path.join(os.path.expanduser("~"), ".ai-employee", "state")
    return Path(base)


def _artifacts_dir() -> Path:
    d = _state_dir() / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hyperframes_available() -> bool:
    # `npx hyperframes` needs npx on PATH; the package resolves at run time.
    return shutil.which("npx") is not None


def _call(input_data: dict[str, Any]) -> dict[str, Any]:
    html = input_data.get("html")
    if not isinstance(html, str) or not html.strip():
        return {"status": "error", "error": "html is required"}
    if len(html.encode("utf-8", "ignore")) > _MAX_HTML_BYTES:
        return {"status": "error", "error": f"html exceeds {_MAX_HTML_BYTES} bytes"}

    name = "".join(c for c in str(input_data.get("name") or "video") if c.isalnum() or c in "-_")[:40] or "video"
    render_id = f"{name}-{uuid.uuid4().hex[:8]}"
    out_name = f"{render_id}.mp4"
    out_path = _artifacts_dir() / out_name

    # Fresh isolated work dir per render (auto-cleaned). HTML is written here only.
    work = Path(tempfile.mkdtemp(prefix="hyperframes-", dir=str(_artifacts_dir())))
    index = work / "index.html"
    index.write_text(html, encoding="utf-8")

    plan = {"render_id": render_id, "out_path": str(out_path), "html_bytes": len(html), "engine": "hyperframes"}

    # Dry-run: validate + plan without invoking the renderer (safe default for tests/CI).
    if input_data.get("dry_run"):
        shutil.rmtree(work, ignore_errors=True)
        return {"status": "planned", "plan": plan, "note": "dry_run: HTML validated, nothing rendered"}

    if not _enabled():
        shutil.rmtree(work, ignore_errors=True)
        return {"status": "disabled", "reason": "VIDEO_RENDER_ENABLED != 1 (rendering is off by default)", "plan": plan}

    if not _hyperframes_available():
        shutil.rmtree(work, ignore_errors=True)
        return {"status": "not_available",
                "reason": "npx/hyperframes not found — install with: npm i -g hyperframes (owner action)",
                "plan": plan}

    try:
        # argv form (no shell) → no metacharacter injection. cwd confined to `work`.
        proc = subprocess.run(
            ["npx", "--yes", "hyperframes", "render", "--output", str(out_path)],
            cwd=str(work), capture_output=True, text=True, timeout=_RENDER_TIMEOUT_S,
            env={**os.environ, "CI": "1"},
        )
        if proc.returncode == 0 and out_path.exists():
            return {"status": "rendered", "mp4_path": str(out_path), "render_id": render_id,
                    "artifact": out_name, "bytes": out_path.stat().st_size}
        return {"status": "error", "error": f"render exit {proc.returncode}",
                "detail": (proc.stderr or proc.stdout or "")[-400:], "plan": plan}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"render timed out after {_RENDER_TIMEOUT_S}s", "plan": plan}
    except Exception as e:  # noqa: BLE001 — tool must never raise into the caller
        return {"status": "error", "error": str(e), "plan": plan}
    finally:
        shutil.rmtree(work, ignore_errors=True)


register_tool(
    name="video_render",
    description="Render an HTML/CSS video composition to MP4 via HeyGen HyperFrames (local, deterministic). "
                "Feature-flagged (VIDEO_RENDER_ENABLED); degrades to planned/not_available safely.",
    call=_call,
    input_schema={
        "type": "object",
        "properties": {
            "html": {"type": "string", "description": "Full HTML document for the HyperFrames composition"},
            "name": {"type": "string", "description": "Artifact name prefix (sanitized)"},
            "dry_run": {"type": "boolean", "description": "Validate + plan without rendering"},
        },
        "required": ["html"],
    },
    output_schema={"type": "object"},
    tags=["media", "video", "content", "money_mode"],
)

"""write_file — atomic tool that writes text content to an allowed output directory.

Input::

    {"filename": "report.txt", "content": "...", "subdir": "output"}

Output::

    {"status": "ok", "path": "...", "bytes_written": 123}

Only writes inside the two allowed output dirs to prevent path traversal:
  - state/artifacts/   (generated files: HTML, reports, etc.)
  - state/output/      (general output files)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .registry import register_tool

logger = logging.getLogger(__name__)

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_ALLOWED_ROOTS = (
    AI_HOME / "state" / "artifacts",
    AI_HOME / "state" / "output",
)


def _resolve_safe_path(filename: str, subdir: str) -> Path:
    """Return an absolute path inside an allowed root, raising on traversal."""
    # Pick root based on subdir hint; default to artifacts
    if subdir and "output" in subdir.lower():
        root = AI_HOME / "state" / "output"
    else:
        root = AI_HOME / "state" / "artifacts"

    # Strip any directory components from filename to prevent traversal
    safe_name = Path(filename).name
    if not safe_name:
        raise ValueError("filename must not be empty after sanitising")

    resolved = (root / safe_name).resolve()
    # Double-check the resolved path is still under the chosen root
    if not str(resolved).startswith(str(root.resolve())):
        raise ValueError(f"path traversal detected: {filename!r}")

    return resolved


def _call(input_data: dict[str, Any]) -> dict[str, Any]:
    filename = str(input_data.get("filename") or "").strip()
    content  = str(input_data.get("content") or "")
    subdir   = str(input_data.get("subdir") or "")

    if not filename:
        return {"status": "error", "error": "filename is required"}

    try:
        target = _resolve_safe_path(filename, subdir)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.info("write_file: wrote %d bytes → %s", len(content), target)
        return {"status": "ok", "path": str(target), "bytes_written": len(content.encode("utf-8"))}
    except Exception as exc:
        logger.warning("write_file failed: %s", exc)
        return {"status": "error", "error": str(exc)}


register_tool(
    name="write_file",
    description=(
        "Write text content to a file in the allowed output directory "
        "(state/artifacts/ or state/output/). "
        "Input: filename, content, subdir (optional: 'artifacts'|'output'). "
        "Returns path and bytes_written."
    ),
    call=_call,
    input_schema={
        "type": "object",
        "required": ["filename", "content"],
        "properties": {
            "filename": {"type": "string", "description": "File name (no path components)"},
            "content":  {"type": "string", "description": "Text content to write"},
            "subdir":   {"type": "string", "description": "'artifacts' (default) or 'output'"},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "status":        {"type": "string"},
            "path":          {"type": "string"},
            "bytes_written": {"type": "integer"},
            "error":         {"type": "string"},
        },
    },
    tags=["file", "write", "output"],
)

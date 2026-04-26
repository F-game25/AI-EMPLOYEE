"""Artifact manager — generate downloadable files from AI response content.

Extracts code blocks and produces a Markdown summary for every response.
Files are saved to state/artifacts/ and served via /api/artifacts/:filename.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

_ARTIFACTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "state", "artifacts")
)

_LANG_EXT: dict[str, str] = {
    "python": "py", "py": "py",
    "javascript": "js", "js": "js",
    "typescript": "ts", "ts": "ts",
    "bash": "sh", "sh": "sh",
    "json": "json",
    "sql": "sql",
    "yaml": "yaml", "yml": "yaml",
    "html": "html",
    "css": "css",
}


def _ensure_dir() -> str:
    os.makedirs(_ARTIFACTS_DIR, exist_ok=True)
    return _ARTIFACTS_DIR


def _slug(text: str, max_len: int = 20) -> str:
    return re.sub(r"[^\w]", "_", text or "output")[:max_len].strip("_")


def generate_artifacts(
    response: str,
    intent: str,
    user_input: str,
    *,
    max_code_files: int = 3,
) -> list[dict[str, str]]:
    """Extract code blocks + summary from *response*, write to disk.

    Returns a list of dicts: {name, type, path} — ready for WorkflowFormatter.
    """
    artifacts: list[dict[str, str]] = []
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = _slug(intent)
    base = _ensure_dir()

    # Extract fenced code blocks ```lang\ncontent```
    code_blocks = re.findall(r"```(\w*)\n(.*?)```", response, re.DOTALL)
    for i, (lang, code) in enumerate(code_blocks[:max_code_files]):
        ext = _LANG_EXT.get(lang.lower(), "txt")
        fname = f"code_{slug}_{ts}_{i}.{ext}"
        fpath = os.path.join(base, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(code.strip())
        artifacts.append({"name": fname, "type": f"Code ({lang or 'text'})", "path": fpath})

    # Always generate a Markdown summary
    summary_fname = f"summary_{slug}_{ts}.md"
    summary_path = os.path.join(base, summary_fname)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# Summary: {intent}\n\n**Query:** {user_input[:500]}\n\n{response}")
    artifacts.append({"name": summary_fname, "type": "Summary (Markdown)", "path": summary_path})

    return artifacts


def list_artifacts() -> list[dict[str, Any]]:
    """Return metadata for all artifacts in the artifacts directory."""
    base = _ensure_dir()
    result = []
    for fname in sorted(os.listdir(base), reverse=True):
        fpath = os.path.join(base, fname)
        if os.path.isfile(fpath):
            result.append({
                "name": fname,
                "size": os.path.getsize(fpath),
                "modified": os.path.getmtime(fpath),
                "url": f"/api/artifacts/{fname}",
            })
    return result

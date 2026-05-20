"""Artifact manager — central store for all system outputs.

ALL outputs (agent results, forge builds, analysis) must go through
create_artifact() so they get a canonical id, provenance, and emit
nb:artifact_created on the event bus.

Schema per artifact:
  id          — uuid4 (stable reference)
  type        — "code" | "summary" | "forge_build" | "analysis" | "file"
  source      — which subsystem created it ("agent:X" | "forge" | "pipeline" | ...)
  version     — semver string from state/version.json (defaults to "0.0.0")
  parent_id   — optional id of the artifact this was derived from
  timestamp   — unix epoch (int)
  name        — filename
  path        — absolute path on disk
  size        — bytes
  url         — /api/artifacts/<name>
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ARTIFACTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "state", "artifacts")
)
_VERSION_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "state", "version.json")
)

_LANG_EXT: dict[str, str] = {
    "python": "py", "py": "py",
    "javascript": "js", "js": "js",
    "typescript": "ts", "ts": "ts",
    "bash": "sh", "sh": "sh",
    "json": "json", "sql": "sql",
    "yaml": "yaml", "yml": "yaml",
    "html": "html", "css": "css",
}


def _ensure_dir() -> str:
    os.makedirs(_ARTIFACTS_DIR, exist_ok=True)
    return _ARTIFACTS_DIR


def _slug(text: str, max_len: int = 20) -> str:
    return re.sub(r"[^\w]", "_", text or "output")[:max_len].strip("_")


def _system_version() -> str:
    try:
        data = json.loads(Path(_VERSION_PATH).read_text())
        return data.get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _make_meta(
    *,
    name: str,
    artifact_type: str,
    source: str,
    path: str,
    parent_id: str | None = None,
) -> dict:
    ts = int(time.time())
    return {
        "id": str(uuid.uuid4()),
        "type": artifact_type,
        "source": source,
        "version": _system_version(),
        "parent_id": parent_id,
        "timestamp": ts,
        "created_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "name": name,
        "path": path,
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
        "url": f"/api/artifacts/{name}",
    }


def _emit(artifacts: list[dict]) -> None:
    try:
        from neural_brain.api.node_bridge import emit
        emit("nb:artifact_created", {
            "artifacts": [
                {"id": a["id"], "name": a["name"], "type": a["type"], "source": a["source"]}
                for a in artifacts
            ],
        })
    except Exception:
        pass


def create_artifact(
    content: str | bytes,
    *,
    name: str,
    artifact_type: str = "file",
    source: str = "system",
    parent_id: str | None = None,
    encoding: str = "utf-8",
) -> dict:
    """Write one artifact to disk and return its full metadata dict.

    This is the single canonical way to persist any system output.
    """
    base = _ensure_dir()
    fpath = os.path.join(base, name)
    if isinstance(content, bytes):
        with open(fpath, "wb") as f:
            f.write(content)
    else:
        with open(fpath, "w", encoding=encoding) as f:
            f.write(content)
    meta = _make_meta(name=name, artifact_type=artifact_type, source=source, path=fpath, parent_id=parent_id)
    _emit([meta])
    return meta


def generate_artifacts(
    response: str,
    intent: str,
    user_input: str,
    *,
    source: str = "pipeline",
    parent_id: str | None = None,
    max_code_files: int = 3,
) -> list[dict]:
    """Extract code blocks + summary from *response*, write to disk via create_artifact().

    Returns list of artifact metadata dicts.
    """
    artifacts: list[dict] = []
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = _slug(intent)

    # Code blocks
    code_blocks = re.findall(r"```(\w*)\n(.*?)```", response, re.DOTALL)
    for i, (lang, code) in enumerate(code_blocks[:max_code_files]):
        ext = _LANG_EXT.get(lang.lower(), "txt")
        name = f"code_{slug}_{ts}_{i}.{ext}"
        meta = create_artifact(
            code.strip(),
            name=name,
            artifact_type="code",
            source=source,
            parent_id=parent_id,
        )
        artifacts.append(meta)

    # Summary always
    summary_name = f"summary_{slug}_{ts}.md"
    summary_content = f"# Summary: {intent}\n\n**Query:** {user_input[:500]}\n\n{response}"
    meta = create_artifact(
        summary_content,
        name=summary_name,
        artifact_type="summary",
        source=source,
        parent_id=parent_id,
    )
    artifacts.append(meta)

    return artifacts


def _infer_type(fname: str) -> str:
    if fname.startswith("summary_"):
        return "summary"
    if fname.startswith("code_"):
        ext = fname.rsplit(".", 1)[-1]
        return f"code:{ext}"
    if fname.startswith("forge_"):
        return "forge_build"
    return "file"


def list_artifacts(limit: int = 200) -> list[dict]:
    """Return metadata for all artifacts, newest first."""
    base = _ensure_dir()
    result = []
    try:
        files = sorted(
            (f for f in os.listdir(base) if os.path.isfile(os.path.join(base, f))),
            key=lambda f: os.path.getmtime(os.path.join(base, f)),
            reverse=True,
        )
        for fname in files[:limit]:
            fpath = os.path.join(base, fname)
            result.append({
                "id": None,       # legacy files have no id; new ones do via create_artifact
                "type": _infer_type(fname),
                "source": "unknown",
                "version": "0.0.0",
                "parent_id": None,
                "timestamp": int(os.path.getmtime(fpath)),
                "created_at": datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "name": fname,
                "path": fpath,
                "size": os.path.getsize(fpath),
                "url": f"/api/artifacts/{fname}",
            })
    except Exception:
        pass
    return result

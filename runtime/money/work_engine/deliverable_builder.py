"""Deliverable builder — produces the actual work product.

For content/writing categories it routes through the EXISTING money_mode
``content_publish_track`` pipeline (imported read-only) so we reuse the real
content factory + its artifact/logging. For everything else it generates the
artifact via the engine LLM. Always saves a real file under the state dir and
returns its path + a summary.

build(opportunity) -> {
    ok: bool,
    artifact_path: str|None,
    summary: str,
    method: 'content_pipeline'|'llm'|'template',
    bytes: int,
}

Never raises; never fabricates success — if no artifact was written, ok=False.
Producing a deliverable is NOT delivering it (delivery is HITL-gated upstream).
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

_CONTENT_CATEGORIES = {"content", "writing"}


def _state_dir() -> Path:
    try:
        from core.state_paths import canonical_state_dir
        base = canonical_state_dir()
    except Exception:
        base = Path(__file__).resolve().parents[3] / "state"
    out = base / "work_deliverables"
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return out


def _write_artifact(opp_id: str, title: str, body: str) -> tuple[str | None, int]:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40] or "deliverable"
    path = _state_dir() / f"{ts}_{opp_id}_{safe}.md"
    try:
        path.write_text(body, encoding="utf-8")
        return str(path), len(body.encode("utf-8"))
    except Exception:
        return None, 0


def _via_content_pipeline(opp: dict[str, Any]) -> dict[str, Any] | None:
    """Reuse the existing money_mode content factory (read-only import)."""
    try:
        from core.money_mode import get_money_mode
    except Exception:
        return None
    try:
        mm = get_money_mode()
        topic = opp.get("title") or opp.get("description") or "work deliverable"
        result = mm.content_publish_track(topic=str(topic), platform="blog", content_type="article")
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    artifact_path = (
        result.get("file_path") or result.get("path") or result.get("artifact_path")
    )
    if not artifact_path:
        return None
    size = 0
    try:
        size = Path(artifact_path).stat().st_size
    except Exception:
        pass
    return {
        "ok": True,
        "artifact_path": str(artifact_path),
        "summary": f"Content draft produced via money_mode content pipeline for '{topic}'.",
        "method": "content_pipeline",
        "bytes": size,
    }


def _via_llm(opp: dict[str, Any], opp_id: str) -> dict[str, Any]:
    title = str(opp.get("title") or "Work deliverable")
    desc = str(opp.get("description") or "")
    category = str(opp.get("category") or "general")
    body = ""
    method = "template"
    try:
        from engine.api import generate
        prompt = (
            f"Produce a complete, client-ready work deliverable in markdown.\n"
            f"Title: {title}\nCategory: {category}\nRequirements: {desc}\n\n"
            "Be concrete and well-structured. Do not include placeholders."
        )
        out = generate(
            prompt=prompt,
            system="You are a senior delivery specialist producing real, finished work.",
            timeout=90,
        )
        if isinstance(out, str) and out.strip():
            body = out.strip()
            method = "llm"
    except Exception:
        body = ""

    if not body:
        # Honest offline fallback — a real (if minimal) artifact, clearly marked.
        body = (
            f"# {title}\n\n"
            f"_Category: {category}_\n\n"
            f"## Requirements\n\n{desc or '(none provided)'}\n\n"
            "## Status\n\n"
            "Draft scaffold generated offline (LLM backend unavailable at build time). "
            "Requires completion before delivery.\n"
        )
        method = "template"

    path, size = _write_artifact(opp_id, title, body)
    if not path:
        return {
            "ok": False, "artifact_path": None,
            "summary": "Failed to write deliverable artifact to disk.",
            "method": method, "bytes": 0,
        }
    return {
        "ok": True,
        "artifact_path": path,
        "summary": f"Deliverable built ({method}) and saved for '{title}'.",
        "method": method,
        "bytes": size,
    }


def build(opportunity: dict[str, Any] | None) -> dict[str, Any]:
    """Build the deliverable artifact for an opportunity. Never raises."""
    try:
        opp = dict(opportunity or {})
        opp_id = str(opp.get("id") or f"opp-{uuid.uuid4().hex[:8]}")
        category = str(opp.get("category") or "general").lower()

        if category in _CONTENT_CATEGORIES:
            piped = _via_content_pipeline(opp)
            if piped and piped.get("ok"):
                return piped
            # Fall through to LLM if the pipeline could not produce an artifact.
        return _via_llm(opp, opp_id)
    except Exception as exc:  # pragma: no cover — defensive
        return {
            "ok": False, "artifact_path": None,
            "summary": f"deliverable_build_error: {exc}",
            "method": "error", "bytes": 0,
        }

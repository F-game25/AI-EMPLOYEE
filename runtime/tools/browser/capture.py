"""Page capture — screenshots (PNG) / PDFs to a rotated capture directory."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

CAPTURE_DIR = Path.home() / ".ai-employee" / "state" / "browser_captures"
KEEP_NEWEST = 40


def capture(session, kind: str = "screenshot") -> dict[str, Any]:
    """Capture the session's page → {ok, kind, path}.

    kind ∈ screenshot (PNG, full page) | pdf (where chromium supports it).
    Keeps the newest ``KEEP_NEWEST`` files in ``CAPTURE_DIR``.
    """
    kind = (kind or "screenshot").strip().lower()
    if kind not in ("screenshot", "pdf"):
        return {"ok": False, "kind": kind, "path": None,
                "detail": "unsupported kind (screenshot | pdf)"}
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ext = "pdf" if kind == "pdf" else "png"
    path = CAPTURE_DIR / f"{session.id}-{stamp}.{ext}"

    def job() -> None:
        if kind == "pdf":
            session.page.pdf(path=str(path))
        else:
            session.page.screenshot(path=str(path), full_page=True)

    try:
        session.call(job)
    except Exception as exc:
        return {"ok": False, "kind": kind, "path": None, "detail": str(exc)}
    _rotate()
    return {"ok": True, "kind": kind, "path": str(path)}


def _rotate() -> None:
    """Best-effort: delete everything but the newest ``KEEP_NEWEST`` captures."""
    try:
        files = sorted((p for p in CAPTURE_DIR.iterdir() if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[KEEP_NEWEST:]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass

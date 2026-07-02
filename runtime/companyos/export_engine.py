"""ExportEngine — full local ownership (anti-Polsia: no lock-in).

Packages a company's complete state (brief, validation, refinement, roadmap,
decisions, metrics, artifact references) into a portable JSON bundle the owner can
take anywhere. Local is the source of truth.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


def _state_dir() -> Path:
    try:
        from core.state_paths import canonical_state_dir
        return canonical_state_dir()
    except Exception:  # noqa: BLE001 — never repo-local ./state (C0); mirror canonical default
        return Path.home() / ".ai-employee" / "state"


class ExportEngine:
    def export(self, company: dict) -> dict:
        """Write a portable bundle for a company and return its path + summary."""
        if not company or not company.get("id"):
            return {"ok": False, "error": "company required"}
        cid = company["id"]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = _state_dir() / "company_exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle = {
            "exported_at": ts,
            "ownership": "local — you own this fully; no lock-in, no take-rate",
            "company": company,
            "includes": ["brief", "validation", "refinement", "roadmap",
                         "decisions", "metrics", "artifacts"],
        }
        path = out_dir / f"{cid}_{ts}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(path)
        return {"ok": True, "company_id": cid, "export_path": str(path),
                "artifact_count": len(company.get("artifacts") or []),
                "note": "Full local export — portable, owner-controlled."}


_instance: ExportEngine | None = None
_instance_lock = threading.Lock()


def get_export_engine() -> ExportEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ExportEngine()
    return _instance

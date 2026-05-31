"""Export & Backup Agent — system state export and backup management.

Exports leads, tasks, revenue, and activity data as CSV/JSON.
Creates dated backup archives with integrity checksums.

Commands (via chat):
  export leads   — export CRM leads as CSV-formatted text
  export tasks   — export tasks with status and timestamps
  export revenue — export invoice/revenue data
  backup create  — create full system state backup
  backup restore — list available backups for restore
"""
from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
BACKUPS_DIR = AI_HOME / "backups"

STATE_FILES = {
    "leads": "lead-generator-crm.json",
    "deals": "deals.json",
    "tasks": "tasks.json",
    "invoices": "invoices.json",
    "tickets": "support-tickets.json",
    "workflows": "workflows.json",
}


class ExportBackupAgent(BaseAgent):
    agent_id = "export-backup"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        action = payload.get("action") or payload.get("task", "export")
        export_type = payload.get("type", "all")

        if "backup" in action.lower():
            return self._create_backup()
        return self._export_data(export_type)

    def _export_data(self, export_type: str) -> dict:
        result = {"export_type": export_type, "exported_at": datetime.now(timezone.utc).isoformat(), "files": {}}

        targets = STATE_FILES if export_type == "all" else {export_type: STATE_FILES.get(export_type, "")}

        for key, fname in targets.items():
            fpath = STATE_DIR / fname
            if not fpath.exists():
                result["files"][key] = {"status": "not_found", "records": 0}
                continue
            try:
                data = json.loads(fpath.read_text())
                records = len(data) if isinstance(data, list) else 1
                if isinstance(data, list) and records > 0:
                    headers = list(data[0].keys()) if isinstance(data[0], dict) else []
                    csv_lines = [",".join(headers)]
                    for row in data[:500]:
                        if isinstance(row, dict):
                            csv_lines.append(",".join(str(row.get(h, "")).replace(",", ";") for h in headers))
                    result["files"][key] = {
                        "status": "ok",
                        "records": records,
                        "csv_preview": "\n".join(csv_lines[:10]),
                        "full_csv": "\n".join(csv_lines),
                    }
                else:
                    result["files"][key] = {"status": "ok", "records": records, "data": data}
            except Exception as e:
                result["files"][key] = {"status": "error", "error": str(e)}

        result["total_records"] = sum(f.get("records", 0) for f in result["files"].values())
        result["tokens_used"] = 0
        return result

    def _create_backup(self) -> dict:
        ts = datetime.now(timezone.utc)
        backup_name = f"backup-{ts.strftime('%Y%m%d-%H%M%S')}"
        backup_dir = BACKUPS_DIR / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)

        manifest = {"created_at": ts.isoformat(), "files": {}}
        for key, fname in STATE_FILES.items():
            fpath = STATE_DIR / fname
            if fpath.exists():
                content = fpath.read_bytes()
                checksum = hashlib.sha256(content).hexdigest()[:16]
                dest = backup_dir / fname
                dest.write_bytes(content)
                manifest["files"][key] = {"file": fname, "checksum": checksum, "size_bytes": len(content)}

        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        return {
            "backup_name": backup_name,
            "backup_path": str(backup_dir),
            "files_backed_up": len(manifest["files"]),
            "manifest": manifest,
            "tokens_used": 0,
        }

"""RollbackManager — snapshot-before-deploy, diff-based restore."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
_SNAPSHOT_ROOT = Path(os.path.expanduser("~/.ai-employee/snapshots"))


class RollbackManager:
    def snapshot(self, service: str, source_dir: str) -> dict:
        """Archive source_dir as a timestamped snapshot. Returns manifest."""
        ts = int(time.time())
        snap_id = f"{service}_{ts}"
        dest = _SNAPSHOT_ROOT / service / snap_id
        dest.mkdir(parents=True, exist_ok=True)
        src = Path(source_dir)
        if not src.exists():
            return {"ok": False, "error": "source_not_found"}

        file_hashes = {}
        for fp in src.rglob("*"):
            if fp.is_file():
                rel = str(fp.relative_to(src))
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fp, target)
                file_hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()[:12]

        manifest = {"snap_id": snap_id, "service": service, "ts": ts,
                    "source": source_dir, "files": file_hashes}
        (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
        logger.info("Snapshot %s created (%d files)", snap_id, len(file_hashes))
        return {"ok": True, "snap_id": snap_id, "ts": ts, "file_count": len(file_hashes)}

    def list_snapshots(self, service: str) -> list[dict]:
        svc_dir = _SNAPSHOT_ROOT / service
        if not svc_dir.exists():
            return []
        snaps = []
        for d in sorted(svc_dir.iterdir(), reverse=True):
            mf = d / "MANIFEST.json"
            if mf.exists():
                try:
                    m = json.loads(mf.read_text())
                    snaps.append({"snap_id": m["snap_id"], "ts": m["ts"],
                                  "file_count": len(m.get("files", {}))})
                except Exception:
                    pass
        return snaps

    def restore(self, service: str, snap_id: str, target_dir: str) -> dict:
        snap_dir = _SNAPSHOT_ROOT / service / snap_id
        if not snap_dir.exists():
            return {"ok": False, "error": "snapshot_not_found"}
        target = Path(target_dir)
        try:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(str(snap_dir), str(target),
                            ignore=shutil.ignore_patterns("MANIFEST.json"))
            logger.info("Restored %s from snapshot %s → %s", service, snap_id, target_dir)
            return {"ok": True, "snap_id": snap_id, "target": target_dir}
        except Exception as e:
            return {"ok": False, "error": str(e)}


_rm: Optional[RollbackManager] = None


def get_rollback_manager() -> RollbackManager:
    global _rm
    if _rm is None:
        _rm = RollbackManager()
    return _rm

"""Export & Backup System — JSON/CSV export, full ZIP backups."""
import csv
import io
import json
import time
import zipfile
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/api/export", tags=["export"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_BACKUP_DIR = Path.home() / ".ai-employee" / "backups"
_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILES: dict[str, str] = {
    "crm": "crm.json",
    "email_marketing": "email_marketing.json",
    "social_media": "social_media.json",
    "finance": "finance.json",
    "meetings": "meetings.json",
    "workflows": "workflows.json",
    "team": "team.json",
    "support": "support.json",
    "competitors": "competitors.json",
    "personal_brand": "personal_brand.json",
    "health_checks": "health_checks.json",
    "briefings": "briefings.json",
    "websites": "websites.json",
}


def _read_state(fname: str) -> dict:
    p = _HOME / fname
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


@router.get("/modules")
def list_modules():
    available = []
    for key, fname in STATE_FILES.items():
        p = _HOME / fname
        available.append({
            "key": key,
            "file": fname,
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else 0,
        })
    return JSONResponse(available)


@router.get("/json/{module}")
def export_json(module: str):
    if module not in STATE_FILES:
        return JSONResponse({"error": "unknown module"}, status_code=404)
    data = _read_state(STATE_FILES[module])
    content = json.dumps(data, indent=2).encode()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={
            "Content-Disposition":
                f"attachment; filename={module}_{time.strftime('%Y%m%d')}.json"
        },
    )


@router.get("/csv/{module}/{collection}")
def export_csv(module: str, collection: str):
    if module not in STATE_FILES:
        return JSONResponse({"error": "unknown module"}, status_code=404)
    data = _read_state(STATE_FILES[module])
    items = data.get(collection, [])
    if not items or not isinstance(items, list) or not isinstance(items[0], dict):
        return JSONResponse({"error": "no data or unsupported format"}, status_code=404)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(items[0].keys()))
    writer.writeheader()
    writer.writerows(items)
    content = output.getvalue().encode()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f"attachment; filename={module}_{collection}_{time.strftime('%Y%m%d')}.csv"
        },
    )


@router.post("/backup")
async def create_backup():
    backup_name = f"ai-employee-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    backup_path = _BACKUP_DIR / backup_name
    included = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for key, fname in STATE_FILES.items():
            p = _HOME / fname
            if p.exists():
                zf.write(p, fname)
                included.append(fname)
    backup_path.write_bytes(buf.getvalue())
    return JSONResponse({
        "ok": True,
        "backup_file": backup_name,
        "size_bytes": backup_path.stat().st_size,
        "files_included": len(included),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@router.get("/backups")
def list_backups():
    backups = []
    for f in sorted(_BACKUP_DIR.glob("*.zip"), reverse=True)[:20]:
        backups.append({
            "name": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(f.stat().st_mtime)
            ),
        })
    return JSONResponse(backups)


@router.get("/download-backup/{backup_name}")
def download_backup(backup_name: str):
    # Reject any path traversal attempts
    if ".." in backup_name or "/" in backup_name or "\\" in backup_name:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    backup_path = _BACKUP_DIR / backup_name
    if not backup_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    content = backup_path.read_bytes()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={backup_name}"},
    )

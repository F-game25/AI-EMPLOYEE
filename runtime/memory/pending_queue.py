"""Pending review queue — file-backed JSON store for claims awaiting verification.

Per-tenant namespacing (2026-05-18 security audit CRITICAL #2):
each tenant has their own queue file at ~/.ai-employee/tenants/{id}/state/.
"""
import json
import os
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional

LEGACY_QUEUE_PATH = Path('/home/lf/AI-EMPLOYEE/state/pending_review_queue.json')
MAX_ENTRIES = 200


def _current_tenant_id() -> str:
    try:
        from core.tenancy import _current_tenant
        ctx = _current_tenant.get()
        if ctx and ctx.tenant_id:
            return ctx.tenant_id
    except Exception:
        pass
    return "default"


def _queue_path() -> Path:
    # Override for tests / explicit
    override = os.environ.get('PENDING_REVIEW_QUEUE_PATH')
    if override:
        return Path(override)
    tid = _current_tenant_id()
    p = Path(os.path.expanduser(f"~/.ai-employee/tenants/{tid}/state/pending_review_queue.json"))
    # One-shot migrate legacy global queue to default tenant on first read
    if tid == "default" and LEGACY_QUEUE_PATH.exists() and not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(LEGACY_QUEUE_PATH), str(p))
    return p


# Backward-compat: callers that read QUEUE_PATH module-level get default-tenant path
QUEUE_PATH: Path = _queue_path()


def _read() -> dict:
    qp = _queue_path()  # tenant-scoped per call
    if qp.exists():
        try:
            return json.loads(qp.read_text())
        except Exception:
            pass
    return {'entries': []}


def _write(data: dict) -> None:
    qp = _queue_path()
    qp.parent.mkdir(parents=True, exist_ok=True)
    tmp = qp.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(qp)


def add(claim: str, verification: dict, topic: str = 'general',
        sources: Optional[List[str]] = None,
        raw_metadata: Optional[Dict] = None) -> str:
    """Add a claim awaiting review. Returns entry id."""
    data = _read()
    entry_id = f"rev_{uuid.uuid4().hex[:10]}"
    entry = {
        'id': entry_id,
        'claim': claim,
        'verification': verification,
        'topic': topic,
        'sources': sources or [],
        'metadata': raw_metadata or {},
        'ts': time.time(),
        'status': 'pending',
    }
    data['entries'].insert(0, entry)
    data['entries'] = data['entries'][:MAX_ENTRIES]
    _write(data)
    return entry_id


def list_all(status: Optional[str] = None, topic: Optional[str] = None) -> List[Dict]:
    entries = _read().get('entries', [])
    if status:
        entries = [e for e in entries if e.get('status') == status]
    if topic:
        entries = [e for e in entries if e.get('topic') == topic]
    return entries


def get(entry_id: str) -> Optional[Dict]:
    for e in _read().get('entries', []):
        if e.get('id') == entry_id:
            return e
    return None


def update_status(entry_id: str, status: str) -> bool:
    data = _read()
    for e in data.get('entries', []):
        if e.get('id') == entry_id:
            e['status'] = status
            e['decided_at'] = time.time()
            _write(data)
            return True
    return False


def remove(entry_id: str) -> bool:
    data = _read()
    before = len(data.get('entries', []))
    data['entries'] = [e for e in data.get('entries', []) if e.get('id') != entry_id]
    if len(data['entries']) != before:
        _write(data)
        return True
    return False


def stats() -> dict:
    entries = _read().get('entries', [])
    by_status: Dict[str, int] = {}
    for e in entries:
        s = e.get('status', 'pending')
        by_status[s] = by_status.get(s, 0) + 1
    return {'total': len(entries), 'by_status': by_status}

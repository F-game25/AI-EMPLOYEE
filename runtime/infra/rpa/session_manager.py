"""SessionManager — lifecycle pool for browser worker sessions."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from .schema import WorkerSession, SessionStatus, BrowserAction, ActionResult, RPAWorkflow
from .browser_worker import BrowserWorker

logger = logging.getLogger(__name__)

_SESSION_TTL = int(os.getenv("RPA_SESSION_TTL", "1800"))   # 30 min idle timeout
_MAX_SESSIONS = int(os.getenv("RPA_MAX_SESSIONS", "20"))
_WORKFLOW_DB = Path(os.path.expanduser("~/.ai-employee/rpa_workflows.db"))


def _wf_conn() -> sqlite3.Connection:
    _WORKFLOW_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_WORKFLOW_DB), timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("""
        CREATE TABLE IF NOT EXISTS rpa_workflows (
            workflow_id TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            actions     TEXT NOT NULL DEFAULT '[]',
            created_at  REAL NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_wf_tenant ON rpa_workflows(tenant_id)")
    c.commit()
    return c


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, tuple[WorkerSession, BrowserWorker]] = {}
        self._lock = asyncio.Lock()
        _wf_conn()  # ensure schema exists at startup

    # ── Session lifecycle ────────────────────────────────────────────────────

    async def spawn(self, tenant_id: str, browser_type: str = "chromium",
                    tags: Optional[dict] = None) -> WorkerSession:
        async with self._lock:
            active = sum(1 for s, _ in self._sessions.values()
                         if s.status != SessionStatus.TERMINATED)
            if active >= _MAX_SESSIONS:
                raise RuntimeError(f"Max sessions ({_MAX_SESSIONS}) reached")

        sid = str(uuid.uuid4())
        session = WorkerSession(
            session_id=sid, tenant_id=tenant_id,
            browser_type=browser_type, tags=tags or {}
        )
        worker = BrowserWorker(session)
        if not worker.available:
            session.status = SessionStatus.ERROR
            session.tags["error"] = "playwright_not_installed"
            async with self._lock:
                self._sessions[sid] = (session, worker)
            return session

        await worker.start()
        async with self._lock:
            self._sessions[sid] = (session, worker)
        logger.info("Session %s spawned for tenant %s", sid, tenant_id)
        return session

    async def get_session(self, session_id: str, tenant_id: str) -> Optional[WorkerSession]:
        async with self._lock:
            entry = self._sessions.get(session_id)
        if entry and entry[0].tenant_id == tenant_id:
            return entry[0]
        return None

    async def execute_action(self, session_id: str, tenant_id: str,
                             action: BrowserAction) -> ActionResult:
        async with self._lock:
            entry = self._sessions.get(session_id)
        if not entry or entry[0].tenant_id != tenant_id:
            return ActionResult(ok=False, action=action.type, error="session_not_found")
        session, worker = entry
        if session.status == SessionStatus.TERMINATED:
            return ActionResult(ok=False, action=action.type, error="session_terminated")
        return await worker.execute(action)

    async def execute_workflow(self, session_id: str, tenant_id: str,
                               actions: list[BrowserAction]) -> list[ActionResult]:
        results = []
        for action in actions:
            r = await self.execute_action(session_id, tenant_id, action)
            results.append(r)
            if not r.ok:
                break   # stop on first failure
        return results

    async def screenshot(self, session_id: str, tenant_id: str) -> Optional[bytes]:
        async with self._lock:
            entry = self._sessions.get(session_id)
        if not entry or entry[0].tenant_id != tenant_id:
            return None
        return await entry[1].screenshot_bytes()

    async def takeover(self, session_id: str, tenant_id: str):
        async with self._lock:
            entry = self._sessions.get(session_id)
        if not entry or entry[0].tenant_id != tenant_id:
            return None
        return entry[1].takeover_token()

    async def terminate(self, session_id: str, tenant_id: str) -> bool:
        async with self._lock:
            entry = self._sessions.pop(session_id, None)
        if not entry or entry[0].tenant_id != tenant_id:
            return False
        await entry[1].stop()
        return True

    def list_sessions(self, tenant_id: str) -> list[dict]:
        out = []
        for s, _ in self._sessions.values():
            if s.tenant_id == tenant_id:
                out.append({
                    "session_id": s.session_id,
                    "status": s.status.value,
                    "browser_type": s.browser_type,
                    "action_count": s.action_count,
                    "created_at": s.created_at,
                    "last_action_at": s.last_action_at,
                    "tags": s.tags,
                })
        return out

    # ── Cleanup loop ─────────────────────────────────────────────────────────

    async def start_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            await self._reap_idle()

    async def _reap_idle(self) -> None:
        now = time.time()
        to_reap = []
        async with self._lock:
            for sid, (s, _) in self._sessions.items():
                if s.status not in (SessionStatus.TERMINATED, SessionStatus.ERROR):
                    if now - s.last_action_at > _SESSION_TTL:
                        to_reap.append(sid)
        for sid in to_reap:
            logger.info("Reaping idle session %s", sid)
            async with self._lock:
                entry = self._sessions.pop(sid, None)
            if entry:
                await entry[1].stop()

    # ── Workflow persistence (SQLite, WAL, tenant-scoped) ────────────────────

    def save_workflow(self, tenant_id: str, name: str, description: str,
                      actions: list[dict]) -> RPAWorkflow:
        wid = str(uuid.uuid4())
        wf = RPAWorkflow(workflow_id=wid, tenant_id=tenant_id, name=name,
                         description=description, actions=actions)
        with _wf_conn() as c:
            c.execute(
                "INSERT INTO rpa_workflows (workflow_id,tenant_id,name,description,actions,created_at)"
                " VALUES (?,?,?,?,?,?)",
                (wid, tenant_id, name, description, json.dumps(actions), wf.created_at)
            )
        return wf

    def list_workflows(self, tenant_id: str) -> list[dict]:
        with _wf_conn() as c:
            rows = c.execute(
                "SELECT workflow_id,name,description,actions,created_at"
                " FROM rpa_workflows WHERE tenant_id=? ORDER BY created_at DESC",
                (tenant_id,)
            ).fetchall()
        return [
            {"workflow_id": r[0], "name": r[1], "description": r[2],
             "action_count": len(json.loads(r[3])), "created_at": r[4]}
            for r in rows
        ]

    def get_workflow(self, workflow_id: str, tenant_id: str) -> Optional[RPAWorkflow]:
        with _wf_conn() as c:
            row = c.execute(
                "SELECT workflow_id,tenant_id,name,description,actions,created_at"
                " FROM rpa_workflows WHERE workflow_id=? AND tenant_id=?",
                (workflow_id, tenant_id)
            ).fetchone()
        if not row:
            return None
        return RPAWorkflow(
            workflow_id=row[0], tenant_id=row[1], name=row[2],
            description=row[3], actions=json.loads(row[4]), created_at=row[5]
        )


_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _instance
    if _instance is None:
        _instance = SessionManager()
    return _instance

"""RAG Sync Daemon — near-real-time incremental sync for all connectors.

Runs as a background asyncio task inside the Python AI backend process.
Each tenant gets independent sync schedules per source type.
Default intervals: every 5 minutes for Slack/Gmail, every 30min for Drive/SharePoint.

Usage:
    from infra.rag.sync_daemon import get_sync_daemon
    daemon = get_sync_daemon()
    await daemon.start()       # call once at app startup
    await daemon.stop()        # call at shutdown
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from infra.rag.connectors import get_connector
from infra.rag.pipeline import get_pipeline
from infra.rag.schema import SourceType

logger = logging.getLogger("rag.sync_daemon")

_SYNC_INTERVALS: dict[SourceType, int] = {
    SourceType.SLACK:        300,    # 5 min
    SourceType.GMAIL:        300,
    SourceType.JIRA:         600,    # 10 min
    SourceType.CONFLUENCE:   1800,   # 30 min
    SourceType.SHAREPOINT:   1800,
    SourceType.GOOGLE_DRIVE: 1800,
    SourceType.CRM:          900,    # 15 min
}


@dataclass
class ConnectorConfig:
    tenant_id: str
    source_type: SourceType
    credentials: dict[str, Any]
    enabled: bool = True
    interval_seconds: int = 0  # 0 = use default from _SYNC_INTERVALS

    def effective_interval(self) -> int:
        return self.interval_seconds or _SYNC_INTERVALS.get(self.source_type, 1800)


class SyncDaemon:
    def __init__(self) -> None:
        self._configs: list[ConnectorConfig] = []
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._stats: dict[str, Any] = {}

    def register(self, config: ConnectorConfig) -> None:
        self._configs.append(config)
        logger.info("RAG sync registered: tenant=%s source=%s interval=%ds",
                    config.tenant_id, config.source_type.value, config.effective_interval())

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for cfg in self._configs:
            if cfg.enabled:
                task = asyncio.create_task(self._sync_loop(cfg), name=f"rag_sync_{cfg.tenant_id}_{cfg.source_type.value}")
                self._tasks.append(task)
        logger.info("RAG SyncDaemon started: %d connectors", len(self._tasks))

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("RAG SyncDaemon stopped")

    async def trigger_sync(self, tenant_id: str, source_type: SourceType, full: bool = False) -> dict:
        cfg = next((c for c in self._configs if c.tenant_id == tenant_id and c.source_type == source_type), None)
        if not cfg:
            return {"error": "connector not registered"}
        return await self._do_sync(cfg, full=full)

    def get_stats(self) -> dict:
        return dict(self._stats)

    async def _sync_loop(self, cfg: ConnectorConfig) -> None:
        # Stagger startup to avoid thundering herd
        await asyncio.sleep(hash(f"{cfg.tenant_id}{cfg.source_type.value}") % 60)
        while self._running:
            try:
                await self._do_sync(cfg)
            except Exception as e:
                logger.error("Sync loop error tenant=%s source=%s: %s", cfg.tenant_id, cfg.source_type.value, e)
            await asyncio.sleep(cfg.effective_interval())

    async def _do_sync(self, cfg: ConnectorConfig, full: bool = False) -> dict:
        t0 = time.time()
        key = f"{cfg.tenant_id}:{cfg.source_type.value}"
        try:
            connector = get_connector(cfg.source_type, cfg.tenant_id, cfg.credentials)
            pipeline = get_pipeline(cfg.tenant_id)
            stats = await pipeline.ingest_connector(connector, full_sync=full)
            stats["elapsed_s"] = round(time.time() - t0, 2)
            stats["synced_at"] = time.time()
            self._stats[key] = {"ok": True, **stats}
            return stats
        except Exception as e:
            err = {"ok": False, "error": str(e), "elapsed_s": round(time.time() - t0, 2)}
            self._stats[key] = err
            logger.error("Sync failed %s: %s", key, e)
            return err


_daemon: SyncDaemon | None = None

def get_sync_daemon() -> SyncDaemon:
    global _daemon
    if _daemon is None:
        _daemon = SyncDaemon()
        _auto_register(_daemon)
    return _daemon


def _auto_register(daemon: SyncDaemon) -> None:
    """Register connectors from environment variables."""
    tenant_id = os.environ.get("DEFAULT_TENANT_ID", "system")

    env_map = {
        SourceType.SLACK:        {"bot_token": os.environ.get("SLACK_BOT_TOKEN", "")},
        SourceType.GMAIL:        {"access_token": os.environ.get("GMAIL_ACCESS_TOKEN", "")},
        SourceType.JIRA:         {"base_url": os.environ.get("JIRA_BASE_URL", ""),
                                  "email": os.environ.get("JIRA_EMAIL", ""),
                                  "api_token": os.environ.get("JIRA_API_TOKEN", "")},
        SourceType.CONFLUENCE:   {"base_url": os.environ.get("CONFLUENCE_BASE_URL", ""),
                                  "email": os.environ.get("CONFLUENCE_EMAIL", ""),
                                  "api_token": os.environ.get("CONFLUENCE_API_TOKEN", "")},
        SourceType.SHAREPOINT:   {"access_token": os.environ.get("SHAREPOINT_ACCESS_TOKEN", ""),
                                  "site_id": os.environ.get("SHAREPOINT_SITE_ID", "")},
        SourceType.GOOGLE_DRIVE: {"service_account_json": os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")},
        SourceType.CRM:          {"crm_type": os.environ.get("CRM_TYPE", "hubspot"),
                                  "access_token": os.environ.get("CRM_ACCESS_TOKEN", "")},
    }

    for source_type, creds in env_map.items():
        # Only register if at least one credential is non-empty
        if any(v for v in creds.values()):
            daemon.register(ConnectorConfig(
                tenant_id=tenant_id,
                source_type=source_type,
                credentials=creds,
            ))

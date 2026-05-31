import logging
import time
from typing import Optional
from collections import defaultdict
from .schema import AnomalyCorrelation
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS anomaly_correlations (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                anomaly_ids TEXT NOT NULL,
                suspected_root_cause TEXT,
                confidence REAL DEFAULT 0,
                affected_subsystems TEXT,
                detected_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_tenant ON anomaly_correlations(tenant_id)")


_ensure_table()


class AnomalyCorrelator:
    def __init__(self, time_window_s: float = 60.0):
        self.time_window_s = time_window_s
        self.recent_anomalies: defaultdict[str, list] = defaultdict(list)

    def record_anomaly(
        self,
        anomaly_id: str,
        tenant_id: str,
        subsystem_id: str,
        error_message: str = "",
    ) -> Optional[AnomalyCorrelation]:
        now = time.time()
        self.recent_anomalies[tenant_id].append({
            "id": anomaly_id,
            "subsystem": subsystem_id,
            "timestamp": now,
            "error": error_message,
        })

        self._cleanup_old_anomalies(tenant_id, now)
        return self._check_correlation(tenant_id, anomaly_id, now)

    def _cleanup_old_anomalies(self, tenant_id: str, now: float) -> None:
        if tenant_id in self.recent_anomalies:
            self.recent_anomalies[tenant_id] = [
                a for a in self.recent_anomalies[tenant_id]
                if now - a["timestamp"] < self.time_window_s
            ]

    def _check_correlation(self, tenant_id: str, anomaly_id: str, now: float) -> Optional[AnomalyCorrelation]:
        anomalies_in_window = self.recent_anomalies[tenant_id]
        if len(anomalies_in_window) < 2:
            return None

        subsystems = [a["subsystem"] for a in anomalies_in_window]
        common_subsystems = set(subsystems)

        if len(common_subsystems) > 1:
            correlation = AnomalyCorrelation(
                tenant_id=tenant_id,
                anomaly_ids=[a["id"] for a in anomalies_in_window],
                suspected_root_cause="multiple_subsystems_affected",
                confidence=min(0.9, len(anomalies_in_window) / 10),
                affected_subsystems=list(common_subsystems),
                detected_at=now,
            )
            self._store_correlation(correlation)
            return correlation

        return None

    def _store_correlation(self, correlation: AnomalyCorrelation) -> None:
        try:
            import json
            with cognitive_conn() as c:
                c.execute(
                    "INSERT INTO anomaly_correlations "
                    "(id, tenant_id, anomaly_ids, suspected_root_cause, confidence, affected_subsystems, detected_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        correlation.id,
                        correlation.tenant_id,
                        json.dumps(correlation.anomaly_ids),
                        correlation.suspected_root_cause,
                        correlation.confidence,
                        json.dumps(correlation.affected_subsystems),
                        correlation.detected_at,
                    ),
                )
        except Exception as e:
            logger.warning("Failed to store anomaly correlation: %s", e)

    def get_correlations(self, tenant_id: str, limit: int = 50) -> list[dict]:
        try:
            import json
            with cognitive_conn() as c:
                rows = c.execute(
                    "SELECT * FROM anomaly_correlations WHERE tenant_id=? ORDER BY detected_at DESC LIMIT ?",
                    (tenant_id, limit),
                ).fetchall()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning("Failed to get anomaly correlations: %s", e)
            return []


_instance: Optional[AnomalyCorrelator] = None


def get_anomaly_correlator() -> AnomalyCorrelator:
    global _instance
    if _instance is None:
        _instance = AnomalyCorrelator()
    return _instance

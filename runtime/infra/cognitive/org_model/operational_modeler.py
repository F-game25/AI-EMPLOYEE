import json
import time
import logging
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_op_model (
                agent_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                avg_latency_ms REAL DEFAULT 0.0,
                failure_patterns TEXT DEFAULT '{}',
                peak_load_hour INTEGER DEFAULT 12,
                updated_at REAL NOT NULL,
                PRIMARY KEY (agent_id, tenant_id)
            )
        """)


_ensure_table()


def record_execution(agent_id: str, tenant_id: str, success: bool, latency_ms: float, error: str = None) -> None:
    now = time.time()
    hour = time.localtime().tm_hour
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT * FROM agent_op_model WHERE agent_id=? AND tenant_id=?",
            (agent_id, tenant_id)
        ).fetchone()
        if row:
            sc = row["success_count"] + (1 if success else 0)
            fc = row["failure_count"] + (0 if success else 1)
            lat = (row["avg_latency_ms"] + latency_ms) / 2
            fp = json.loads(row["failure_patterns"])
            if error:
                fp[error[:50]] = fp.get(error[:50], 0) + 1
                fp = dict(sorted(fp.items(), key=lambda x: -x[1])[:5])
            c.execute(
                "UPDATE agent_op_model SET success_count=?, failure_count=?, avg_latency_ms=?, failure_patterns=?, peak_load_hour=?, updated_at=? WHERE agent_id=? AND tenant_id=?",
                (sc, fc, lat, json.dumps(fp), hour, now, agent_id, tenant_id)
            )
        else:
            fp = {error[:50]: 1} if error else {}
            c.execute(
                "INSERT INTO agent_op_model VALUES (?,?,?,?,?,?,?,?)",
                (agent_id, tenant_id, 1 if success else 0, 0 if success else 1, latency_ms, json.dumps(fp), hour, now)
            )


def get_all_models(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute("SELECT * FROM agent_op_model WHERE tenant_id=? ORDER BY success_count DESC", (tenant_id,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["failure_patterns"] = json.loads(d["failure_patterns"])
        total = d["success_count"] + d["failure_count"]
        d["success_rate"] = round(d["success_count"] / max(total, 1), 3)
        d["total_executions"] = total
        result.append(d)
    return result


def get_model(agent_id: str, tenant_id: str) -> dict | None:
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT * FROM agent_op_model WHERE agent_id=? AND tenant_id=?",
            (agent_id, tenant_id)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["failure_patterns"] = json.loads(d["failure_patterns"])
    total = d["success_count"] + d["failure_count"]
    d["success_rate"] = round(d["success_count"] / max(total, 1), 3)
    d["total_executions"] = total
    return d


def get_summary(tenant_id: str) -> dict:
    """Get summary statistics across all agents."""
    with cognitive_conn() as c:
        rows = c.execute("SELECT * FROM agent_op_model WHERE tenant_id=?", (tenant_id,)).fetchall()
    if not rows:
        return {"agents": 0, "avg_success_rate": 0.0, "total_executions": 0, "avg_latency_ms": 0.0}

    total_success = sum(r["success_count"] for r in rows)
    total_failure = sum(r["failure_count"] for r in rows)
    total_exec = total_success + total_failure
    avg_latency = sum(r["avg_latency_ms"] for r in rows) / len(rows) if rows else 0.0

    return {
        "agents": len(rows),
        "avg_success_rate": round(total_success / max(total_exec, 1), 3),
        "total_executions": total_exec,
        "avg_latency_ms": round(avg_latency, 1),
    }

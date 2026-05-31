import json
import time
import logging
import collections
from .schema import UserBehaviorProfile
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                peak_hours TEXT DEFAULT '[]',
                frequent_workflows TEXT DEFAULT '{}',
                avg_session_length_m REAL DEFAULT 0.0,
                preferred_agents TEXT DEFAULT '{}',
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, tenant_id)
            )
        """)


_ensure_table()


def record_request(user_id: str, tenant_id: str, workflow_type: str, agent_id: str) -> None:
    hour = time.localtime().tm_hour
    now = time.time()
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT * FROM user_profiles WHERE user_id=? AND tenant_id=?",
            (user_id, tenant_id)
        ).fetchone()
        if row:
            peaks = json.loads(row["peak_hours"])
            peaks.append(hour)
            peaks = peaks[-168:]  # 1 week of hourly data
            wf = json.loads(row["frequent_workflows"])
            wf[workflow_type] = wf.get(workflow_type, 0) + 1
            ag = json.loads(row["preferred_agents"])
            ag[agent_id] = ag.get(agent_id, 0) + 1
            c.execute(
                "UPDATE user_profiles SET peak_hours=?, frequent_workflows=?, preferred_agents=?, updated_at=? WHERE user_id=? AND tenant_id=?",
                (json.dumps(peaks), json.dumps(wf), json.dumps(ag), now, user_id, tenant_id)
            )
        else:
            c.execute(
                "INSERT INTO user_profiles VALUES (?,?,?,?,?,?,?)",
                (user_id, tenant_id, json.dumps([hour]), json.dumps({workflow_type: 1}), 0.0, json.dumps({agent_id: 1}), now)
            )


def get_profile(user_id: str, tenant_id: str) -> dict:
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT * FROM user_profiles WHERE user_id=? AND tenant_id=?",
            (user_id, tenant_id)
        ).fetchone()
    if not row:
        return {"user_id": user_id, "tenant_id": tenant_id, "profile": None}
    d = dict(row)
    d["peak_hours"] = json.loads(d["peak_hours"])
    d["frequent_workflows"] = json.loads(d["frequent_workflows"])
    d["preferred_agents"] = json.loads(d["preferred_agents"])
    return d


_instance = None


def get_user_profiler():
    global _instance
    if _instance is None:
        _instance = type("UserProfiler", (), {
            "record_request": staticmethod(record_request),
            "get_profile": staticmethod(get_profile),
        })()
    return _instance

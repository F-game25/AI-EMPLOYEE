import time
import logging
import uuid
from .schema import HallucinationFlag
from ..db import cognitive_conn

logger = logging.getLogger(__name__)

_ABSOLUTE_WORDS = {"always", "never", "100%", "guaranteed", "impossible", "definitely"}


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS hallucination_flags (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                flag_type TEXT DEFAULT 'low_confidence',
                severity INTEGER DEFAULT 1,
                reason TEXT,
                flagged_at REAL NOT NULL,
                quarantined INTEGER DEFAULT 0
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_hf_tenant ON hallucination_flags(tenant_id, flagged_at)")


_ensure_table()


def flag(memory: dict, tenant_id: str = "system") -> dict:
    flags = []
    flag_ids = []
    content = memory.get("content", "").lower()
    confidence = memory.get("confidence", 1.0)
    memory_id = memory.get("id", "")

    if confidence < 0.5 and not memory.get("corroborating_source"):
        hf = HallucinationFlag(
            tenant_id=tenant_id,
            memory_id=memory_id,
            flag_type="low_confidence_no_source",
            severity=3,
            reason=f"Low confidence ({confidence:.2f}) without corroborating source"
        )
        flags.append("low_confidence_no_source")
        flag_ids.append(hf.id)
        _store_flag(hf)

    words = set(content.split())
    if words & _ABSOLUTE_WORDS:
        hf = HallucinationFlag(
            tenant_id=tenant_id,
            memory_id=memory_id,
            flag_type="absolute_claim",
            severity=2,
            reason="Uses absolute language without qualifiers"
        )
        flags.append("absolute_claim")
        flag_ids.append(hf.id)
        _store_flag(hf)

    ts = memory.get("timestamp", 0)
    if ts and ts > time.time():
        hf = HallucinationFlag(
            tenant_id=tenant_id,
            memory_id=memory_id,
            flag_type="future_dated",
            severity=5,
            reason=f"Timestamp in future ({ts - time.time():.0f}s ahead)"
        )
        flags.append("future_dated")
        flag_ids.append(hf.id)
        _store_flag(hf)

    should_quarantine = any(f == "future_dated" for f in flags) or len(flags) >= 2
    return {
        "memory_id": memory_id,
        "flags": flags,
        "flag_ids": flag_ids,
        "should_quarantine": should_quarantine,
        "severity": max([3 if "low_confidence" in f else 2 if "absolute" in f else 5 for f in flags] or [0])
    }


def _store_flag(hf: HallucinationFlag) -> None:
    with cognitive_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO hallucination_flags VALUES (?,?,?,?,?,?,?,?)",
            (hf.id, hf.tenant_id, hf.memory_id, hf.flag_type, hf.severity,
             hf.reason, hf.flagged_at, 1 if hf.quarantined else 0)
        )


def list_flags(tenant_id: str, limit: int = 50) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM hallucination_flags WHERE tenant_id=? ORDER BY flagged_at DESC LIMIT ?",
            (tenant_id, limit)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["quarantined"] = bool(d["quarantined"])
        result.append(d)
    return result

"""Tests for Data Lifecycle Manager — runtime/core/data_lifecycle_manager.py.

Coverage:
  RetentionPolicy:
  - ttl_days=0 → enabled=False
  - ttl_days>0 → enabled=True, cutoff_epoch/iso correct
  - to_dict() shape

  PurgeResult:
  - to_dict() has required keys

  _SqliteHandler:
  - purge disabled (TTL=0) → skipped=True
  - purge absent db → skipped=True
  - purge deletes old rows, retains new ones
  - count_total on absent db returns 0

  _JsonlHandler:
  - purge disabled → skipped=True
  - purge absent file → skipped=True
  - purge deletes old entries, retains new ones
  - malformed JSON lines always retained
  - missing ts field → retained
  - result counts correct

  _MemoryIndexHandler:
  - purge disabled → skipped=True
  - purge absent file → skipped=True
  - purge deletes expired memories, retains fresh ones
  - updated_at field written after purge

  DataLifecycleManager:
  - get_policies() returns 5 known stores
  - get_policy() returns correct shape for known store
  - get_policy() returns None for unknown store
  - set_ttl() updates policy
  - set_ttl() returns False for unknown store
  - purge() returns skipped for unknown store
  - purge() delegates to correct handler
  - purge_all() purges all stores, returns dict
  - status() includes policies + scheduler + last_run
  - scheduler starts and is_running()
  - scheduler stops after stop_scheduler()
  - singleton identity

  Server integration:
  - _get_lifecycle_manager loader present
  - GET /api/lifecycle endpoint registered
  - POST /api/lifecycle/purge endpoint registered
  - PATCH /api/lifecycle/{store_id}/ttl endpoint registered
  - data_lifecycle_manager.py module exists
"""
from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT   = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.data_lifecycle_manager import (
    DataLifecycleManager,
    PurgeResult,
    RetentionPolicy,
    _JsonlHandler,
    _MemoryIndexHandler,
    _SqliteHandler,
    _parse_iso,
    get_lifecycle_manager,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _ago(days: float) -> str:
    """Return an ISO timestamp that is `days` days in the past."""
    t = time.time() - (days * 86400)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _future(days: float = 1) -> str:
    """Return an ISO timestamp that is `days` days in the future."""
    t = time.time() + (days * 86400)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


# ═══════════════════════════════════════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseIso:
    def test_valid_iso_z(self):
        ts = _parse_iso("2020-01-01T00:00:00Z")
        assert ts is not None
        assert ts > 0

    def test_none_input(self):
        assert _parse_iso(None) is None

    def test_empty_string(self):
        assert _parse_iso("") is None

    def test_returns_float(self):
        ts = _parse_iso("2023-06-15T12:00:00Z")
        assert isinstance(ts, float)


# ═══════════════════════════════════════════════════════════════════════════════
# RetentionPolicy
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetentionPolicy:
    def test_enabled_false_when_ttl_zero(self):
        p = RetentionPolicy(store_id="x", ttl_days=0, store_type="sqlite")
        assert p.enabled is False

    def test_enabled_true_when_ttl_positive(self):
        p = RetentionPolicy(store_id="x", ttl_days=30, store_type="sqlite")
        assert p.enabled is True

    def test_cutoff_epoch_is_past(self):
        p = RetentionPolicy(store_id="x", ttl_days=30, store_type="sqlite")
        assert p.cutoff_epoch() < time.time()

    def test_cutoff_iso_is_string(self):
        p = RetentionPolicy(store_id="x", ttl_days=30, store_type="sqlite")
        s = p.cutoff_iso()
        assert isinstance(s, str)
        assert "T" in s

    def test_to_dict_shape(self):
        p = RetentionPolicy(store_id="audit_log", ttl_days=90, store_type="sqlite", description="d")
        d = p.to_dict()
        for key in ("store_id", "ttl_days", "store_type", "description", "enabled", "cutoff_iso"):
            assert key in d

    def test_to_dict_cutoff_none_when_disabled(self):
        p = RetentionPolicy(store_id="x", ttl_days=0, store_type="sqlite")
        assert p.to_dict()["cutoff_iso"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# PurgeResult
# ═══════════════════════════════════════════════════════════════════════════════

class TestPurgeResult:
    def test_to_dict_required_keys(self):
        r = PurgeResult(store_id="test")
        d = r.to_dict()
        for key in ("store_id", "deleted", "retained", "skipped", "error", "duration_ms"):
            assert key in d

    def test_defaults(self):
        r = PurgeResult(store_id="test")
        assert r.deleted == 0
        assert r.retained == 0
        assert r.skipped is False
        assert r.error == ""


# ═══════════════════════════════════════════════════════════════════════════════
# _SqliteHandler
# ═══════════════════════════════════════════════════════════════════════════════

def _make_sqlite_db(path: Path, rows: list[tuple[str, str]]) -> None:
    """Create a test audit_log.db with (id, ts) rows."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_log "
        "(id TEXT PRIMARY KEY, ts TEXT NOT NULL, actor TEXT DEFAULT '', action TEXT DEFAULT '', "
        "input TEXT DEFAULT '', output TEXT DEFAULT '', risk_score REAL DEFAULT 0, "
        "trace_id TEXT DEFAULT '', meta TEXT DEFAULT '')"
    )
    for row_id, ts in rows:
        conn.execute(
            "INSERT OR IGNORE INTO audit_log (id, ts, actor, action) VALUES (?, ?, '', '')",
            (row_id, ts),
        )
    conn.commit()
    conn.close()


class TestSqliteHandler:
    def test_count_total_absent_db(self, tmp_path):
        h = _SqliteHandler(tmp_path / "missing.db", "audit_log")
        assert h.count_total() == 0

    def test_purge_disabled_skips(self, tmp_path):
        db = tmp_path / "audit_log.db"
        _make_sqlite_db(db, [("r1", _ago(200))])
        h = _SqliteHandler(db, "audit_log")
        policy = RetentionPolicy(store_id="audit_log", ttl_days=0, store_type="sqlite")
        result = h.purge(policy)
        assert result.skipped is True
        assert result.deleted == 0

    def test_purge_absent_db_skips(self, tmp_path):
        h = _SqliteHandler(tmp_path / "absent.db", "audit_log")
        policy = RetentionPolicy(store_id="audit_log", ttl_days=90, store_type="sqlite")
        result = h.purge(policy)
        assert result.skipped is True

    def test_purge_deletes_old_keeps_new(self, tmp_path):
        db = tmp_path / "audit_log.db"
        _make_sqlite_db(db, [
            ("old1", _ago(100)),
            ("old2", _ago(95)),
            ("new1", _ago(10)),
            ("new2", _ago(5)),
        ])
        h = _SqliteHandler(db, "audit_log")
        policy = RetentionPolicy(store_id="audit_log", ttl_days=90, store_type="sqlite")
        result = h.purge(policy)
        assert result.deleted == 2
        assert result.retained == 2
        assert result.skipped is False
        assert result.error == ""

    def test_purge_returns_duration_ms(self, tmp_path):
        db = tmp_path / "audit_log.db"
        _make_sqlite_db(db, [("r1", _ago(100))])
        h = _SqliteHandler(db, "audit_log")
        policy = RetentionPolicy(store_id="audit_log", ttl_days=90, store_type="sqlite")
        result = h.purge(policy)
        assert result.duration_ms >= 0

    def test_purge_all_old_rows(self, tmp_path):
        db = tmp_path / "audit_log.db"
        _make_sqlite_db(db, [("a", _ago(200)), ("b", _ago(300))])
        h = _SqliteHandler(db, "audit_log")
        policy = RetentionPolicy(store_id="audit_log", ttl_days=90, store_type="sqlite")
        result = h.purge(policy)
        assert result.deleted == 2
        assert result.retained == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _JsonlHandler
# ═══════════════════════════════════════════════════════════════════════════════

def _make_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class TestJsonlHandler:
    def test_count_total_absent(self, tmp_path):
        h = _JsonlHandler(tmp_path / "missing.jsonl")
        assert h.count_total() == 0

    def test_purge_disabled_skips(self, tmp_path):
        f = tmp_path / "chat.jsonl"
        _make_jsonl(f, [{"ts": _ago(100), "msg": "hi"}])
        h = _JsonlHandler(f)
        policy = RetentionPolicy(store_id="chat_history", ttl_days=0, store_type="jsonl")
        result = h.purge(policy)
        assert result.skipped is True

    def test_purge_absent_file_skips(self, tmp_path):
        h = _JsonlHandler(tmp_path / "absent.jsonl")
        policy = RetentionPolicy(store_id="chat_history", ttl_days=60, store_type="jsonl")
        result = h.purge(policy)
        assert result.skipped is True

    def test_purge_deletes_old_keeps_new(self, tmp_path):
        f = tmp_path / "chat.jsonl"
        _make_jsonl(f, [
            {"ts": _ago(100), "msg": "old1"},
            {"ts": _ago(70), "msg": "old2"},
            {"ts": _ago(10), "msg": "new1"},
            {"ts": _future(1), "msg": "future"},
        ])
        h = _JsonlHandler(f)
        policy = RetentionPolicy(store_id="chat_history", ttl_days=60, store_type="jsonl")
        result = h.purge(policy)
        assert result.deleted == 2
        assert result.retained == 2
        assert result.error == ""

    def test_malformed_lines_always_kept(self, tmp_path):
        f = tmp_path / "chat.jsonl"
        f.write_text('not-json\n{"ts": "' + _ago(200) + '", "msg": "old"}\n', encoding="utf-8")
        h = _JsonlHandler(f)
        policy = RetentionPolicy(store_id="chat_history", ttl_days=60, store_type="jsonl")
        result = h.purge(policy)
        # Only the valid old entry should be deleted; the malformed line is kept
        assert result.deleted == 1
        assert result.retained == 1

    def test_missing_ts_field_kept(self, tmp_path):
        f = tmp_path / "chat.jsonl"
        _make_jsonl(f, [{"msg": "no-timestamp"}])
        h = _JsonlHandler(f)
        policy = RetentionPolicy(store_id="chat_history", ttl_days=1, store_type="jsonl")
        result = h.purge(policy)
        assert result.deleted == 0
        assert result.retained == 1

    def test_file_rewritten_correctly(self, tmp_path):
        f = tmp_path / "chat.jsonl"
        _make_jsonl(f, [
            {"ts": _ago(200), "msg": "old"},
            {"ts": _ago(1), "msg": "new"},
        ])
        h = _JsonlHandler(f)
        policy = RetentionPolicy(store_id="chat_history", ttl_days=60, store_type="jsonl")
        h.purge(policy)
        remaining = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        assert len(remaining) == 1
        assert remaining[0]["msg"] == "new"


# ═══════════════════════════════════════════════════════════════════════════════
# _MemoryIndexHandler
# ═══════════════════════════════════════════════════════════════════════════════

def _make_memory_json(path: Path, memories: list[dict]) -> None:
    path.write_text(json.dumps({"updated_at": "2020-01-01T00:00:00Z", "memories": memories}), encoding="utf-8")


class TestMemoryIndexHandler:
    def test_count_total_absent(self, tmp_path):
        h = _MemoryIndexHandler(tmp_path / "missing.json")
        assert h.count_total() == 0

    def test_purge_disabled_skips(self, tmp_path):
        f = tmp_path / "memory_index.json"
        _make_memory_json(f, [{"id": "m1", "text": "x", "last_used": _ago(400)}])
        h = _MemoryIndexHandler(f)
        policy = RetentionPolicy(store_id="memory_index", ttl_days=0, store_type="json")
        result = h.purge(policy)
        assert result.skipped is True

    def test_purge_absent_file_skips(self, tmp_path):
        h = _MemoryIndexHandler(tmp_path / "absent.json")
        policy = RetentionPolicy(store_id="memory_index", ttl_days=365, store_type="json")
        result = h.purge(policy)
        assert result.skipped is True

    def test_purge_deletes_expired_keeps_fresh(self, tmp_path):
        f = tmp_path / "memory_index.json"
        _make_memory_json(f, [
            {"id": "m1", "text": "expired", "last_used": _ago(400)},
            {"id": "m2", "text": "old",     "last_used": _ago(370)},
            {"id": "m3", "text": "fresh",   "last_used": _ago(10)},
        ])
        h = _MemoryIndexHandler(f)
        policy = RetentionPolicy(store_id="memory_index", ttl_days=365, store_type="json")
        result = h.purge(policy)
        assert result.deleted == 2
        assert result.retained == 1
        assert result.error == ""

    def test_updated_at_refreshed(self, tmp_path):
        f = tmp_path / "memory_index.json"
        _make_memory_json(f, [{"id": "m1", "text": "old", "last_used": _ago(400)}])
        h = _MemoryIndexHandler(f)
        policy = RetentionPolicy(store_id="memory_index", ttl_days=365, store_type="json")
        h.purge(policy)
        payload = json.loads(f.read_text())
        assert payload["updated_at"] != "2020-01-01T00:00:00Z"

    def test_entries_without_last_used_retained(self, tmp_path):
        f = tmp_path / "memory_index.json"
        _make_memory_json(f, [{"id": "m1", "text": "no-date"}])
        h = _MemoryIndexHandler(f)
        policy = RetentionPolicy(store_id="memory_index", ttl_days=1, store_type="json")
        result = h.purge(policy)
        assert result.deleted == 0
        assert result.retained == 1


# ═══════════════════════════════════════════════════════════════════════════════
# DataLifecycleManager
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataLifecycleManager:
    def _mgr(self, tmp_path: Path) -> DataLifecycleManager:
        return DataLifecycleManager(state_dir=tmp_path)

    def test_get_policies_returns_five_stores(self, tmp_path):
        mgr = self._mgr(tmp_path)
        policies = mgr.get_policies()
        assert len(policies) == 5
        expected = {"audit_log", "observability_events", "chat_history", "activity_log", "memory_index"}
        assert set(policies.keys()) == expected

    def test_get_policy_known_store(self, tmp_path):
        mgr = self._mgr(tmp_path)
        p = mgr.get_policy("audit_log")
        assert p is not None
        assert p["store_id"] == "audit_log"
        assert p["ttl_days"] > 0

    def test_get_policy_unknown_returns_none(self, tmp_path):
        mgr = self._mgr(tmp_path)
        assert mgr.get_policy("nonexistent") is None

    def test_set_ttl_updates_policy(self, tmp_path):
        mgr = self._mgr(tmp_path)
        assert mgr.set_ttl("audit_log", days=7) is True
        assert mgr.get_policy("audit_log")["ttl_days"] == 7

    def test_set_ttl_to_zero_disables(self, tmp_path):
        mgr = self._mgr(tmp_path)
        mgr.set_ttl("chat_history", days=0)
        assert mgr.get_policy("chat_history")["enabled"] is False

    def test_set_ttl_unknown_returns_false(self, tmp_path):
        mgr = self._mgr(tmp_path)
        assert mgr.set_ttl("no_such_store", days=30) is False

    def test_purge_unknown_store_skipped(self, tmp_path):
        mgr = self._mgr(tmp_path)
        result = mgr.purge("unknown_store")
        assert result.skipped is True
        assert "unknown" in result.error

    def test_purge_absent_files_skipped(self, tmp_path):
        mgr = self._mgr(tmp_path)
        for sid in ("audit_log", "observability_events", "chat_history", "activity_log", "memory_index"):
            result = mgr.purge(sid)
            assert result.skipped is True, f"{sid} should be skipped when file absent"

    def test_purge_all_returns_dict_for_all_stores(self, tmp_path):
        mgr = self._mgr(tmp_path)
        results = mgr.purge_all()
        assert set(results.keys()) == {"audit_log", "observability_events", "chat_history", "activity_log", "memory_index"}

    def test_purge_all_updates_last_run(self, tmp_path):
        mgr = self._mgr(tmp_path)
        assert mgr.status()["last_run"] is None
        mgr.purge_all()
        assert mgr.status()["last_run"] is not None

    def test_purge_chat_history_real(self, tmp_path):
        chatlog = tmp_path / "chatlog.jsonl"
        chatlog.write_text(
            json.dumps({"ts": _ago(100), "msg": "old"}) + "\n" +
            json.dumps({"ts": _ago(1),   "msg": "new"}) + "\n",
            encoding="utf-8",
        )
        mgr = self._mgr(tmp_path)
        result = mgr.purge("chat_history")
        assert result.deleted == 1
        assert result.retained == 1

    def test_purge_memory_index_real(self, tmp_path):
        mi = tmp_path / "memory_index.json"
        mi.write_text(json.dumps({
            "updated_at": "2020-01-01T00:00:00Z",
            "memories": [
                {"id": "m1", "text": "old", "last_used": _ago(400)},
                {"id": "m2", "text": "new", "last_used": _ago(5)},
            ]
        }), encoding="utf-8")
        mgr = self._mgr(tmp_path)
        result = mgr.purge("memory_index")
        assert result.deleted == 1
        assert result.retained == 1

    def test_status_shape(self, tmp_path):
        mgr = self._mgr(tmp_path)
        s = mgr.status()
        assert "policies" in s
        assert "last_run" in s
        assert "scheduler" in s
        assert "store_count" in s
        assert s["store_count"] == 5

    def test_scheduler_starts(self, tmp_path):
        mgr = self._mgr(tmp_path)
        assert not mgr.scheduler_running()
        mgr.start_scheduler(interval_hours=999)
        assert mgr.scheduler_running()
        mgr.stop_scheduler()
        time.sleep(0.1)

    def test_scheduler_idempotent_start(self, tmp_path):
        mgr = self._mgr(tmp_path)
        mgr.start_scheduler(interval_hours=999)
        mgr.start_scheduler(interval_hours=999)  # Should not raise or double-start
        assert mgr.scheduler_running()
        mgr.stop_scheduler()

    def test_thread_safety(self, tmp_path):
        """Concurrent purge_all calls must not raise."""
        mgr = self._mgr(tmp_path)
        errors: list[str] = []
        barrier = threading.Barrier(5)

        def _worker():
            barrier.wait()
            try:
                mgr.purge_all()
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_singleton_identity(self):
        a = get_lifecycle_manager()
        b = get_lifecycle_manager()
        assert a is b

    def test_singleton_has_five_stores(self):
        mgr = get_lifecycle_manager()
        assert len(mgr.get_policies()) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Server integration (static analysis)
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerLifecycleIntegration:
    def _src(self) -> str:
        return (REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py").read_text()

    def test_lifecycle_loader_defined(self):
        assert "_get_lifecycle_manager" in self._src()

    def test_lifecycle_status_endpoint_registered(self):
        assert '"/api/lifecycle"' in self._src()

    def test_lifecycle_purge_endpoint_registered(self):
        assert '"/api/lifecycle/purge"' in self._src()

    def test_lifecycle_ttl_endpoint_registered(self):
        assert '"/api/lifecycle/{store_id}/ttl"' in self._src()

    def test_data_lifecycle_module_exists(self):
        assert (RUNTIME_DIR / "core" / "data_lifecycle_manager.py").exists()

    def test_purge_all_wired(self):
        assert "purge_all" in self._src()

    def test_set_ttl_wired(self):
        assert "set_ttl" in self._src()

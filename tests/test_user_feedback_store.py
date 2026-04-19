"""Tests for User Feedback Store — runtime/core/user_feedback_store.py.

Coverage:
  FeedbackEntry:
  - to_dict() has all required keys
  - default field values

  _validate_rating:
  - "up" accepted
  - "down" accepted
  - invalid raises ValueError
  - case-insensitive normalisation

  _aggregate:
  - empty list returns zeroed stats
  - mixed ratings compute correct positive_rate
  - avg_reward calculated correctly

  UserFeedbackStore.submit():
  - persists entry to JSONL
  - returns FeedbackEntry with correct fields
  - reward mapped correctly for "up"
  - reward mapped correctly for "down"
  - text is truncated to 2000 chars
  - memory_ids stored on entry
  - missing agent_id handled gracefully (no learning engine crash)
  - invalid rating raises ValueError
  - multiple submits accumulate in file

  UserFeedbackStore.get_for_output():
  - returns only entries for requested output_id
  - returns empty list for unknown output_id

  UserFeedbackStore.list_recent():
  - returns newest-first ordering
  - respects limit parameter

  UserFeedbackStore.summary_for_agent():
  - returns correct thumbs_up / thumbs_down counts
  - returns 0s for agent with no feedback

  UserFeedbackStore.summary():
  - includes by_agent breakdown
  - global totals correct

  Integration with LearningEngine:
  - _forward_to_learning_engine calls record_task with correct args
  - errors in LearningEngine are swallowed gracefully

  Integration with MemoryIndex:
  - _forward_to_memory_index calls apply_feedback when memory_ids present
  - skipped when memory_ids is empty

  Integration with AuditEngine:
  - _record_audit is called after submit
  - errors in AuditEngine are swallowed gracefully

  Singleton:
  - get_feedback_store() returns same instance each call

  Server integration (static analysis):
  - _get_feedback_store loader present
  - POST /api/feedback endpoint registered
  - GET /api/feedback/summary endpoint registered
  - GET /api/feedback/recent endpoint registered
  - GET /api/feedback/{output_id} endpoint registered
  - user_feedback_store.py module exists
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT   = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.user_feedback_store import (
    FeedbackEntry,
    UserFeedbackStore,
    _aggregate,
    _validate_rating,
    get_feedback_store,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _store(tmp_path: Path) -> UserFeedbackStore:
    return UserFeedbackStore(path=tmp_path / "user_feedback.jsonl")


def _entry(**kw) -> FeedbackEntry:
    defaults = dict(
        id="fb-001", ts="2026-01-01T00:00:00Z", output_id="out-1",
        rating="up", reward=1.0, agent_id="agent-x", actor="user:alice",
        text="", memory_ids=[], meta={},
    )
    defaults.update(kw)
    return FeedbackEntry(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# FeedbackEntry
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackEntry:
    def test_to_dict_required_keys(self):
        e = _entry()
        d = e.to_dict()
        for key in ("id", "ts", "output_id", "rating", "reward", "agent_id", "actor", "text", "memory_ids", "meta"):
            assert key in d

    def test_defaults_are_correct(self):
        e = _entry()
        assert e.memory_ids == []
        assert e.meta == {}
        assert e.text == ""


# ═══════════════════════════════════════════════════════════════════════════════
# _validate_rating
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRating:
    def test_up_accepted(self):
        assert _validate_rating("up") == "up"

    def test_down_accepted(self):
        assert _validate_rating("down") == "down"

    def test_case_normalised(self):
        assert _validate_rating("UP") == "up"
        assert _validate_rating("Down") == "down"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _validate_rating("neutral")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _validate_rating("")


# ═══════════════════════════════════════════════════════════════════════════════
# _aggregate
# ═══════════════════════════════════════════════════════════════════════════════

class TestAggregate:
    def test_empty_list(self):
        a = _aggregate([])
        assert a["total"] == 0
        assert a["thumbs_up"] == 0
        assert a["thumbs_down"] == 0
        assert a["avg_reward"] == 0.0
        assert a["positive_rate"] == 0.0

    def test_all_up(self):
        entries = [_entry(rating="up", reward=1.0) for _ in range(3)]
        a = _aggregate(entries)
        assert a["thumbs_up"] == 3
        assert a["thumbs_down"] == 0
        assert a["positive_rate"] == 1.0

    def test_all_down(self):
        entries = [_entry(rating="down", reward=-1.0) for _ in range(2)]
        a = _aggregate(entries)
        assert a["thumbs_up"] == 0
        assert a["thumbs_down"] == 2
        assert a["positive_rate"] == 0.0

    def test_mixed(self):
        entries = [
            _entry(rating="up",   reward=1.0),
            _entry(rating="up",   reward=1.0),
            _entry(rating="down", reward=-1.0),
        ]
        a = _aggregate(entries)
        assert a["thumbs_up"] == 2
        assert a["thumbs_down"] == 1
        assert a["total"] == 3
        assert round(a["positive_rate"], 4) == round(2/3, 4)

    def test_avg_reward_mixed(self):
        entries = [
            _entry(rating="up",   reward=1.0),
            _entry(rating="down", reward=-1.0),
        ]
        a = _aggregate(entries)
        assert a["avg_reward"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# UserFeedbackStore.submit
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubmit:
    def test_returns_feedback_entry(self, tmp_path):
        s = _store(tmp_path)
        with patch.object(s, "_forward_to_learning_engine"), \
             patch.object(s, "_forward_to_memory_index"), \
             patch.object(s, "_record_audit"):
            e = s.submit(output_id="out-1", rating="up", agent_id="ag-1", actor="user:bob")
        assert isinstance(e, FeedbackEntry)
        assert e.output_id == "out-1"
        assert e.rating == "up"
        assert e.reward == 1.0
        assert e.agent_id == "ag-1"
        assert e.actor == "user:bob"

    def test_down_reward_is_negative(self, tmp_path):
        s = _store(tmp_path)
        with patch.object(s, "_forward_to_learning_engine"), \
             patch.object(s, "_forward_to_memory_index"), \
             patch.object(s, "_record_audit"):
            e = s.submit(output_id="out-1", rating="down")
        assert e.reward == -1.0

    def test_persists_to_jsonl(self, tmp_path):
        s = _store(tmp_path)
        with patch.object(s, "_forward_to_learning_engine"), \
             patch.object(s, "_forward_to_memory_index"), \
             patch.object(s, "_record_audit"):
            s.submit(output_id="out-1", rating="up")
        lines = [l for l in (tmp_path / "user_feedback.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["output_id"] == "out-1"

    def test_text_truncated(self, tmp_path):
        s = _store(tmp_path)
        long_text = "x" * 5000
        with patch.object(s, "_forward_to_learning_engine"), \
             patch.object(s, "_forward_to_memory_index"), \
             patch.object(s, "_record_audit"):
            e = s.submit(output_id="out-1", rating="up", text=long_text)
        assert len(e.text) == 2000

    def test_memory_ids_stored(self, tmp_path):
        s = _store(tmp_path)
        with patch.object(s, "_forward_to_learning_engine"), \
             patch.object(s, "_forward_to_memory_index"), \
             patch.object(s, "_record_audit"):
            e = s.submit(output_id="out-1", rating="up", memory_ids=["m-1", "m-2"])
        assert e.memory_ids == ["m-1", "m-2"]

    def test_invalid_rating_raises(self, tmp_path):
        s = _store(tmp_path)
        with pytest.raises(ValueError):
            s.submit(output_id="out-1", rating="meh")

    def test_multiple_submits_accumulate(self, tmp_path):
        s = _store(tmp_path)
        for i in range(3):
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                s.submit(output_id=f"out-{i}", rating="up")
        lines = [l for l in (tmp_path / "user_feedback.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 3

    def test_no_agent_id_no_crash(self, tmp_path):
        s = _store(tmp_path)
        with patch.object(s, "_forward_to_learning_engine"), \
             patch.object(s, "_forward_to_memory_index"), \
             patch.object(s, "_record_audit"):
            e = s.submit(output_id="out-1", rating="up", agent_id="")
        assert e.agent_id == ""

    def test_entry_id_is_unique(self, tmp_path):
        s = _store(tmp_path)
        ids = set()
        for _ in range(10):
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                e = s.submit(output_id="out-1", rating="up")
            ids.add(e.id)
        assert len(ids) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# UserFeedbackStore.get_for_output
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetForOutput:
    def _prep(self, tmp_path):
        s = _store(tmp_path)
        for oid in ("out-A", "out-A", "out-B"):
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                s.submit(output_id=oid, rating="up")
        return s

    def test_filters_by_output_id(self, tmp_path):
        s = self._prep(tmp_path)
        entries = s.get_for_output("out-A")
        assert len(entries) == 2
        assert all(e.output_id == "out-A" for e in entries)

    def test_returns_empty_for_unknown(self, tmp_path):
        s = self._prep(tmp_path)
        assert s.get_for_output("out-UNKNOWN") == []


# ═══════════════════════════════════════════════════════════════════════════════
# UserFeedbackStore.list_recent
# ═══════════════════════════════════════════════════════════════════════════════

class TestListRecent:
    def test_returns_newest_first(self, tmp_path):
        s = _store(tmp_path)
        for i in range(5):
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                s.submit(output_id=f"out-{i}", rating="up")
        recent = s.list_recent(limit=5)
        assert recent[0].output_id == "out-4"
        assert recent[-1].output_id == "out-0"

    def test_respects_limit(self, tmp_path):
        s = _store(tmp_path)
        for i in range(10):
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                s.submit(output_id=f"out-{i}", rating="up")
        assert len(s.list_recent(limit=3)) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# UserFeedbackStore.summary_for_agent
# ═══════════════════════════════════════════════════════════════════════════════

class TestSummaryForAgent:
    def test_counts_per_agent(self, tmp_path):
        s = _store(tmp_path)
        ratings = [("up", "ag-1"), ("up", "ag-1"), ("down", "ag-1"), ("up", "ag-2")]
        for r, ag in ratings:
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                s.submit(output_id="out-1", rating=r, agent_id=ag)
        a1 = s.summary_for_agent("ag-1")
        assert a1["thumbs_up"]   == 2
        assert a1["thumbs_down"] == 1
        assert a1["total"]       == 3

    def test_unknown_agent_returns_zeros(self, tmp_path):
        s = _store(tmp_path)
        a = s.summary_for_agent("nonexistent-agent")
        assert a["total"] == 0
        assert a["thumbs_up"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# UserFeedbackStore.summary
# ═══════════════════════════════════════════════════════════════════════════════

class TestSummary:
    def test_global_totals(self, tmp_path):
        s = _store(tmp_path)
        for i in range(4):
            r = "up" if i % 2 == 0 else "down"
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                s.submit(output_id=f"out-{i}", rating=r, agent_id="ag-1")
        sm = s.summary()
        assert sm["total"] == 4
        assert sm["thumbs_up"] == 2
        assert sm["thumbs_down"] == 2

    def test_by_agent_breakdown(self, tmp_path):
        s = _store(tmp_path)
        for ag in ("ag-A", "ag-B"):
            with patch.object(s, "_forward_to_learning_engine"), \
                 patch.object(s, "_forward_to_memory_index"), \
                 patch.object(s, "_record_audit"):
                s.submit(output_id="out-1", rating="up", agent_id=ag)
        sm = s.summary()
        assert "ag-A" in sm["by_agent"]
        assert "ag-B" in sm["by_agent"]


# ═══════════════════════════════════════════════════════════════════════════════
# Learning Engine integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestLearningEngineIntegration:
    def test_record_task_called_with_correct_args(self, tmp_path):
        s = _store(tmp_path)
        entry = _entry(output_id="out-x", rating="up", reward=1.0, agent_id="ag-test")
        mock_eng_instance = MagicMock()
        with patch("core.learning_engine.get_learning_engine", return_value=mock_eng_instance):
            s._forward_to_learning_engine(entry)
        mock_eng_instance.record_task.assert_called_once()
        kwargs = mock_eng_instance.record_task.call_args[1]
        assert kwargs["chosen_agent"] == "ag-test"
        assert kwargs["success_score"] == 1.0

    def test_learning_engine_error_swallowed(self, tmp_path):
        s = _store(tmp_path)
        entry = _entry(agent_id="ag-crash")

        import core.user_feedback_store as _mod
        original = getattr(_mod, "get_learning_engine", None)
        def _boom():
            raise RuntimeError("engine exploded")
        try:
            _mod.get_learning_engine = _boom  # type: ignore
            s._forward_to_learning_engine(entry)  # must not raise
        finally:
            if original is not None:
                _mod.get_learning_engine = original  # type: ignore
            elif hasattr(_mod, "get_learning_engine"):
                del _mod.get_learning_engine

    def test_skipped_when_no_agent_id(self, tmp_path):
        """No call to LearningEngine when agent_id is empty."""
        s = _store(tmp_path)
        entry = _entry(agent_id="")
        called = []

        import core.user_feedback_store as _mod
        original = getattr(_mod, "get_learning_engine", None)
        def _should_not_be_called():
            called.append(True)
            return MagicMock()
        try:
            _mod.get_learning_engine = _should_not_be_called  # type: ignore
            s._forward_to_learning_engine(entry)
        finally:
            if original is not None:
                _mod.get_learning_engine = original  # type: ignore
            elif hasattr(_mod, "get_learning_engine"):
                del _mod.get_learning_engine

        assert called == [], "get_learning_engine should not be called when agent_id is empty"


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryIndex integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryIndexIntegration:
    def test_skipped_when_no_memory_ids(self, tmp_path):
        s = _store(tmp_path)
        entry = _entry(memory_ids=[])
        # Must not call MemoryIndex at all
        import core.user_feedback_store as _mod
        called = []
        original_mi = getattr(_mod, "MemoryIndex", None)
        class _FakeMI:
            def __init__(self, *a, **kw): called.append(True)
            def apply_feedback(self, *a, **kw): pass
        with patch.dict("sys.modules", {"core.memory_index": MagicMock(MemoryIndex=_FakeMI)}):
            s._forward_to_memory_index(entry)
        assert called == []

    def test_apply_feedback_called_with_memory_ids(self, tmp_path):
        s = _store(tmp_path)
        entry = _entry(memory_ids=["m-1", "m-2"], reward=1.0)
        calls = []

        class _FakeMI:
            def __init__(self, *a, **kw): pass
            def apply_feedback(self, mems, reward):
                calls.append({"mems": mems, "reward": reward})

        fake_module = MagicMock()
        fake_module.MemoryIndex = _FakeMI
        fake_module._state_path = lambda: Path("/tmp/fake.json")

        with patch.dict("sys.modules", {"core.memory_index": fake_module}):
            s._forward_to_memory_index(entry)

        assert len(calls) == 1
        assert calls[0]["reward"] == pytest.approx(0.5, abs=0.01)  # damped


# ═══════════════════════════════════════════════════════════════════════════════
# AuditEngine integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditEngineIntegration:
    def test_record_called_after_submit(self, tmp_path):
        s = _store(tmp_path)
        mock_ae = MagicMock()
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae), \
             patch.object(s, "_forward_to_learning_engine"), \
             patch.object(s, "_forward_to_memory_index"):
            s.submit(output_id="out-1", rating="up", agent_id="ag-1")
        mock_ae.record.assert_called_once()
        kwargs = mock_ae.record.call_args[1]
        assert kwargs["action"] == "user_feedback"
        assert kwargs["risk_score"] == pytest.approx(0.05)

    def test_audit_engine_error_swallowed(self, tmp_path):
        s = _store(tmp_path)
        entry = _entry()

        import core.user_feedback_store as _mod
        orig = getattr(_mod, "get_audit_engine", None)
        def _boom():
            raise RuntimeError("audit engine down")
        try:
            _mod.get_audit_engine = _boom  # type: ignore
            s._record_audit(entry)  # must not raise
        finally:
            if orig is not None:
                _mod.get_audit_engine = orig  # type: ignore
            elif hasattr(_mod, "get_audit_engine"):
                del _mod.get_audit_engine


# ═══════════════════════════════════════════════════════════════════════════════
# Thread safety
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_submits(self, tmp_path):
        s = _store(tmp_path)
        errors: list[str] = []
        barrier = threading.Barrier(10)

        def _worker(i):
            barrier.wait()
            try:
                with patch.object(s, "_forward_to_learning_engine"), \
                     patch.object(s, "_forward_to_memory_index"), \
                     patch.object(s, "_record_audit"):
                    s.submit(output_id=f"out-{i}", rating="up" if i % 2 == 0 else "down")
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(s.list_recent(limit=100)) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_same_instance_returned(self):
        a = get_feedback_store()
        b = get_feedback_store()
        assert a is b


# ═══════════════════════════════════════════════════════════════════════════════
# Server integration (static analysis)
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerIntegration:
    def _src(self) -> str:
        return (REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py").read_text()

    def test_feedback_store_loader_defined(self):
        assert "_get_feedback_store" in self._src()

    def test_post_feedback_endpoint(self):
        assert '"/api/feedback"' in self._src()

    def test_get_feedback_summary_endpoint(self):
        assert '"/api/feedback/summary"' in self._src()

    def test_get_feedback_recent_endpoint(self):
        assert '"/api/feedback/recent"' in self._src()

    def test_get_feedback_output_id_endpoint(self):
        assert '"/api/feedback/{output_id}"' in self._src()

    def test_module_exists(self):
        assert (RUNTIME_DIR / "core" / "user_feedback_store.py").exists()

    def test_submit_wired(self):
        assert "store.submit(" in self._src()

    def test_summary_wired(self):
        assert "store.summary()" in self._src()

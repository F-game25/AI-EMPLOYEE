"""Unit tests for runtime/agents/utils.py

Covers every public function:
  - now_iso()           — timestamp format and timezone
  - load_json_safe()    — happy path, missing file, corrupt JSON, custom default
  - save_json_safe()    — write/overwrite, parent mkdir, failure handling
  - append_jsonl_safe() — single append, max_lines trimming, concurrent-safety
  - read_last_jsonl()   — full read, n-limit, missing file, malformed lines
  - _get_file_lock()    — same path returns same lock object (lock identity)
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

# utils.py lives in runtime/agents/ — conftest.py already adds that to sys.path
import utils


# ══════════════════════════════════════════════════════════════════════════════
# now_iso
# ══════════════════════════════════════════════════════════════════════════════

class TestNowIso:
    def test_returns_string(self):
        assert isinstance(utils.now_iso(), str)

    def test_ends_with_z(self):
        ts = utils.now_iso()
        assert ts.endswith("Z"), f"Expected UTC 'Z' suffix, got: {ts}"

    def test_format_parseable(self):
        from datetime import datetime, timezone
        ts = utils.now_iso()
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        assert parsed is not None

    def test_private_alias_matches(self):
        # _now_iso is an alias for now_iso
        assert utils._now_iso is utils.now_iso


# ══════════════════════════════════════════════════════════════════════════════
# load_json_safe
# ══════════════════════════════════════════════════════════════════════════════

class TestLoadJsonSafe:
    def test_load_dict(self, tmp_path):
        p = tmp_path / "data.json"
        payload = {"key": "value", "num": 42}
        p.write_text(json.dumps(payload))
        assert utils.load_json_safe(p) == payload

    def test_load_list(self, tmp_path):
        p = tmp_path / "list.json"
        p.write_text(json.dumps([1, 2, 3]))
        assert utils.load_json_safe(p) == [1, 2, 3]

    def test_missing_file_returns_none_by_default(self, tmp_path):
        assert utils.load_json_safe(tmp_path / "nope.json") is None

    def test_missing_file_returns_custom_default(self, tmp_path):
        assert utils.load_json_safe(tmp_path / "nope.json", default={}) == {}

    def test_corrupt_json_returns_default(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ not valid json !! }")
        assert utils.load_json_safe(p, default=[]) == []

    def test_empty_file_returns_default(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        assert utils.load_json_safe(p, default={"empty": True}) == {"empty": True}

    def test_accepts_string_path(self, tmp_path):
        p = tmp_path / "str.json"
        p.write_text('{"a": 1}')
        assert utils.load_json_safe(str(p)) == {"a": 1}


# ══════════════════════════════════════════════════════════════════════════════
# save_json_safe
# ══════════════════════════════════════════════════════════════════════════════

class TestSaveJsonSafe:
    def test_writes_file(self, tmp_path):
        p = tmp_path / "out.json"
        result = utils.save_json_safe(p, {"x": 1})
        assert result is True
        assert json.loads(p.read_text()) == {"x": 1}

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "file.json"
        utils.save_json_safe(p, [1, 2])
        assert p.exists()

    def test_overwrites_existing(self, tmp_path):
        p = tmp_path / "overwrite.json"
        utils.save_json_safe(p, {"v": 1})
        utils.save_json_safe(p, {"v": 2})
        assert json.loads(p.read_text())["v"] == 2

    def test_returns_false_on_failure(self, tmp_path):
        # Point to a path where we can't write (parent is a file)
        blocker = tmp_path / "blocker"
        blocker.write_text("I am a file, not a dir")
        p = blocker / "file.json"
        result = utils.save_json_safe(p, {})
        assert result is False

    def test_indent_respected(self, tmp_path):
        p = tmp_path / "indented.json"
        utils.save_json_safe(p, {"a": 1}, indent=4)
        raw = p.read_text()
        assert "    " in raw  # 4-space indent

    def test_unicode_preserved(self, tmp_path):
        p = tmp_path / "unicode.json"
        utils.save_json_safe(p, {"emoji": "🚀", "japanese": "日本語"})
        loaded = json.loads(p.read_text(encoding="utf-8"))
        assert loaded["emoji"] == "🚀"

    def test_concurrent_writes_do_not_corrupt(self, tmp_path):
        p = tmp_path / "concurrent.json"
        errors = []

        def writer(val):
            try:
                utils.save_json_safe(p, {"val": val})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # File must be valid JSON after all concurrent writes
        data = json.loads(p.read_text())
        assert "val" in data


# ══════════════════════════════════════════════════════════════════════════════
# append_jsonl_safe
# ══════════════════════════════════════════════════════════════════════════════

class TestAppendJsonlSafe:
    def test_creates_new_file(self, tmp_path):
        p = tmp_path / "log.jsonl"
        result = utils.append_jsonl_safe(p, {"event": "start"})
        assert result is True
        assert p.exists()

    def test_appends_multiple_lines(self, tmp_path):
        p = tmp_path / "multi.jsonl"
        for i in range(5):
            utils.append_jsonl_safe(p, {"i": i})
        lines = [json.loads(l) for l in p.read_text().splitlines() if l]
        assert len(lines) == 5
        assert [l["i"] for l in lines] == list(range(5))

    def test_max_lines_trims(self, tmp_path):
        p = tmp_path / "trim.jsonl"
        for i in range(10):
            utils.append_jsonl_safe(p, {"i": i}, max_lines=5)
        lines = [json.loads(l) for l in p.read_text().splitlines() if l]
        assert len(lines) == 5
        # Most recent entries kept
        assert lines[-1]["i"] == 9

    def test_max_lines_zero_means_no_trim(self, tmp_path):
        p = tmp_path / "notrim.jsonl"
        for i in range(20):
            utils.append_jsonl_safe(p, {"i": i}, max_lines=0)
        lines = p.read_text().splitlines()
        assert len(lines) == 20

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "a" / "b" / "c.jsonl"
        utils.append_jsonl_safe(p, {"msg": "hello"})
        assert p.exists()

    def test_concurrent_appends_no_data_loss(self, tmp_path):
        p = tmp_path / "concurrent.jsonl"
        errors = []

        def appender(i):
            try:
                utils.append_jsonl_safe(p, {"i": i})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=appender, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        lines = [l for l in p.read_text().splitlines() if l]
        assert len(lines) == 30


# ══════════════════════════════════════════════════════════════════════════════
# read_last_jsonl
# ══════════════════════════════════════════════════════════════════════════════

class TestReadLastJsonl:
    def test_returns_empty_for_missing_file(self, tmp_path):
        result = utils.read_last_jsonl(tmp_path / "missing.jsonl")
        assert result == []

    def test_reads_all_lines(self, tmp_path):
        p = tmp_path / "all.jsonl"
        entries = [{"n": i} for i in range(10)]
        p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        result = utils.read_last_jsonl(p, n=100)
        assert result == entries

    def test_respects_n_limit(self, tmp_path):
        p = tmp_path / "limited.jsonl"
        entries = [{"n": i} for i in range(20)]
        p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        result = utils.read_last_jsonl(p, n=5)
        assert len(result) == 5
        assert result[-1]["n"] == 19

    def test_skips_malformed_lines(self, tmp_path):
        p = tmp_path / "mixed.jsonl"
        p.write_text('{"ok": 1}\nnot-valid-json\n{"ok": 2}\n')
        result = utils.read_last_jsonl(p)
        assert len(result) == 2
        assert result[0]["ok"] == 1
        assert result[1]["ok"] == 2

    def test_skips_blank_lines(self, tmp_path):
        p = tmp_path / "blanks.jsonl"
        p.write_text('{"a": 1}\n\n\n{"b": 2}\n')
        result = utils.read_last_jsonl(p)
        assert len(result) == 2

    def test_accepts_string_path(self, tmp_path):
        p = tmp_path / "str.jsonl"
        p.write_text('{"x": 9}\n')
        result = utils.read_last_jsonl(str(p))
        assert result == [{"x": 9}]


# ══════════════════════════════════════════════════════════════════════════════
# _get_file_lock (internal — but critical for thread-safety)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetFileLock:
    def test_same_path_same_lock(self, tmp_path):
        p = tmp_path / "locked.json"
        lock1 = utils._get_file_lock(p)
        lock2 = utils._get_file_lock(p)
        assert lock1 is lock2

    def test_different_paths_different_locks(self, tmp_path):
        lock_a = utils._get_file_lock(tmp_path / "a.json")
        lock_b = utils._get_file_lock(tmp_path / "b.json")
        assert lock_a is not lock_b

    def test_string_and_path_same_lock(self, tmp_path):
        p = tmp_path / "x.json"
        lock1 = utils._get_file_lock(p)
        lock2 = utils._get_file_lock(str(p))
        assert lock1 is lock2

    def test_lock_is_threading_lock(self, tmp_path):
        lock = utils._get_file_lock(tmp_path / "check.json")
        assert hasattr(lock, "acquire") and hasattr(lock, "release")

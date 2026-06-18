"""Phase C0 — state foundation: prove FileLock is blocking-with-timeout (no silent
last-writer-wins), the locked writer serializes robustly, and StateStore resolves
the canonical state dir. See docs/SYSTEM_COHERENCE_PLAN.md (C0)."""
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "runtime"))

from core.file_lock import FileLock, read_json_safe, write_json_safe  # noqa: E402


def test_filelock_serializes_concurrent_writers_no_lost_update(tmp_path):
    """20 threads each read-modify-write a counter under FileLock; with the
    blocking lock every increment must survive (== 20). The mid-section sleep
    widens the race window so an unlocked / non-blocking lock would lose updates."""
    p = tmp_path / "counter.json"
    p.write_text(json.dumps({"n": 0}))
    N = 20

    def inc():
        with FileLock(p, timeout=15):
            data = json.loads(p.read_text())
            time.sleep(0.005)  # widen the critical section
            data["n"] += 1
            p.write_text(json.dumps(data))

    threads = [threading.Thread(target=inc) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert json.loads(p.read_text())["n"] == N


def test_filelock_times_out_when_held(tmp_path):
    """A second acquirer must block then raise TimeoutError — not corrupt or
    silently proceed — when the lock is already held."""
    p = tmp_path / "held.json"
    p.write_text("{}")
    held = threading.Event()
    release = threading.Event()

    def holder():
        with FileLock(p, timeout=5):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    assert held.wait(timeout=5)
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        with FileLock(p, timeout=0.3):
            pass
    assert time.monotonic() - t0 >= 0.3  # it actually waited (blocking), not instant-fail
    release.set()
    t.join()


def test_write_json_safe_serializes_datetime(tmp_path):
    """The locked writer must serialize non-JSON-native values (datetime/Path)
    via default=str so StateStore can route through it without regression."""
    p = tmp_path / "dt.json"
    assert write_json_safe(p, {"when": datetime(2026, 6, 18, tzinfo=timezone.utc)})
    assert "2026-06-18" in read_json_safe(p)["when"]


def test_state_store_uses_canonical_dir(tmp_path, monkeypatch):
    """StateStore must resolve the canonical dir (honouring STATE_DIR) and round-trip,
    not write to a repo-local ./state tree."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    import importlib
    import core.state_paths as sp
    importlib.reload(sp)
    import core.state_store as ss
    importlib.reload(ss)
    ss._save_json("c0_probe", {"ok": True})
    assert (tmp_path / "c0_probe.json").exists()
    assert ss._load_json("c0_probe") == {"ok": True}

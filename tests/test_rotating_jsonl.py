"""C0 follow-up — prove the size-bounded JSONL writer caps disk usage so
telemetry.jsonl can no longer grow without limit (the 134MB stray-log class of
bug). See docs/SYSTEM_COHERENCE_PLAN.md C0 backlog."""
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from core import rotating_jsonl  # noqa: E402


def _segments(path: Path):
    return sorted(p for p in path.parent.glob(path.name + "*"))


def test_append_creates_file(tmp_path):
    p = tmp_path / "log.jsonl"
    rotating_jsonl.append(p, {"a": 1})
    lines = p.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"a": 1}


def test_rotation_caps_total_disk(tmp_path):
    p = tmp_path / "telemetry.jsonl"
    # ~60 bytes/record; cap active at 1 KiB, keep 2 backups → ≤ 3 KiB total.
    for i in range(500):
        rotating_jsonl.append(p, {"i": i, "pad": "x" * 40}, max_bytes=1024, backups=2)

    segs = _segments(p)
    # active + at most 2 backups
    assert p in segs
    assert len(segs) <= 3
    total = sum(s.stat().st_size for s in segs)
    assert total <= 1024 * 3 + 256  # bounded; never 500 records' worth

    # Newest data is in the active file; oldest was discarded (not all i present).
    active = p.read_text().splitlines()
    assert active, "active segment must not be empty"
    seen = {json.loads(l)["i"] for s in segs for l in s.read_text().splitlines()}
    assert max(seen) == 499
    assert len(seen) < 500  # proof that old records were dropped


def test_backups_zero_truncates(tmp_path):
    p = tmp_path / "log.jsonl"
    for i in range(200):
        rotating_jsonl.append(p, {"i": i, "pad": "y" * 40}, max_bytes=512, backups=0)
    assert _segments(p) == [p]  # no .1/.2 ever created
    assert p.stat().st_size <= 512 + 128


def test_append_many_single_batch(tmp_path):
    p = tmp_path / "batch.jsonl"
    rotating_jsonl.append_many(p, ({"n": n} for n in range(5)))
    assert len(p.read_text().splitlines()) == 5


def test_no_cap_when_max_bytes_zero(tmp_path):
    p = tmp_path / "log.jsonl"
    for i in range(100):
        rotating_jsonl.append(p, {"i": i}, max_bytes=0, backups=3)
    assert _segments(p) == [p]
    assert len(p.read_text().splitlines()) == 100


def test_concurrent_appends_no_loss_or_corruption(tmp_path):
    p = tmp_path / "log.jsonl"
    n_threads, per = 8, 200

    def worker(tid):
        for i in range(per):
            rotating_jsonl.append(p, {"t": tid, "i": i}, max_bytes=4096, backups=5)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every line across all segments must be valid JSON (no interleaved writes).
    count = 0
    for s in _segments(p):
        for line in s.read_text().splitlines():
            json.loads(line)  # raises on corruption
            count += 1
    # Some old segments were rotated out, but no partial/garbled lines.
    assert count > 0


def test_serializes_non_json_default(tmp_path):
    p = tmp_path / "log.jsonl"
    from datetime import datetime, timezone
    rotating_jsonl.append(p, {"ts": datetime(2026, 6, 30, tzinfo=timezone.utc)})
    rec = json.loads(p.read_text().splitlines()[0])
    assert "2026-06-30" in rec["ts"]

#!/usr/bin/env python3
"""One-time migration: consolidate a repo-local ``./state`` tree into the canonical
state dir (``STATE_DIR`` / ``~/.ai-employee/state``). Part of Coherence Phase C0.

Historically several modules wrote to a repo-local ``./state`` (via
``Path(__file__).parents[N]/"state"``) instead of the canonical dir, splitting
runtime state across two trees. After the C0 code change every module resolves
through ``canonical_state_dir()``; this script moves any data that lived only in
the repo-local tree into the canonical one so nothing is lost.

Safe by construction:
  * dry-run by default — pass ``--apply`` to actually copy.
  * never overwrites without backing up: a canonical file that would be replaced
    is first copied to ``<canonical>/.migrate_backup_<ts>/``.
  * SQLite databases (``*.db`` + ``-wal``/``-shm``) are NOT auto-merged — copying
    one over another loses rows. They are reported for manual handling.
  * canonical wins ties — a repo-local file is only promoted when it is strictly
    newer than its canonical counterpart.

Usage:
    python3 scripts/migrate_state_to_canonical.py            # dry-run report
    python3 scripts/migrate_state_to_canonical.py --apply    # perform migration
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from core.state_paths import canonical_state_dir  # noqa: E402

_DB_SUFFIXES = (".db", ".db-wal", ".db-shm", ".db-journal")


def _is_db(p: Path) -> bool:
    name = p.name
    return any(name.endswith(s) for s in _DB_SUFFIXES)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform the migration (default: dry-run)")
    ap.add_argument("--repo-state", default=str(Path(__file__).resolve().parents[1] / "state"),
                    help="repo-local state dir to migrate FROM")
    args = ap.parse_args()

    src = Path(args.repo_state).resolve()
    dst = canonical_state_dir().resolve()
    print(f"repo-local : {src}")
    print(f"canonical  : {dst}")
    if src == dst:
        print("✓ already one tree (src == canonical) — nothing to do.")
        return 0
    if not src.exists():
        print("✓ no repo-local state dir — nothing to do.")
        return 0

    backup = dst / f".migrate_backup_{time.strftime('%Y%m%dT%H%M%S')}"
    copied, promoted, skipped_db, skipped_older, backed_up = [], [], [], [], []

    for item in sorted(src.rglob("*")):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        if ".migrate_backup_" in str(rel):
            continue
        target = dst / rel
        if _is_db(item):
            skipped_db.append(str(rel))
            continue
        if not target.exists():
            copied.append(str(rel))
            if args.apply:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
            continue
        # both exist — canonical wins unless repo-local is strictly newer
        if item.stat().st_mtime > target.stat().st_mtime + 1:
            promoted.append(str(rel))
            backed_up.append(str(rel))
            if args.apply:
                bpath = backup / rel
                bpath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, bpath)
                shutil.copy2(item, target)
        else:
            skipped_older.append(str(rel))

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'} summary:")
    print(f"  copied (repo-only)      : {len(copied)}")
    print(f"  promoted (repo newer)   : {len(promoted)}  (backed up to {backup if args.apply else '<backup>'})")
    print(f"  skipped (canonical wins): {len(skipped_older)}")
    print(f"  skipped DBs (manual)    : {len(skipped_db)}  {skipped_db if skipped_db else ''}")
    if not args.apply:
        print("\nRe-run with --apply to perform the migration.")
    if skipped_db:
        print("\n⚠ SQLite DBs were NOT migrated (copying loses rows). If the repo-local DB is")
        print("  authoritative, stop the stack and move it manually, or keep canonical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

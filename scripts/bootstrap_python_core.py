#!/usr/bin/env python3
"""Create the first-boot Python core venv from the bundled wheelhouse."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = REPO_ROOT / "runtime" / "requirements-core.txt"
WHEELHOUSE_ROOT = REPO_ROOT / "runtime" / "wheelhouse"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_core_dependencies.py"


def target_tag() -> str:
    return f"{platform.system().lower()}-{platform.machine().lower()}-py{sys.version_info.major}{sys.version_info.minor}"


def default_ai_home() -> Path:
    return Path(os.environ.get("AI_HOME") or os.environ.get("AI_EMPLOYEE_HOME") or (Path.home() / ".ai-employee"))


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_wheelhouse(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if path.exists():
            return path
        raise SystemExit(f"wheelhouse not found: {path}")

    exact = WHEELHOUSE_ROOT / target_tag()
    if exact.exists():
        return exact

    candidates = sorted(
        path for path in WHEELHOUSE_ROOT.iterdir()
        if path.is_dir() and any(child.suffix == ".whl" for child in path.iterdir())
    ) if WHEELHOUSE_ROOT.exists() else []
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        names = ", ".join(path.name for path in candidates)
        raise SystemExit(f"multiple wheelhouses found; set AI_EMPLOYEE_WHEELHOUSE_DIR or --wheelhouse: {names}")
    raise SystemExit(f"no bundled wheelhouse found under {WHEELHOUSE_ROOT}")


def validate_wheelhouse(wheelhouse: Path) -> None:
    manifest_path = wheelhouse / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"wheelhouse manifest missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"wheelhouse manifest invalid: {exc}")

    expected_target = target_tag()
    manifest_target = manifest.get("target")
    if manifest_target and manifest_target != expected_target:
        raise SystemExit(
            f"wheelhouse target mismatch: current={expected_target}, manifest={manifest_target}"
        )

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit(f"wheelhouse manifest has no files: {manifest_path}")

    for item in files:
        filename = item.get("file")
        expected_sha = item.get("sha256")
        expected_size = item.get("size")
        if not filename or not expected_sha:
            raise SystemExit(f"wheelhouse manifest entry is incomplete: {item}")
        file_path = wheelhouse / filename
        if not file_path.is_file():
            raise SystemExit(f"wheelhouse file missing: {file_path}")
        if expected_size is not None and file_path.stat().st_size != int(expected_size):
            raise SystemExit(f"wheelhouse file size mismatch: {file_path}")
        actual_sha = sha256(file_path)
        if actual_sha != expected_sha:
            raise SystemExit(f"wheelhouse sha256 mismatch: {file_path}")


def run(cmd: list[str], quiet: bool = False) -> None:
    if not quiet:
        print("+ " + " ".join(cmd), flush=True)
    subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        check=True,
        stdout=subprocess.DEVNULL if quiet else None,
    )


def marker_data(wheelhouse: Path) -> dict:
    manifest = wheelhouse / "manifest.json"
    return {
        "schema": 1,
        "created_by": "bootstrap_python_core.py",
        "python": sys.version.split()[0],
        "target": target_tag(),
        "requirements_sha256": sha256(REQUIREMENTS),
        "wheelhouse": str(wheelhouse),
        "wheelhouse_manifest_sha256": sha256(manifest) if manifest.exists() else "",
    }


def marker_matches(marker: Path, expected: dict) -> bool:
    try:
        current = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return False
    keys = ["python", "target", "requirements_sha256", "wheelhouse_manifest_sha256"]
    return all(current.get(key) == expected.get(key) for key in keys)


def install_core_venv(venv_dir: Path, wheelhouse: Path, quiet: bool = False) -> Path:
    validate_wheelhouse(wheelhouse)
    expected = marker_data(wheelhouse)
    marker = venv_dir / ".aeternus_python_core.json"
    python = venv_python(venv_dir)

    if python.exists() and marker_matches(marker, expected):
        return python

    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    python = venv_python(venv_dir)
    run([
        str(python),
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "-r",
        str(REQUIREMENTS),
    ], quiet=quiet)
    run([str(python), str(VERIFY_SCRIPT)], quiet=quiet)

    expected["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    marker.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return python


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Python core venv from bundled wheelhouse")
    parser.add_argument("--venv", default=str(default_ai_home() / "python-core"))
    parser.add_argument("--wheelhouse", default=os.environ.get("AI_EMPLOYEE_WHEELHOUSE_DIR"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    wheelhouse = resolve_wheelhouse(args.wheelhouse)
    python = install_core_venv(Path(args.venv).resolve(), wheelhouse, quiet=args.quiet)
    result = {
        "ok": True,
        "python": str(python),
        "venv": str(Path(args.venv).resolve()),
        "wheelhouse": str(wheelhouse),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    elif not args.quiet:
        print(f"[ok] Python core venv ready: {python}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

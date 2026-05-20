#!/usr/bin/env python3
"""Verify the Linux enterprise packaged app resources.

This verifies the built Electron directory package, not just the source tree.
It intentionally checks the offline first-boot contract: bundled Node backend,
frontend dist, Python wheelhouse, browser bundle, bootstrap scripts, manifests
and a clean Python core venv created from the packaged wheelhouse.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_DIR = REPO_ROOT / "launcher" / "dist" / "linux-unpacked"
LINUX_EXECUTABLE_CANDIDATES = [
    "aeternus-nexus",
    "AETERNUS NEXUS",
    "ai-employee-launcher",
]


def ok(message: str) -> None:
    print(f"[✓] {message}", flush=True)


def fail(message: str) -> None:
    print(f"[✗] {message}", flush=True)
    raise SystemExit(1)


def require_file(path: Path, executable: bool = False) -> None:
    if not path.is_file():
        fail(f"missing file: {path}")
    if path.stat().st_size <= 0:
        fail(f"empty file: {path}")
    if executable and not os.access(path, os.X_OK):
        fail(f"file is not executable: {path}")
    ok(f"file present: {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path}")


def require_dir(path: Path) -> None:
    if not path.is_dir():
        fail(f"missing directory: {path}")
    ok(f"directory present: {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path}")


def load_manifest(path: Path) -> dict:
    require_file(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid manifest {path}: {exc}")
    if not data.get("files"):
        fail(f"manifest has no files: {path}")
    return data


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_tag() -> str:
    return f"{platform.system().lower()}-{platform.machine().lower()}-py{sys.version_info.major}{sys.version_info.minor}"


def verify_manifest_files(root: Path, manifest: dict, label: str) -> None:
    files = manifest.get("files", [])
    for item in files:
        rel = item.get("file")
        expected_sha = item.get("sha256")
        expected_size = item.get("size")
        if not rel or not expected_sha:
            fail(f"{label} manifest entry is incomplete: {item}")
        path = root / rel
        if not path.is_file():
            fail(f"{label} file missing: {path}")
        if expected_size is not None and path.stat().st_size != int(expected_size):
            fail(f"{label} size mismatch: {path}")
        if sha256(path) != expected_sha:
            fail(f"{label} sha256 mismatch: {path}")
    ok(f"{label} hashes verified: {len(files)}")


def wheelhouse_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.iterdir()
        if path.is_dir() and any(child.suffix == ".whl" for child in path.iterdir())
    )


def assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            fail(f"port {port} is in use; stop the app before package preflight")
    ok(f"port {port} free")


def find_free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def require_text(path: Path, needle: str, label: str) -> None:
    require_file(path)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        fail(f"cannot read {label}: {exc}")
    if needle not in text:
        fail(f"{label} missing required marker: {needle}")
    ok(f"{label} marker present: {needle}")


def verify_bootstrap(repo_dir: Path, wheelhouse: Path, app_home: Path, node_bin: Path) -> None:
    script = repo_dir / "scripts" / "bootstrap_python_core.py"
    require_file(script)
    verify_port = find_free_port(int(os.environ.get("AETERNUS_PACKAGE_VERIFY_PORT", "18787")))
    env = os.environ.copy()
    env.update({
        "AI_HOME": str(app_home),
        "AI_EMPLOYEE_HOME": str(app_home),
        "AI_EMPLOYEE_PACKAGED": "1",
        "AI_EMPLOYEE_WHEELHOUSE_DIR": str(wheelhouse),
        "AI_EMPLOYEE_NODE_RUN_AS_NODE": "1",
        "NODE_BIN": str(node_bin),
        "PORT": str(verify_port),
        "PROBLEM_SOLVER_UI_PORT": str(verify_port),
    })
    run([str(node_bin), "--version"], cwd=repo_dir, env={**env, "ELECTRON_RUN_AS_NODE": "1"})
    run([sys.executable, str(script), "--quiet", "--json"], cwd=repo_dir, env=env)

    python = app_home / "python-core" / "bin" / "python"
    require_file(python, executable=True)
    run([str(python), str(repo_dir / "scripts" / "verify_core_dependencies.py")], cwd=repo_dir, env=env)

    assert_port_free(verify_port)
    run([str(python), str(repo_dir / "runtime" / "core" / "startup.py"), "--preflight"], cwd=repo_dir, env=env)


def verify_vendor_intake(repo_dir: Path) -> None:
    require_file(repo_dir / "runtime" / "config" / "fork_integration_manifest.json")
    require_file(repo_dir / "runtime" / "config" / "source_trust.json")
    require_dir(repo_dir / "runtime" / "vendor" / "manifests")
    script = repo_dir / "scripts" / "verify_vendor_intake.py"
    require_file(script)
    run([sys.executable, str(script)], cwd=repo_dir)


def verify_package(app_dir: Path, keep_temp: bool = False) -> None:
    resources = app_dir / "resources"
    repo_dir = resources / "repo"
    require_dir(resources)
    require_dir(repo_dir)

    executable = next((app_dir / name for name in LINUX_EXECUTABLE_CANDIDATES if (app_dir / name).is_file()), None)
    if executable is None:
        fail(f"missing Linux app executable; checked: {', '.join(LINUX_EXECUTABLE_CANDIDATES)}")
    require_file(executable, executable=True)
    require_file(repo_dir / "start.sh", executable=True)
    require_file(repo_dir / "stop.sh", executable=True)
    require_file(repo_dir / "backend" / "server.js")
    require_file(repo_dir / "backend" / "package.json")
    require_dir(repo_dir / "backend" / "node_modules")
    require_file(repo_dir / "backend" / "core" / "native-memory-graph.js")
    require_file(repo_dir / "backend" / "routes" / "hybrid-memory-router.js")
    require_text(repo_dir / "backend" / "routes" / "hybrid-memory-router.js", "/graph/maintenance", "native graph maintenance route")
    require_text(repo_dir / "backend" / "routes" / "hybrid-memory-router.js", "/graph/restore", "native graph restore route")
    require_text(repo_dir / "backend" / "routes" / "hybrid-memory-router.js", "/graph/merge", "native graph merge route")
    require_text(repo_dir / "backend" / "core" / "native-memory-graph.js", "RESTORE_NATIVE_GRAPH", "native graph restore approval gate")
    require_text(repo_dir / "backend" / "core" / "native-memory-graph.js", "MERGE_NATIVE_GRAPH", "native graph merge approval gate")
    require_file(repo_dir / "frontend" / "dist" / "index.html")
    require_file(repo_dir / "runtime" / "requirements-core.txt")
    require_file(repo_dir / "runtime" / "config" / "core_dependency_manifest.json")
    require_file(repo_dir / "runtime" / "config" / "fork_integration_manifest.json")
    require_file(repo_dir / "scripts" / "verify_core_dependencies.py")
    require_file(repo_dir / "scripts" / "verify_vendor_intake.py")
    require_file(repo_dir / "scripts" / "bootstrap_python_core.py")

    wheels = wheelhouse_dirs(repo_dir / "runtime" / "wheelhouse")
    if not wheels:
        fail("no packaged Python wheelhouse found")
    exact_wheelhouse = repo_dir / "runtime" / "wheelhouse" / target_tag()
    if exact_wheelhouse not in wheels:
        fail(f"missing wheelhouse for current Python target: {target_tag()}")
    wheelhouse = exact_wheelhouse
    wheel_manifest = load_manifest(wheelhouse / "manifest.json")
    if wheel_manifest.get("target") != target_tag():
        fail(f"wheelhouse manifest target mismatch: {wheel_manifest.get('target')} != {target_tag()}")
    verify_manifest_files(wheelhouse, wheel_manifest, "wheelhouse")
    ok(f"wheelhouse files: {len(wheel_manifest.get('files', []))}")

    browser_manifest = load_manifest(repo_dir / "runtime" / "browsers" / "playwright" / "manifest.json")
    verify_manifest_files(repo_dir / "runtime" / "browsers" / "playwright", browser_manifest, "browser bundle")
    ok(f"browser bundle files: {len(browser_manifest.get('files', []))}")

    forbidden = [
        repo_dir / "state",
        repo_dir / ".git",
        repo_dir / "frontend" / "node_modules",
    ]
    for path in forbidden:
        if path.exists():
            fail(f"forbidden packaged path exists: {path}")
    ok("forbidden mutable/dev paths absent")
    verify_vendor_intake(repo_dir)

    temp_dir = Path(tempfile.mkdtemp(prefix="aeternus-package-verify-"))
    app_home = temp_dir / "user-data"
    try:
        verify_bootstrap(repo_dir, wheelhouse, app_home, executable)
    finally:
        if keep_temp:
            print(f"[i] kept temp app home: {app_home}", flush=True)
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)

    ok("enterprise Linux package resources verified")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=str(DEFAULT_APP_DIR))
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    verify_package(Path(args.app_dir).resolve(), keep_temp=args.keep_temp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

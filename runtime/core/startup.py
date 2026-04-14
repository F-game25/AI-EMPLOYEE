from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

UI_HOST = "127.0.0.1"
UI_PORT = 8787
REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_APP_DIR = REPO_ROOT / "runtime" / "bots" / "problem-solver-ui"
FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
WORKER_POOL_PATH = REPO_ROOT / "runtime" / "core" / "worker_pool.py"


def _ok(message: str) -> None:
    print(f"[✓] {message}", flush=True)


def _fail(message: str) -> None:
    print(f"[✗] {message}", flush=True)
    raise RuntimeError(message)


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        _fail(f"Python 3.10+ required, found {sys.version.split()[0]}")
    _ok(f"Python version OK ({sys.version.split()[0]})")


def check_node_installed() -> None:
    if not shutil.which("node") or not shutil.which("npm"):
        _fail("Node.js and npm must be installed")
    _ok("Node installed")


def check_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((UI_HOST, port)) == 0:
            _fail(f"Port {port} is already in use")
    _ok(f"Port {port} free")


def check_env_variables() -> None:
    configured_port = os.environ.get("PROBLEM_SOLVER_UI_PORT")
    if configured_port and configured_port != str(UI_PORT):
        _fail(f"PROBLEM_SOLVER_UI_PORT must be {UI_PORT}, got {configured_port}")
    try:
        __import__("fastapi")
        __import__("uvicorn")
    except Exception as exc:
        _fail(f"Missing backend dependency: {exc}")
    _ok("Environment variables OK")


def check_frontend_build() -> None:
    if (FRONTEND_DIST / "index.html").exists():
        _ok("Frontend build found")
        return

    print("[•] Frontend dist missing, running npm install + npm run build", flush=True)
    try:
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, check=True)
    except subprocess.CalledProcessError as exc:
        _fail(f"Frontend build failed: {exc}")

    if not (FRONTEND_DIST / "index.html").exists():
        _fail("Frontend dist/index.html is still missing after rebuild")
    _ok("Frontend build found")


def check_database() -> None:
    ai_home = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
    state_dir = ai_home / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    probe = state_dir / ".startup_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        _fail(f"Database/state directory unavailable: {exc}")
    _ok("Database ready")


def start_worker_pool() -> subprocess.Popen[str]:
    if not WORKER_POOL_PATH.exists():
        _fail(f"Worker pool script missing: {WORKER_POOL_PATH}")
    proc = subprocess.Popen([sys.executable, str(WORKER_POOL_PATH)], text=True)
    time.sleep(0.5)
    if proc.poll() is not None:
        _fail("Worker pool failed to start")
    _ok("Worker pool started")
    return proc


def start_server() -> subprocess.Popen[str]:
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    runtime_path = str(REPO_ROOT / "runtime")
    env["PYTHONPATH"] = f"{runtime_path}:{current_pythonpath}" if current_pythonpath else runtime_path
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(BOT_APP_DIR),
            "--host",
            UI_HOST,
            "--port",
            str(UI_PORT),
        ],
        text=True,
        env=env,
    )
    time.sleep(1.0)
    if proc.poll() is not None:
        _fail("Server failed to start")
    _ok("Server started")
    return proc


def verify_ui_access(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"http://{UI_HOST}:{UI_PORT}/health", timeout=1.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("status") != "ok":
                    raise RuntimeError("/health response invalid")
            with urlopen(f"http://{UI_HOST}:{UI_PORT}/", timeout=1.0) as resp:
                if resp.status != 200:
                    raise RuntimeError("UI root not reachable")
            _ok(f"UI reachable at http://localhost:{UI_PORT}")
            return
        except (URLError, RuntimeError):
            time.sleep(0.5)
    _fail("UI not reachable after startup")


def _terminate(proc: subprocess.Popen[str] | None) -> None:
    if not proc or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def startup_sequence() -> tuple[subprocess.Popen[str], subprocess.Popen[str]]:
    check_python_version()
    check_node_installed()
    check_port_available(UI_PORT)
    check_env_variables()
    check_frontend_build()
    check_database()
    worker_proc = start_worker_pool()
    server_proc = start_server()
    verify_ui_access()
    start_evolution_controller()
    return server_proc, worker_proc


def start_evolution_controller() -> None:
    """Start the autonomous evolution loop using the EVOLUTION_MODE env var.

    Valid values for EVOLUTION_MODE:
      OFF   — disabled (default when the var is unset).
      SAFE  — analyse & generate patches but require explicit API approval.
      AUTO  — fully autonomous: detect, patch, validate, and deploy with no
              human in the loop.

    Set EVOLUTION_MODE=AUTO in ~/.ai-employee/credentials/.env for fully
    unsupervised production self-healing.
    """
    mode = os.environ.get("EVOLUTION_MODE", "OFF").upper().strip()
    if mode == "OFF":
        _ok("Evolution controller: mode OFF (set EVOLUTION_MODE=AUTO or SAFE to enable)")
        return

    runtime_path = str(REPO_ROOT / "runtime")
    env = os.environ.copy()
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{runtime_path}:{current}" if current else runtime_path

    try:
        sys.path.insert(0, runtime_path)
        from core.self_evolution.evolution_controller import get_evolution_controller
        ctrl = get_evolution_controller()
        ctrl.set_mode(mode)
        ctrl.start()
        _ok(f"Evolution controller started (mode={mode})")
    except Exception as exc:
        # Non-fatal: log and continue; the rest of the stack still starts.
        print(f"[!] Evolution controller failed to start: {exc}", flush=True)


def run_preflight() -> None:
    check_python_version()
    check_node_installed()
    check_port_available(UI_PORT)
    check_env_variables()
    check_frontend_build()
    check_database()


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Employee startup orchestration")
    parser.add_argument("--preflight", action="store_true", help="Run checks only without starting services")
    args = parser.parse_args()

    if args.preflight:
        run_preflight()
        return 0

    server_proc = None
    worker_proc = None
    try:
        server_proc, worker_proc = startup_sequence()
        print("[•] Services running. Press Ctrl+C to stop.", flush=True)
        while True:
            if server_proc.poll() is not None:
                _fail("Server process exited unexpectedly")
            if worker_proc.poll() is not None:
                _fail("Worker pool process exited unexpectedly")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[•] Shutdown requested", flush=True)
    finally:
        _terminate(server_proc)
        _terminate(worker_proc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

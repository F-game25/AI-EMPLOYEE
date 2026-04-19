"""
run_system.py — Start the ASCEND AI system (backend + frontend).

Usage:
    python run_system.py [--frontend-only | --backend-only] [--no-wait]

The script:
  1. Builds the React frontend (if not already built) and starts the FastAPI
     backend on port 8787.  The backend serves the built static UI, so a
     single process serves both API and UI.
  2. Polls /api/health until the API is responsive.
  3. Performs a basic UI load-check (GET /) and prints the result.

Environment variables respected:
  ASCEND_PORT          — backend port (default 8787)
  SKIP_FRONTEND_BUILD  — set to "1" to skip the npm build step
  FRONTEND_DEV         — set to "1" to start Vite dev server instead of build
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
ASCEND_ROOT = REPO_ROOT / "ascend-ai"
BACKEND_DIR = ASCEND_ROOT / "backend"
FRONTEND_DIR = ASCEND_ROOT / "frontend"
STATIC_DIR = BACKEND_DIR / "static"

PORT = int(os.environ.get("ASCEND_PORT", 8787))
VITE_PORT = 5173

HEALTH_URL = f"http://127.0.0.1:{PORT}/api/health"
UI_URL = f"http://127.0.0.1:{PORT}/"


# ── Helpers ────────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> int:
    """Run a command, stream output, return exit code."""
    print(f"\n▶ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        print(f"✗ Command failed with exit code {result.returncode}", flush=True)
        sys.exit(result.returncode)
    return result.returncode


def _wait_for_url(url: str, timeout: int = 60, label: str = "") -> bool:
    """Poll *url* until a 2xx response is received or *timeout* seconds pass."""
    label = label or url
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status < 400:
                    print(f"✓ {label} — responsive (attempt {attempt})", flush=True)
                    return True
        except Exception:
            pass
        print(f"  … waiting for {label} (attempt {attempt})", flush=True)
        time.sleep(2)
    print(f"✗ {label} did not respond within {timeout}s", flush=True)
    return False


def build_frontend() -> None:
    """Install npm deps and build the React app into backend/static/."""
    if os.environ.get("SKIP_FRONTEND_BUILD") == "1":
        print("⏩  SKIP_FRONTEND_BUILD=1 — skipping npm build", flush=True)
        return

    if not (FRONTEND_DIR / "node_modules").exists():
        _run(["npm", "install", "--legacy-peer-deps"], cwd=FRONTEND_DIR)

    _run(["npx", "vite", "build", "--outDir", str(STATIC_DIR)], cwd=FRONTEND_DIR)
    print(f"✓ Frontend built → {STATIC_DIR}", flush=True)


def start_backend() -> subprocess.Popen:
    """Launch uvicorn for the ASCEND AI backend. Returns the Popen object."""
    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--reload",
    ]
    print(f"\n▶ Starting backend on port {PORT} …", flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return proc


def start_frontend_dev() -> subprocess.Popen:
    """Launch Vite dev server (used when FRONTEND_DEV=1)."""
    if not (FRONTEND_DIR / "node_modules").exists():
        _run(["npm", "install", "--legacy-peer-deps"], cwd=FRONTEND_DIR)

    cmd = ["npx", "vite", "--port", str(VITE_PORT), "--host"]
    print(f"\n▶ Starting Vite dev server on port {VITE_PORT} …", flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(FRONTEND_DIR),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return proc


def health_check() -> dict:
    """Return the parsed /api/health JSON (or error info)."""
    import json
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"error": str(exc)}


def ui_load_check(url: str = UI_URL) -> bool:
    """Return True if the UI root responds with HTML."""
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            content = resp.read(512).decode("utf-8", errors="replace")
            return "<html" in content.lower() or "<!doctype" in content.lower()
    except Exception:
        return False


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Start the ASCEND AI system")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--backend-only", action="store_true",
                       help="Start backend only (no frontend build)")
    group.add_argument("--frontend-only", action="store_true",
                       help="Build & serve frontend only (no backend spawn)")
    parser.add_argument("--no-wait", action="store_true",
                        help="Skip health-check polling after start")
    parser.add_argument("--frontend-dev", action="store_true",
                        help="Start Vite dev server instead of building")
    args = parser.parse_args()

    processes: list[subprocess.Popen] = []

    try:
        # ── Frontend build / dev server ──────────────────────────────────
        if not args.backend_only:
            if args.frontend_dev or os.environ.get("FRONTEND_DEV") == "1":
                proc = start_frontend_dev()
                processes.append(proc)
            else:
                build_frontend()   # builds static into backend/static/

        # ── Backend ──────────────────────────────────────────────────────
        if not args.frontend_only:
            backend_proc = start_backend()
            processes.append(backend_proc)

        if args.no_wait:
            print("\n✓ System started (--no-wait, skipping health checks)", flush=True)
            # Keep processes alive until Ctrl-C
            while True:
                time.sleep(5)
                for p in processes:
                    if p.poll() is not None:
                        print(f"✗ Process {p.pid} exited unexpectedly", flush=True)
                        sys.exit(1)
            return

        # ── Health checks ─────────────────────────────────────────────
        print("\n⏳ Waiting for backend …", flush=True)
        api_ok = _wait_for_url(HEALTH_URL, timeout=60, label="/api/health")
        if not api_ok:
            print("✗ Backend health check failed — aborting", flush=True)
            sys.exit(1)

        health = health_check()
        print(f"   Health: {health}", flush=True)

        # UI check (only when backend serves static files)
        if not args.backend_only and not (args.frontend_dev or os.environ.get("FRONTEND_DEV") == "1"):
            ui_ok = ui_load_check()
            print(f"   UI load check: {'✓ OK' if ui_ok else '✗ FAILED'}", flush=True)
        elif args.frontend_dev or os.environ.get("FRONTEND_DEV") == "1":
            dev_ui = f"http://127.0.0.1:{VITE_PORT}/"
            ui_ok = _wait_for_url(dev_ui, timeout=30, label="Vite dev server")
            print(f"   UI load check (dev): {'✓ OK' if ui_ok else '✗ FAILED'}", flush=True)

        print("\n🚀 ASCEND AI system is running.", flush=True)
        print(f"   API:   {HEALTH_URL}", flush=True)
        print(f"   UI:    {UI_URL}", flush=True)

        # Keep alive until Ctrl-C
        while True:
            time.sleep(5)
            for p in processes:
                if p.poll() is not None:
                    print(f"✗ Process {p.pid} exited unexpectedly", flush=True)
                    sys.exit(1)

    except KeyboardInterrupt:
        print("\n⏹ Shutting down …", flush=True)
    finally:
        for p in processes:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("✓ All processes stopped.", flush=True)


if __name__ == "__main__":
    main()

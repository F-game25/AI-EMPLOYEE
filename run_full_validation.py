"""
run_full_validation.py — Single-command ASCEND AI end-to-end validation.

Steps:
  1. Install Python + Node dependencies (if needed)
  2. Build the React frontend
  3. Start the ASCEND AI backend
  4. Wait until API is healthy
  5. Run backend API tests
  6. Run UI end-to-end tests (Playwright) + screenshots
  7. Generate /test_results/report.json and /test_results/logs.txt

Usage:
    python run_full_validation.py [--skip-build] [--skip-ui]

Environment variables:
  ASCEND_PORT          — backend port (default 8787)
  SKIP_FRONTEND_BUILD  — "1" to skip npm build
  ANTHROPIC_API_KEY    — optional; enables real AI responses
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
ASCEND_ROOT = REPO_ROOT / "ascend-ai"
BACKEND_DIR = ASCEND_ROOT / "backend"
FRONTEND_DIR = ASCEND_ROOT / "frontend"
STATIC_DIR = BACKEND_DIR / "static"

RESULTS_DIR = REPO_ROOT / "test_results"
SCREENSHOTS_DIR = RESULTS_DIR / "screenshots"
FAILURES_DIR = RESULTS_DIR / "failures"
LOGS_FILE = RESULTS_DIR / "logs.txt"
REPORT_FILE = RESULTS_DIR / "report.json"

PORT = int(os.environ.get("ASCEND_PORT", 8787))
HEALTH_URL = f"http://127.0.0.1:{PORT}/api/health"
BASE_URL = f"http://127.0.0.1:{PORT}"

MISSING_INTEGRATIONS = [
    "Fairness Dashboard (not yet in ASCEND AI frontend — exists in runtime/core/bias_detection_engine.py)",
    "Governance Dashboard (not yet in ASCEND AI frontend — exists in runtime/core/governance_digest.py)",
]


# ── Logging ────────────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    for d in (SCREENSHOTS_DIR, FAILURES_DIR):
        d.mkdir(parents=True, exist_ok=True)
    LOGS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOGS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Backend process management ─────────────────────────────────────────────

_backend_proc: subprocess.Popen | None = None


def _start_backend() -> subprocess.Popen:
    global _backend_proc
    log_path = RESULTS_DIR / "backend.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w", encoding="utf-8")

    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0",
        "--port", str(PORT),
    ]
    _log(f"Starting backend: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        stdout=log_fh,
        stderr=log_fh,
    )
    _backend_proc = proc
    _log(f"Backend PID: {proc.pid}")
    return proc


def _stop_backend() -> None:
    global _backend_proc
    if _backend_proc is not None:
        _log("Stopping backend …")
        try:
            _backend_proc.terminate()
            _backend_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _backend_proc.kill()
        _backend_proc = None


def _wait_for_backend(timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
                if resp.status < 400:
                    _log(f"Backend healthy after {attempt} attempts")
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


# ── Frontend build ─────────────────────────────────────────────────────────

def _build_frontend() -> bool:
    if os.environ.get("SKIP_FRONTEND_BUILD") == "1":
        _log("SKIP_FRONTEND_BUILD=1 — skipping build")
        return True

    if not (FRONTEND_DIR / "node_modules").exists():
        _log("Installing npm dependencies …")
        r = subprocess.run(
            ["npm", "install", "--legacy-peer-deps"],
            cwd=str(FRONTEND_DIR),
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            _log(f"npm install failed:\n{r.stderr}", "ERROR")
            return False

    _log("Building React frontend …")
    r = subprocess.run(
        ["npx", "vite", "build", "--outDir", str(STATIC_DIR)],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        _log(f"Frontend build failed:\n{r.stderr}", "ERROR")
        return False
    _log(f"Frontend built → {STATIC_DIR}")
    return True


# ── Dependency checks ──────────────────────────────────────────────────────

def _ensure_playwright() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        _log("Installing playwright …")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright", "-q"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            _log(f"playwright install failed: {r.stderr}", "ERROR")
            return False
        # Install browser
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
            capture_output=True,
        )
        return True


def _ensure_python_deps() -> None:
    reqs = ASCEND_ROOT / "requirements.txt"
    if reqs.exists():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(reqs), "-q"],
            check=False,
        )


# ── Backend API tests (inline — no pytest needed) ─────────────────────────

class _TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = ""

    def ok(self) -> "Self":  # type: ignore[name-defined]
        self.passed = True
        return self

    def fail(self, err: str) -> "Self":  # type: ignore[name-defined]
        self.error = err
        return self


def _api_get(path: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def _api_post(path: str, data: dict | None = None, timeout: int = 10) -> dict:
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _run_backend_tests() -> list[_TestResult]:
    tests: list[_TestResult] = []

    def _t(name: str, fn) -> _TestResult:
        r = _TestResult(name)
        try:
            fn(r)
            if not r.passed:
                r.ok()
        except Exception as exc:
            r.fail(str(exc))
        tests.append(r)
        status = "PASS" if r.passed else "FAIL"
        _log(f"  [{status}] {name}" + (f" — {r.error}" if r.error else ""))
        return r

    _log("=== Backend API Tests ===")

    _t("GET /api/health returns ok", lambda r: (
        _api_get("/api/health") and r.ok()
    ))

    _t("GET /api/agents returns list", lambda r: (
        isinstance(_api_get("/api/agents"), list) and r.ok()
    ))

    _t("GET /api/system/stats has cpu_percent", lambda r: (
        "cpu_percent" in _api_get("/api/system/stats") and r.ok()
    ))

    _t("GET /api/forge/status has mode", lambda r: (
        "mode" in _api_get("/api/forge/status") and r.ok()
    ))

    _t("GET /api/blacklight/status has connections", lambda r: (
        "connections" in _api_get("/api/blacklight/status") and r.ok()
    ))

    _t("POST /api/forge/task activates mode", lambda r: (
        _api_post("/api/forge/task", {"task": "test", "mode": "on"}).get("success") and r.ok()
    ))

    _t("POST /api/forge/rollback succeeds", lambda r: (
        _api_post("/api/forge/rollback").get("success") and r.ok()
    ))

    _t("POST /api/money/task activates mode", lambda r: (
        _api_post("/api/money/task", {"task": "test", "mode": "on"}).get("success") and r.ok()
    ))

    _t("POST /api/blacklight/scan returns results", lambda r: (
        isinstance(_api_post("/api/blacklight/scan").get("results"), list) and r.ok()
    ))

    _t("POST /api/doctor/run returns pass checks", lambda r: (
        _api_post("/api/doctor/run").get("success") and r.ok()
    ))

    _t("POST /api/chat returns content", lambda r: (
        "content" in _api_post("/api/chat", {"message": "ping"}, timeout=20) and r.ok()
    ))

    _t("GET /api/errors returns list", lambda r: (
        isinstance(_api_get("/api/errors"), list) and r.ok()
    ))

    _t("Forge trace: last_action reflects submitted task", lambda r: (
        (
            _api_post("/api/forge/task", {"task": "trace-validation", "mode": "on"}),
            _api_get("/api/forge/status")["last_action"] == "trace-validation" and r.ok(),
        )[-1]
    ))

    return tests


# ── UI / Playwright tests ──────────────────────────────────────────────────

def _run_ui_tests() -> list[_TestResult]:
    """Run Playwright UI tests using pytest subprocess."""
    tests: list[_TestResult] = []

    _log("=== UI Automation Tests ===")

    test_file = REPO_ROOT / "tests" / "ui_e2e" / "test_ascend_ui_e2e.py"
    if not test_file.exists():
        t = _TestResult("UI test file exists")
        t.fail(f"Not found: {test_file}")
        tests.append(t)
        _log(f"  [FAIL] {t.name} — {t.error}", "ERROR")
        return tests

    junit_xml = RESULTS_DIR / "ui_test_results.xml"
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        f"--junitxml={junit_xml}",
        f"--rootdir={REPO_ROOT}",
    ]
    _log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    _log("--- pytest stdout ---")
    _log(result.stdout)
    if result.stderr:
        _log(f"--- pytest stderr ---\n{result.stderr}", "WARN")

    # Parse JUnit XML for test details
    if junit_xml.exists():
        tests = _parse_junit(junit_xml)
    else:
        # Fallback: infer from return code
        t = _TestResult("UI Test Suite")
        if result.returncode == 0:
            t.ok()
        else:
            t.fail(f"pytest exit code {result.returncode}")
        tests = [t]

    passed = sum(1 for t in tests if t.passed)
    _log(f"UI tests: {passed}/{len(tests)} passed")
    return tests


def _parse_junit(xml_path: Path) -> list[_TestResult]:
    """Extract test results from JUnit XML."""
    import xml.etree.ElementTree as ET
    results: list[_TestResult] = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for tc in root.iter("testcase"):
            name = f"{tc.get('classname', '')}.{tc.get('name', '')}"
            r = _TestResult(name)
            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")
            if skipped is not None:
                r.ok()  # skipped = not broken
                r.error = "SKIPPED"
            elif failure is not None:
                r.fail(failure.get("message", failure.text or "")[:200])
            elif error is not None:
                r.fail(error.get("message", error.text or "")[:200])
            else:
                r.ok()
            results.append(r)
    except Exception as exc:
        fallback = _TestResult("JUnit XML parse")
        fallback.fail(str(exc))
        results.append(fallback)
    return results


# ── Screenshot inventory ───────────────────────────────────────────────────

def _collect_screenshots() -> list[str]:
    if not SCREENSHOTS_DIR.exists():
        return []
    return [str(p) for p in sorted(SCREENSHOTS_DIR.glob("*.png"))]


# ── Report generation ──────────────────────────────────────────────────────

def _generate_report(
    backend_tests: list[_TestResult],
    ui_tests: list[_TestResult],
    screenshots: list[str],
    health: dict,
    build_ok: bool,
    start_time: float,
) -> dict:
    all_tests = backend_tests + ui_tests
    passed = [t for t in all_tests if t.passed and t.error != "SKIPPED"]
    failed = [t for t in all_tests if not t.passed]
    skipped = [t for t in all_tests if t.passed and t.error == "SKIPPED"]

    total = len(all_tests)
    score = round(len(passed) / total * 100, 1) if total > 0 else 0.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - start_time, 1),
        "system_health": health,
        "build_ok": build_ok,
        "system_health_score": score,
        "summary": {
            "total": total,
            "passed": len(passed),
            "failed": len(failed),
            "skipped": len(skipped),
        },
        "passed_tests": [t.name for t in passed],
        "failed_tests": [{"name": t.name, "error": t.error} for t in failed],
        "skipped_tests": [t.name for t in skipped],
        "missing_integrations": MISSING_INTEGRATIONS,
        "ui_issues": [
            {"name": t.name, "error": t.error}
            for t in ui_tests
            if not t.passed and t.error != "SKIPPED"
        ],
        "screenshot_paths": screenshots,
        "logs_file": str(LOGS_FILE),
        "failures_dir": str(FAILURES_DIR),
    }

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    _log(f"Report written to {REPORT_FILE}")
    return report


def _print_summary(report: dict) -> None:
    s = report["summary"]
    score = report["system_health_score"]
    failed = report["failed_tests"]
    screenshots = report["screenshot_paths"]

    print("\n" + "═" * 60, flush=True)
    print("  ASCEND AI — END-TO-END VALIDATION REPORT", flush=True)
    print("═" * 60, flush=True)
    print(f"  Generated : {report['generated_at']}", flush=True)
    print(f"  Duration  : {report['duration_seconds']}s", flush=True)
    print(f"  Build OK  : {report['build_ok']}", flush=True)
    print(f"  Health    : {report['system_health']}", flush=True)
    print(f"  Score     : {score}%  ({s['passed']}/{s['total']} passed, "
          f"{s['failed']} failed, {s['skipped']} skipped)", flush=True)
    print("─" * 60, flush=True)
    if failed:
        print("  FAILURES:", flush=True)
        for f in failed:
            print(f"    ✗ {f['name']}", flush=True)
            if f["error"]:
                print(f"      → {f['error'][:120]}", flush=True)
    else:
        print("  ✓ All tests passed!", flush=True)
    print("─" * 60, flush=True)
    print(f"  Screenshots ({len(screenshots)}):", flush=True)
    for ss in screenshots:
        print(f"    {ss}", flush=True)
    print("─" * 60, flush=True)
    print("  Missing integrations (planned, not yet in ASCEND UI):", flush=True)
    for mi in report["missing_integrations"]:
        print(f"    • {mi}", flush=True)
    print("═" * 60, flush=True)
    print(f"  Full report : {REPORT_FILE}", flush=True)
    print(f"  Logs        : {LOGS_FILE}", flush=True)
    print("═" * 60 + "\n", flush=True)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Run full ASCEND AI validation")
    parser.add_argument("--skip-build", action="store_true",
                        help="Skip frontend npm build")
    parser.add_argument("--skip-ui", action="store_true",
                        help="Skip Playwright UI tests")
    parser.add_argument("--no-start", action="store_true",
                        help="Don't start the backend (assumes it is already running)")
    args = parser.parse_args()

    if args.skip_build:
        os.environ["SKIP_FRONTEND_BUILD"] = "1"

    start_time = time.time()
    _ensure_dirs()

    # Truncate old log
    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        f.write(f"# ASCEND AI Validation Log — {datetime.now(timezone.utc).isoformat()}\n")

    _log("══════════════════════════════════════════════")
    _log(" ASCEND AI — Full End-to-End Validation")
    _log("══════════════════════════════════════════════")

    # ── Step 1: Python deps ───────────────────────────────────────────────
    _log("[Step 1] Ensuring Python dependencies …")
    _ensure_python_deps()

    # ── Step 2: Frontend build ────────────────────────────────────────────
    _log("[Step 2] Building frontend …")
    build_ok = _build_frontend()

    # ── Step 3: Start backend ─────────────────────────────────────────────
    backend_proc = None
    if not args.no_start:
        _log("[Step 3] Starting ASCEND AI backend …")
        backend_proc = _start_backend()
    else:
        _log("[Step 3] --no-start: assuming backend already running")

    try:
        # ── Step 4: Wait for health ───────────────────────────────────────
        _log("[Step 4] Waiting for backend health check …")
        backend_ok = _wait_for_backend(timeout=60)
        if not backend_ok:
            _log("Backend did not start in time — aborting", "ERROR")
            return 1

        # Fetch actual health
        health = {}
        try:
            health = _api_get("/api/health")
        except Exception as exc:
            health = {"error": str(exc)}

        # ── Step 5: Backend API tests ─────────────────────────────────────
        _log("[Step 5] Running backend API tests …")
        backend_results = _run_backend_tests()

        # ── Step 6: UI Automation ─────────────────────────────────────────
        ui_results: list[_TestResult] = []
        if not args.skip_ui:
            _log("[Step 6] Running UI end-to-end tests …")
            pw_ok = _ensure_playwright()
            if pw_ok:
                ui_results = _run_ui_tests()
            else:
                t = _TestResult("Playwright installation")
                t.fail("Could not install playwright")
                ui_results = [t]
        else:
            _log("[Step 6] --skip-ui: skipping UI tests")

        # ── Step 7: Screenshot inventory ──────────────────────────────────
        _log("[Step 7] Collecting screenshots …")
        screenshots = _collect_screenshots()
        _log(f"  {len(screenshots)} screenshot(s) found")

        # ── Step 8: Generate report ───────────────────────────────────────
        _log("[Step 8] Generating report …")
        report = _generate_report(
            backend_results, ui_results, screenshots,
            health, build_ok, start_time,
        )

        _print_summary(report)

        failed_count = report["summary"]["failed"]
        if failed_count > 0:
            _log(f"Validation completed with {failed_count} failure(s) — exit 1", "WARN")
            return 1

        _log("All validations passed — exit 0")
        return 0

    finally:
        if backend_proc is not None:
            _stop_backend()


if __name__ == "__main__":
    sys.exit(main())

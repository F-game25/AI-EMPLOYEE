#!/usr/bin/env python3
"""Full QA validation runner for the AI Employee platform.

This is the single entrypoint that:
1. Runs all backend/unit tests via pytest
2. Runs UI automation with screenshot capture (if server is available)
3. Generates a system health report
4. Outputs a clear summary

Usage:
    python run_full_tests.py [--ui-url URL] [--skip-ui] [--skip-backend]

Environment variables:
    UI_BASE_URL   — override the default UI URL (http://127.0.0.1:8787)
    PORT          — backend port (default 8787)
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
TESTS_DIR = REPO_ROOT / "tests"
RESULTS_DIR = REPO_ROOT / "test_results"
SCREENSHOTS_DIR = RESULTS_DIR / "screenshots"
FAILURES_DIR = RESULTS_DIR / "failures"
LOGS_FILE = RESULTS_DIR / "logs.txt"
REPORT_FILE = RESULTS_DIR / "system_report.json"

BACKEND_PORT = int(os.environ.get("PORT", 8787))
UI_BASE_URL = os.environ.get("UI_BASE_URL", f"http://127.0.0.1:{BACKEND_PORT}")


def _ensure_dirs() -> None:
    for d in (RESULTS_DIR, SCREENSHOTS_DIR, FAILURES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOGS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _server_reachable(port: int = BACKEND_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Backend tests
# ─────────────────────────────────────────────────────────────────────────────

def run_backend_tests() -> dict:
    """Run all pytest test files and return results."""
    _log("=" * 60)
    _log("RUNNING BACKEND TESTS (pytest)")
    _log("=" * 60)

    test_files = [
        "test_ui.py",
        "test_agents.py",
        "test_memory.py",
        "test_forge.py",
        "test_api.py",
        "test_security.py",
        "test_economy.py",
    ]

    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "details": [],
    }

    for tf in test_files:
        test_path = TESTS_DIR / tf
        if not test_path.exists():
            _log(f"  SKIP: {tf} not found")
            results["skipped"] += 1
            continue

        _log(f"  Running: {tf}")
        try:
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pytest",
                    str(test_path),
                    "-v",
                    "--tb=short",
                    "--no-header",
                    "--no-cov",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(REPO_ROOT),
            )
            output = proc.stdout + proc.stderr

            # Parse pytest output for counts
            passed = output.count(" PASSED")
            failed = output.count(" FAILED")
            errored = output.count(" ERROR")
            skipped = output.count(" SKIPPED")

            results["passed"] += passed
            results["failed"] += failed
            results["errors"] += errored
            results["skipped"] += skipped
            results["total"] += passed + failed + errored + skipped

            status = "PASS" if proc.returncode == 0 else "FAIL"
            results["details"].append({
                "file": tf,
                "status": status,
                "return_code": proc.returncode,
                "passed": passed,
                "failed": failed,
                "errors": errored,
                "skipped": skipped,
            })
            _log(f"    {status}: {passed} passed, {failed} failed, {skipped} skipped")

            if proc.returncode != 0:
                # Log failed output
                with open(FAILURES_DIR / f"{tf}.log", "w", encoding="utf-8") as f:
                    f.write(output)

        except subprocess.TimeoutExpired:
            _log(f"    TIMEOUT: {tf}")
            results["errors"] += 1
            results["total"] += 1
            results["details"].append({"file": tf, "status": "TIMEOUT"})
        except Exception as e:
            _log(f"    ERROR: {tf}: {e}")
            results["errors"] += 1
            results["total"] += 1
            results["details"].append({"file": tf, "status": "ERROR", "error": str(e)})

    return results


# ─────────────────────────────────────────────────────────────────────────────
# UI Automation
# ─────────────────────────────────────────────────────────────────────────────

def run_ui_automation(base_url: str = UI_BASE_URL) -> dict:
    """Run the UI screenshot automation suite."""
    _log("=" * 60)
    _log("RUNNING UI AUTOMATION + SCREENSHOTS")
    _log("=" * 60)

    if not _server_reachable():
        _log("  SKIP: Backend server not reachable — skipping UI automation")
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": True,
            "reason": "server_not_reachable",
            "screenshot_paths": [],
            "failures": [],
        }

    try:
        # Add the repo root to path so imports work
        sys.path.insert(0, str(REPO_ROOT))
        from tests.ui_automation.screenshot_runner import run_screenshot_suite, generate_summary

        results = run_screenshot_suite(base_url=base_url)
        summary = generate_summary(results)

        _log(f"  UI tests: {summary['passed']}/{summary['total']} passed")
        if summary["failures"]:
            for f in summary["failures"]:
                _log(f"  FAIL: {f['label']} — {f['error']}")

        return summary

    except ImportError:
        _log("  SKIP: playwright not installed — skipping UI automation")
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": True,
            "reason": "playwright_not_installed",
            "screenshot_paths": [],
            "failures": [],
        }
    except Exception as e:
        _log(f"  ERROR: UI automation failed: {e}")
        traceback.print_exc()
        return {
            "total": 0,
            "passed": 0,
            "failed": 1,
            "error": str(e),
            "screenshot_paths": [],
            "failures": [{"page": "__runner__", "error": str(e)}],
        }


# ─────────────────────────────────────────────────────────────────────────────
# System health checks
# ─────────────────────────────────────────────────────────────────────────────

def run_system_health_checks() -> dict:
    """Run direct Python-level system health checks."""
    _log("=" * 60)
    _log("RUNNING SYSTEM HEALTH CHECKS")
    _log("=" * 60)

    checks: dict = {}
    runtime_dir = REPO_ROOT / "runtime"
    if str(runtime_dir) not in sys.path:
        sys.path.insert(0, str(runtime_dir))

    # Check 1: Agent controller
    try:
        from core.agent_controller import AgentController
        ac = AgentController()
        checks["agent_controller"] = {"status": "ok", "has_planner": hasattr(ac, "planner")}
        _log("  ✓ Agent controller: OK")
    except Exception as e:
        checks["agent_controller"] = {"status": "error", "error": str(e)}
        _log(f"  ✗ Agent controller: {e}")

    # Check 2: Memory index
    try:
        from core.memory_index import get_memory_index
        mi = get_memory_index()
        mi.add_memory("health check entry", importance=0.5)
        results = mi.get_relevant_memories("health check", top_k=1)
        checks["memory_system"] = {"status": "ok", "entries_found": len(results)}
        _log("  ✓ Memory system: OK")
    except Exception as e:
        checks["memory_system"] = {"status": "error", "error": str(e)}
        _log(f"  ✗ Memory system: {e}")

    # Check 3: Audit engine
    try:
        from core.audit_engine import AuditEngine
        ae = AuditEngine()
        event = ae.record(actor="health_check", action="system_test")
        checks["audit_engine"] = {"status": "ok", "event_id": event.get("id")}
        _log("  ✓ Audit engine: OK")
    except Exception as e:
        checks["audit_engine"] = {"status": "error", "error": str(e)}
        _log(f"  ✗ Audit engine: {e}")

    # Check 4: Forge
    try:
        from core.ascend_forge import get_ascend_forge_executor
        forge = get_ascend_forge_executor()
        req = forge.submit_change(objective_id="health-check", goal="improve system health")
        checks["ascend_forge"] = {
            "status": "ok",
            "request_id": req.id,
            "risk_level": req.risk_level,
        }
        _log("  ✓ Ascend Forge: OK")
    except Exception as e:
        checks["ascend_forge"] = {"status": "error", "error": str(e)}
        _log(f"  ✗ Ascend Forge: {e}")

    # Check 5: Security layer
    try:
        from core.security_layer import SecurityLayer, MEMORY_WRITE
        sl = SecurityLayer()
        sl.grant("health_check_agent", {MEMORY_WRITE})
        ok = sl.has_permission("health_check_agent", MEMORY_WRITE)
        checks["security_layer"] = {"status": "ok", "permission_check": ok}
        _log("  ✓ Security layer: OK")
    except Exception as e:
        checks["security_layer"] = {"status": "error", "error": str(e)}
        _log(f"  ✗ Security layer: {e}")

    # Check 6: Reliability engine
    try:
        from core.reliability_engine import ReliabilityEngine
        re_eng = ReliabilityEngine()
        status = re_eng.status()
        checks["reliability_engine"] = {
            "status": "ok",
            "stability_score": status.get("stability_score"),
            "forge_frozen": status.get("forge_frozen"),
        }
        _log("  ✓ Reliability engine: OK")
    except Exception as e:
        checks["reliability_engine"] = {"status": "error", "error": str(e)}
        _log(f"  ✗ Reliability engine: {e}")

    # Check 7: Money mode
    try:
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(topic="health check", dry_run=True)
        checks["money_mode"] = {"status": "ok", "pipeline_status": result.get("status")}
        _log("  ✓ Money mode: OK")
    except Exception as e:
        checks["money_mode"] = {"status": "error", "error": str(e)}
        _log(f"  ✗ Money mode: {e}")

    # Check 8: Backend reachability
    if _server_reachable():
        checks["backend_server"] = {"status": "ok", "port": BACKEND_PORT}
        _log(f"  ✓ Backend server: reachable on port {BACKEND_PORT}")
    else:
        checks["backend_server"] = {"status": "not_running", "port": BACKEND_PORT}
        _log(f"  ⚠ Backend server: not reachable on port {BACKEND_PORT}")

    # Calculate health score
    total = len(checks)
    healthy = sum(1 for c in checks.values() if c.get("status") == "ok")
    health_score = round(healthy / total * 100, 1) if total else 0

    return {
        "checks": checks,
        "total_checks": total,
        "healthy": healthy,
        "health_score": health_score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(
    backend_results: dict,
    ui_results: dict,
    health_results: dict,
) -> dict:
    """Combine all results into the final system report."""
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend_tests": backend_results,
        "ui_automation": ui_results,
        "system_health": health_results,
        "summary": {
            "total_tests": backend_results.get("total", 0),
            "passed_tests": backend_results.get("passed", 0),
            "failed_tests": backend_results.get("failed", 0) + backend_results.get("errors", 0),
            "skipped_tests": backend_results.get("skipped", 0),
            "ui_screenshots_captured": len(ui_results.get("screenshot_paths", [])),
            "system_health_score": health_results.get("health_score", 0),
            "healthy_subsystems": health_results.get("healthy", 0),
            "total_subsystems": health_results.get("total_checks", 0),
        },
    }

    # List broken features
    broken: list[str] = []
    for detail in backend_results.get("details", []):
        if detail.get("status") != "PASS":
            broken.append(f"backend:{detail.get('file', 'unknown')}")
    for f in ui_results.get("failures", []):
        broken.append(f"ui:{f.get('page', 'unknown')}")
    for name, check in health_results.get("checks", {}).items():
        if check.get("status") != "ok":
            broken.append(f"health:{name}")

    report["summary"]["broken_features"] = broken
    return report


def print_summary(report: dict) -> None:
    """Print a human-readable summary to stdout."""
    s = report["summary"]
    print()
    print("═" * 60)
    print("  AI EMPLOYEE — QA VALIDATION REPORT")
    print("═" * 60)
    print()
    print(f"  Timestamp:            {report['timestamp']}")
    print()
    print("  ── Backend Tests ──")
    print(f"  Total:                {s['total_tests']}")
    print(f"  Passed:               {s['passed_tests']}")
    print(f"  Failed:               {s['failed_tests']}")
    print(f"  Skipped:              {s['skipped_tests']}")
    print()
    print("  ── UI Automation ──")
    print(f"  Screenshots:          {s['ui_screenshots_captured']}")
    if report["ui_automation"].get("skipped"):
        print(f"  Status:               SKIPPED ({report['ui_automation'].get('reason', '')})")
    print()
    print("  ── System Health ──")
    print(f"  Health Score:         {s['system_health_score']}%")
    print(f"  Healthy Subsystems:   {s['healthy_subsystems']}/{s['total_subsystems']}")
    print()

    if s["broken_features"]:
        print("  ── Broken Features ──")
        for bf in s["broken_features"]:
            print(f"    ✗ {bf}")
        print()

    # Screenshot paths
    ss_paths = report["ui_automation"].get("screenshot_paths", [])
    if ss_paths:
        print("  ── Screenshot Paths ──")
        for sp in ss_paths:
            print(f"    📸 {sp}")
        print()

    # Overall verdict
    if s["failed_tests"] == 0 and s["system_health_score"] >= 80:
        print("  ✅ OVERALL: SYSTEM HEALTHY")
    elif s["system_health_score"] >= 50:
        print("  ⚠️  OVERALL: SYSTEM DEGRADED — review broken features")
    else:
        print("  ❌ OVERALL: SYSTEM UNHEALTHY — immediate attention required")
    print()
    print("═" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="AI Employee QA Validation Runner")
    parser.add_argument("--ui-url", default=UI_BASE_URL, help="Base URL for UI automation")
    parser.add_argument("--skip-ui", action="store_true", help="Skip UI automation tests")
    parser.add_argument("--skip-backend", action="store_true", help="Skip backend pytest tests")
    args = parser.parse_args()

    _ensure_dirs()

    # Clear previous log
    LOGS_FILE.write_text("", encoding="utf-8")

    _log("Starting AI Employee full QA validation")
    _log(f"Repository root: {REPO_ROOT}")
    _log(f"UI URL: {args.ui_url}")
    _log(f"Backend port: {BACKEND_PORT}")

    start = time.time()

    # Phase 1: Backend tests
    if args.skip_backend:
        _log("Skipping backend tests (--skip-backend)")
        backend_results = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "details": []}
    else:
        backend_results = run_backend_tests()

    # Phase 2: UI automation
    if args.skip_ui:
        _log("Skipping UI automation (--skip-ui)")
        ui_results = {"total": 0, "passed": 0, "failed": 0, "skipped": True, "reason": "cli_flag", "screenshot_paths": [], "failures": []}
    else:
        ui_results = run_ui_automation(base_url=args.ui_url)

    # Phase 3: System health checks
    health_results = run_system_health_checks()

    elapsed = round(time.time() - start, 1)
    _log(f"Full validation completed in {elapsed}s")

    # Generate report
    report = generate_report(backend_results, ui_results, health_results)
    report["elapsed_seconds"] = elapsed

    # Save report
    REPORT_FILE.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _log(f"Report saved to {REPORT_FILE}")

    # Print summary
    print_summary(report)

    # Exit code: 0 if no failures, 1 otherwise
    if report["summary"]["failed_tests"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import json
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from core.self_evolution.code_analyzer import CodeAnalyzer
from core.self_evolution.evolution_controller import EvolutionController
from core.self_evolution.patch_validator import PatchValidator
from core.self_evolution.safe_deployer import SafeDeployer


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "backend").mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend" / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "core").mkdir(parents=True, exist_ok=True)

    (tmp_path / "backend" / "server.js").write_text(
        "app.get('/api/brain/status',()=>{});app.get('/api/brain/insights',()=>{});"
        "app.get('/api/brain/activity',()=>{});app.get('/api/brain/neurons',()=>{});",
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "src" / "App.jsx").write_text(
        "fetch('/api/missing/route')",
        encoding="utf-8",
    )
    (tmp_path / "runtime" / "core" / "sample.py").write_text(
        "def alive():\n    return True\n",
        encoding="utf-8",
    )
    return tmp_path


def test_code_analyzer_detects_missing_connection(tmp_path):
    repo = _make_repo(tmp_path)
    analyzer = CodeAnalyzer(repo_root=repo)
    issues = analyzer.scan_full_repo()
    assert isinstance(issues, list)
    assert any(issue["issue_type"] == "missing_connection" for issue in issues)


def test_patch_validator_security_gate_flags_unsafe_line(tmp_path):
    repo = _make_repo(tmp_path)
    validator = PatchValidator(repo_root=repo)
    security = validator._security_scan("+eval('x')\n")
    assert security["ok"] is False
    assert security["issues"]


def test_safe_deployer_respects_mode_off(tmp_path):
    repo = _make_repo(tmp_path)
    deployer = SafeDeployer(repo_root=repo)
    result = deployer.deploy(
        diff_text="diff --git a/runtime/core/sample.py b/runtime/core/sample.py\n--- a/runtime/core/sample.py\n+++ b/runtime/core/sample.py\n@@ -1,2 +1,2 @@\n def alive():\n-    return True\n+    return False\n",
        risk_level="low",
        evolution_mode="OFF",
        tester_gate_passed=True,
    )
    assert result["deployed"] is False
    assert result["reason"] == "evolution_mode_off"


def test_evolution_controller_mode_and_status(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    controller = EvolutionController(repo_root=repo)
    assert controller.set_mode("SAFE") == "SAFE"
    status = controller.status()
    assert status["mode"] == "SAFE"
    controller.set_mode("OFF")
    result = controller.run_once()
    assert result["status"] == "skipped"

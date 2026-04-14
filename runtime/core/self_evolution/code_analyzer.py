from __future__ import annotations

import ast
import py_compile
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CodeIssue:
    file: str
    issue_type: str
    severity: str
    suggested_fix: str

    def to_dict(self) -> dict[str, str]:
        return {
            "file": self.file,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "suggested_fix": self.suggested_fix,
        }


class CodeAnalyzer:
    """Repository analyzer that detects breakages and connection gaps."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or self._detect_repo_root()

    @staticmethod
    def _detect_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "package.json").exists():
                return parent
        return current.parents[3]

    def scan_full_repo(self) -> list[dict[str, str]]:
        py_files = [
            path for path in self._repo_root.rglob("*.py")
            if ".venv" not in path.parts and "node_modules" not in path.parts and "__pycache__" not in path.parts
        ]
        issues: list[CodeIssue] = []
        issues.extend(self._detect_broken_imports(py_files))
        issues.extend(self._detect_unused_code(py_files))
        issues.extend(self._detect_failing_modules(py_files))
        issues.extend(self._detect_performance_bottlenecks(py_files))
        issues.extend(self._detect_missing_connections())
        issues.extend(self._scan_runtime_health())
        uniq: dict[tuple[str, str, str], CodeIssue] = {}
        for issue in issues:
            uniq[(issue.file, issue.issue_type, issue.suggested_fix)] = issue
        return [issue.to_dict() for issue in uniq.values()]

    def _detect_broken_imports(self, py_files: list[Path]) -> list[CodeIssue]:
        issues: list[CodeIssue] = []
        for file_path in py_files:
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    parts = node.module.split(".")
                    if parts[0] in {"core", "brain", "memory", "agents", "actions"}:
                        module_path = Path(*parts)
                        candidate = self._repo_root / "runtime" / module_path
                        candidate_py = (self._repo_root / "runtime" / module_path).with_suffix(".py")
                        if not candidate.exists() and not candidate_py.exists():
                            issues.append(
                                CodeIssue(
                                    file=str(file_path.relative_to(self._repo_root)),
                                    issue_type="broken_import",
                                    severity="high",
                                    suggested_fix=f"Resolve import '{node.module}' to an existing runtime module.",
                                )
                            )
        return issues

    def _detect_unused_code(self, py_files: list[Path]) -> list[CodeIssue]:
        issues: list[CodeIssue] = []
        for file_path in py_files:
            rel = str(file_path.relative_to(self._repo_root))
            if rel.startswith("tests/"):
                continue
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            except Exception:
                continue
            defs: dict[str, ast.AST] = {}
            used: set[str] = set()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                    defs[node.name] = node
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    used.add(node.id)
                elif isinstance(node, ast.Attribute):
                    used.add(node.attr)
            for name in defs:
                if name not in used:
                    issues.append(
                        CodeIssue(
                            file=rel,
                            issue_type="unused_code",
                            severity="low",
                            suggested_fix=f"Remove or integrate unused symbol '{name}'.",
                        )
                    )
        return issues

    def _detect_failing_modules(self, py_files: list[Path]) -> list[CodeIssue]:
        issues: list[CodeIssue] = []
        for file_path in py_files:
            rel = str(file_path.relative_to(self._repo_root))
            try:
                py_compile.compile(str(file_path), doraise=True)
            except Exception as exc:
                issues.append(
                    CodeIssue(
                        file=rel,
                        issue_type="failing_module",
                        severity="critical",
                        suggested_fix=f"Fix syntax/import error: {exc}",
                    )
                )
        return issues

    def _detect_performance_bottlenecks(self, py_files: list[Path]) -> list[CodeIssue]:
        issues: list[CodeIssue] = []
        nested_loop_pattern = re.compile(r"for\s+.+:\n(?:\s{4,}.+\n){0,6}\s{4,}for\s+.+:")
        sleep_pattern = re.compile(r"while\s+.+:\n(?:\s{4,}.+\n){0,8}\s{4,}time\.sleep\(")
        for file_path in py_files:
            rel = str(file_path.relative_to(self._repo_root))
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            if nested_loop_pattern.search(text):
                issues.append(
                    CodeIssue(
                        file=rel,
                        issue_type="performance_bottleneck",
                        severity="medium",
                        suggested_fix="Review nested loops and replace with indexed lookup/caching where possible.",
                    )
                )
            if sleep_pattern.search(text):
                issues.append(
                    CodeIssue(
                        file=rel,
                        issue_type="performance_bottleneck",
                        severity="low",
                        suggested_fix="Avoid blocking while-loop sleep paths; use event-driven scheduling.",
                    )
                )
        return issues

    def _detect_missing_connections(self) -> list[CodeIssue]:
        issues: list[CodeIssue] = []
        backend = self._repo_root / "backend" / "server.js"
        if not backend.exists():
            return [
                CodeIssue(
                    file="backend/server.js",
                    issue_type="missing_connection",
                    severity="critical",
                    suggested_fix="Backend server entrypoint is missing.",
                )
            ]

        backend_text = backend.read_text(encoding="utf-8", errors="replace")
        backend_routes = set(re.findall(r"app\.(?:get|post|put|delete)\('(/api/[^']+)'", backend_text))

        frontend_files = list((self._repo_root / "frontend" / "src").rglob("*.jsx")) + list(
            (self._repo_root / "frontend" / "src").rglob("*.js")
        )
        requested_routes: set[str] = set()
        for file_path in frontend_files:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            requested_routes.update(re.findall(r"/api/[a-zA-Z0-9_\-/]+", text))

        for route in sorted(requested_routes):
            if route not in backend_routes:
                issues.append(
                    CodeIssue(
                        file="frontend/src",
                        issue_type="missing_connection",
                        severity="high",
                        suggested_fix=f"Expose backend route '{route}' or update frontend caller.",
                    )
                )

        required_brain_routes = {
            "/api/brain/status",
            "/api/brain/insights",
            "/api/brain/activity",
            "/api/brain/neurons",
        }
        for route in sorted(required_brain_routes):
            if route not in backend_routes:
                issues.append(
                    CodeIssue(
                        file="backend/server.js",
                        issue_type="missing_connection",
                        severity="critical",
                        suggested_fix=f"Add required brain route '{route}'.",
                    )
                )
        return issues

    def _scan_runtime_health(self) -> list[CodeIssue]:
        """Translate live observability signals into CodeIssue entries.

        Queries the anomaly detector for recent anomalies and the event stream
        for recent ``error_detected`` events.  Each finding becomes a
        ``CodeIssue`` with ``issue_type="runtime_failure"`` so the evolution
        loop can generate a patch for it.
        """
        issues: list[CodeIssue] = []

        # ── Anomaly detector ──────────────────────────────────────────────────
        try:
            from core.observability.anomaly_detector import get_anomaly_detector
            for anomaly in get_anomaly_detector().recent(20):
                severity = (anomaly.get("severity") or "high").lower()
                anomaly_type = anomaly.get("type", "unknown_anomaly")
                payload_str = str(anomaly.get("payload") or "")[:200]
                issues.append(
                    CodeIssue(
                        file="runtime",
                        issue_type="runtime_failure",
                        severity=severity,
                        suggested_fix=(
                            f"Resolve runtime anomaly '{anomaly_type}': {payload_str}"
                        ),
                    )
                )
        except Exception:
            pass

        # ── Event stream: recent error_detected events ────────────────────────
        try:
            from core.observability.event_stream import get_event_stream
            recent_events = get_event_stream().recent(100)
            error_events = [
                e for e in recent_events
                if e.get("event_type") == "error_detected"
            ]
            # Group by anomaly type to avoid duplicate issues.
            seen: set[str] = set()
            for event in error_events:
                payload = event.get("payload") or {}
                anomaly = payload.get("anomaly") or {}
                key = anomaly.get("type") or str(payload)[:60]
                if key in seen:
                    continue
                seen.add(key)
                severity = (anomaly.get("severity") or "high").lower()
                detail = str(payload)[:200]
                issues.append(
                    CodeIssue(
                        file="runtime",
                        issue_type="runtime_failure",
                        severity=severity,
                        suggested_fix=(
                            f"Fix runtime error event '{key}': {detail}"
                        ),
                    )
                )
        except Exception:
            pass

        return issues

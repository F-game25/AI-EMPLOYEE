"""Health Check Agent — system health monitoring and diagnostics.

Checks all services, validates API keys, verifies state file integrity,
measures response times, and returns a health grade with remediation steps.

Commands (via chat):
  health check    — full system health check
  health services — check all running services
  health keys     — validate API keys are configured
  health grade    — letter grade (A/B/C/D) with breakdown
  health fix      — auto-remediation suggestions
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urllib_request

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"

SERVICES = [
    {"name": "Node Backend", "url": "http://localhost:8787/health", "critical": True},
    {"name": "Python AI Backend", "url": "http://localhost:18790/health", "critical": True},
]

REQUIRED_KEYS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
OPTIONAL_KEYS = ["TAVILY_API_KEY", "SERP_API_KEY", "NEWS_API_KEY", "WHATSAPP_TOKEN", "DISCORD_TOKEN"]

STATE_FILES_EXPECTED = ["bus.jsonl", "lead-generator-crm.json"]


class HealthCheckAgent(BaseAgent):
    agent_id = "health-check"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        checks = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "services": self._check_services(),
            "api_keys": self._check_api_keys(),
            "state_files": self._check_state_files(),
            "disk_usage": self._check_disk(),
        }

        score = self._calculate_score(checks)
        grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 55 else "D"
        checks["score"] = score
        checks["grade"] = grade
        checks["summary"] = self._build_summary(checks, grade)
        checks["remediation"] = self._build_remediation(checks)
        checks["tokens_used"] = 0
        return checks

    def _check_services(self) -> list:
        results = []
        for svc in SERVICES:
            t0 = time.time()
            try:
                req = urllib_request.Request(svc["url"])
                with urllib_request.urlopen(req, timeout=3) as resp:
                    status = resp.status
                    ok = status == 200
            except Exception as e:
                ok = False
                status = 0
            ms = round((time.time() - t0) * 1000)
            results.append({
                "name": svc["name"],
                "url": svc["url"],
                "status": "up" if ok else "down",
                "http_code": status,
                "response_ms": ms,
                "critical": svc["critical"],
            })
        return results

    def _check_api_keys(self) -> dict:
        env = {}
        try:
            env_file = AI_HOME / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, _, v = line.partition("=")
                        env[k.strip()] = bool(v.strip())
        except Exception:
            pass

        result = {}
        for key in REQUIRED_KEYS:
            configured = bool(os.environ.get(key) or env.get(key))
            result[key] = {"status": "configured" if configured else "missing", "required": True}
        for key in OPTIONAL_KEYS:
            configured = bool(os.environ.get(key) or env.get(key))
            result[key] = {"status": "configured" if configured else "not set", "required": False}
        return result

    def _check_state_files(self) -> list:
        results = []
        for fname in STATE_FILES_EXPECTED:
            fpath = STATE_DIR / fname
            results.append({
                "file": fname,
                "exists": fpath.exists(),
                "size_bytes": fpath.stat().st_size if fpath.exists() else 0,
            })
        return results

    def _check_disk(self) -> dict:
        try:
            import shutil
            total, used, free = shutil.disk_usage(str(AI_HOME))
            return {"total_gb": round(total / 1e9, 1), "free_gb": round(free / 1e9, 1), "used_percent": round(used / total * 100)}
        except Exception:
            return {}

    def _calculate_score(self, checks: dict) -> int:
        score = 100
        for svc in checks.get("services", []):
            if svc["status"] == "down" and svc.get("critical"):
                score -= 30
            elif svc["status"] == "down":
                score -= 10
        for key, info in checks.get("api_keys", {}).items():
            if info.get("required") and info.get("status") == "missing":
                score -= 20
        return max(0, score)

    def _build_summary(self, checks: dict, grade: str) -> str:
        up = sum(1 for s in checks.get("services", []) if s["status"] == "up")
        total = len(checks.get("services", []))
        return f"Grade {grade}: {up}/{total} services up, score {checks.get('score', 0)}/100"

    def _build_remediation(self, checks: dict) -> list:
        actions = []
        for svc in checks.get("services", []):
            if svc["status"] == "down":
                actions.append(f"Start {svc['name']}: check logs and restart service")
        for key, info in checks.get("api_keys", {}).items():
            if info.get("required") and info.get("status") == "missing":
                actions.append(f"Set {key} in ~/.ai-employee/.env")
        return actions

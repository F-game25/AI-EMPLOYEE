"""API Tester Agent — REST API test suite generation.

Generates HTTP test suites for REST APIs: validates responses, checks auth
and rate limits, tests edge cases, produces Postman-style collections
and security review notes.

Commands (via chat):
  api test       <endpoint>     — generate test cases for an endpoint
  api validate   <spec>         — validate API against OpenAPI spec
  api security   <endpoint>     — security test checklist
  api collection <base_url>     — full Postman-style test collection
  api docs       <endpoint>     — API documentation draft
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a Senior QA Engineer and API Security Specialist. You write comprehensive, production-grade API test suites.

Output JSON with this structure:
{
  "api_endpoint": "...",
  "method": "GET|POST|PUT|PATCH|DELETE",
  "test_suite": {
    "happy_path": [
      {
        "test_name": "...",
        "description": "...",
        "request": {"method": "...", "url": "...", "headers": {}, "body": {}},
        "expected_response": {"status": 200, "body_contains": [], "headers": {}},
        "assertions": ["assertion 1", "assertion 2"]
      }
    ],
    "edge_cases": [],
    "error_cases": [],
    "security_tests": [],
    "performance_tests": []
  },
  "postman_collection": {
    "info": {"name": "...", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
    "item": []
  },
  "security_checklist": [
    {"check": "...", "status": "pass|fail|manual", "recommendation": "..."}
  ],
  "documentation_draft": {
    "endpoint": "...",
    "description": "...",
    "parameters": [],
    "request_body": {},
    "responses": []
  },
  "coverage_score": 0,
  "critical_gaps": ["gap 1", "gap 2"]
}"""


class APITesterAgent(BaseAgent):
    agent_id = "api-tester"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        endpoint = payload.get("endpoint") or payload.get("url", "")
        method = payload.get("method", "GET").upper()
        auth_type = payload.get("auth", "bearer")
        spec = payload.get("spec", "")
        task = payload.get("task", "test")

        if not endpoint and task:
            endpoint = task

        prompt = (
            f"Generate API tests for:\n"
            f"Endpoint: {endpoint}\n"
            f"Method: {method}\n"
            f"Auth type: {auth_type}\n"
            f"OpenAPI spec: {spec[:500] if spec else 'not provided'}\n"
            f"Include: happy path, edge cases, error handling, security checks, rate limiting"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

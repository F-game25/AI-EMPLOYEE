#!/usr/bin/env python3
"""Forge bridge — sandbox testing, rollback, snapshots, system builder.

Usage: echo '{"operation": "snapshots"}' | python3 run_forge.py
"""
import json
import os
import re
import sys
from pathlib import Path

_REPO_DIR = os.environ.get("AI_EMPLOYEE_REPO_DIR", "")
if _REPO_DIR:
    _RUNTIME_DIR = Path(_REPO_DIR) / "runtime"
else:
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    _RUNTIME_DIR = _REPO_ROOT / "runtime"
    if not _RUNTIME_DIR.exists():
        for _candidate in [
            Path.home() / "AI-EMPLOYEE" / "runtime",
            Path("/home/lf/AI-EMPLOYEE/runtime"),
        ]:
            if _candidate.exists():
                _RUNTIME_DIR = _candidate
                break

if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

_ENV_FILE = Path.home() / ".ai-employee" / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

AI_HOME = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        operation = payload.get("operation", "")
    except (json.JSONDecodeError, KeyError) as exc:
        _fail(f"bad_input: {exc}")
        return

    dispatch = {
        "sandbox": _op_sandbox,
        "rollback": _op_rollback,
        "snapshots": _op_snapshots,
        "build_system": _op_build_system,
        "security_scan": _op_security_scan,
        "governance_digest": _op_governance_digest,
        "llm_status": _op_llm_status,
    }
    handler = dispatch.get(operation)
    if handler is None:
        _fail(f"unknown_operation: {operation!r}")
    else:
        handler(payload)


# ── Operations ────────────────────────────────────────────────────────────────

def _op_sandbox(payload: dict) -> None:
    goal = str(payload.get("goal", "")).strip()
    if not goal:
        _fail("sandbox: goal is required")
        return

    try:
        from core.tool_llm_caller import call_llm_for_tool
    except Exception as exc:
        _fail(f"import_llm: {exc}")
        return

    prompt = (
        f"You are a senior Python engineer. Write ONLY valid Python code (no markdown, no explanation) for:\n\n"
        f"{goal}\n\n"
        f"Rules: no exec(), no eval(), no __import__(), no os.system(), no subprocess.\n"
        f"Code:"
    )
    generated_code = call_llm_for_tool(prompt)
    if not generated_code:
        _fail("sandbox: llm_unavailable")
        return

    # Strip markdown code fences
    m = re.search(r"```(?:python)?\s*([\s\S]*?)```", generated_code)
    if m:
        generated_code = m.group(1).strip()

    try:
        from runtime.sandbox_executor import get_sandbox_executor
    except ImportError:
        try:
            from sandbox_executor import get_sandbox_executor
        except Exception as exc:
            _fail(f"import_sandbox: {exc}")
            return

    module_path = str(payload.get("module_path", "forge_sandbox_test"))
    result = get_sandbox_executor().run(code=generated_code, module_name=module_path)

    _out({
        "operation": "sandbox",
        "safe": result.get("safe", False),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
        "generated_code": generated_code,
        "duration_ms": result.get("duration_ms", 0),
    })


def _op_rollback(payload: dict) -> None:
    snapshot_id = str(payload.get("snapshot_id", "")).strip()
    if not snapshot_id:
        _fail("rollback: snapshot_id is required")
        return

    try:
        from runtime.version_control import get_version_control
    except ImportError:
        try:
            from version_control import get_version_control
        except Exception as exc:
            _fail(f"import_version_control: {exc}")
            return

    result = get_version_control().rollback(snapshot_id)
    _out({"operation": "rollback", **result})


def _op_snapshots(payload: dict) -> None:
    try:
        from runtime.version_control import get_version_control
    except ImportError:
        try:
            from version_control import get_version_control
        except Exception as exc:
            _fail(f"import_version_control: {exc}")
            return

    vc = get_version_control()
    raw = vc.list_versions(limit=50)
    summary = vc.summary() if hasattr(vc, "summary") else {}

    slim = [{
        "id": s.get("id"),
        "module": s.get("module"),
        "description": s.get("description"),
        "tag": s.get("tag"),
        "author": s.get("author"),
        "ts": s.get("ts"),
        "status": s.get("status"),
        "performance_score": s.get("performance_score"),
        "code_preview": (s.get("code") or "")[:200],
    } for s in raw]

    _out({"operation": "snapshots", "snapshots": slim, "summary": summary})


def _op_build_system(payload: dict) -> None:
    spec = str(payload.get("spec", "")).strip()
    project_name = re.sub(r"[^\w\-]", "_", str(payload.get("project_name", "project")).strip()) or "project"
    if not spec:
        _fail("build_system: spec is required")
        return

    try:
        from core.tool_llm_caller import call_llm_for_tool
    except Exception as exc:
        _fail(f"import_llm: {exc}")
        return

    plan_prompt = (
        f"You are a software architect. Design a minimal file structure for:\n{spec}\n\n"
        f'Return ONLY JSON: {{"files": [{{"path": "relative/path.ext", "description": "purpose"}}]}}\n'
        f"Include 3-7 essential files. JSON only:"
    )
    plan_raw = call_llm_for_tool(plan_prompt)
    if not plan_raw:
        _fail("build_system: llm_unavailable")
        return

    plan_match = re.search(r"\{[\s\S]*\}", plan_raw)
    if not plan_match:
        _fail("build_system: could_not_parse_file_plan")
        return
    try:
        plan = json.loads(plan_match.group(0))
    except Exception as exc:
        _fail(f"build_system: json_parse_failed: {exc}")
        return

    files_plan = plan.get("files", [])[:8]
    if not files_plan:
        _fail("build_system: empty_file_list")
        return

    project_dir = AI_HOME / "workspace" / "projects" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []
    for file_def in files_plan:
        file_path = str(file_def.get("path", "")).strip()
        if not file_path:
            continue
        file_desc = str(file_def.get("description", ""))
        content = call_llm_for_tool(
            f"Generate the complete file `{file_path}` for this project:\n{spec}\n"
            f"File purpose: {file_desc}\n"
            f"Return ONLY the raw file content, no markdown fences."
        ) or f"# {file_path}\n# Generation failed — LLM unavailable\n"

        dest = project_dir / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        generated_files.append({"path": str(dest.relative_to(AI_HOME)), "bytes": dest.stat().st_size})

    _out({
        "operation": "build_system",
        "project_name": project_name,
        "project_path": str(project_dir),
        "files": generated_files,
    })


def _op_security_scan(payload: dict) -> None:
    try:
        from runtime.sandbox_executor import get_sandbox_executor
    except ImportError:
        try:
            from sandbox_executor import get_sandbox_executor
        except Exception as exc:
            _fail(f"import_sandbox: {exc}")
            return

    executor = get_sandbox_executor()
    scan_targets = [
        "core/tool_registry.py",
        "core/real_execution_engine.py",
        "core/goal_parser.py",
        "core/tool_llm_caller.py",
    ]

    findings = []
    for target in scan_targets:
        full_path = _RUNTIME_DIR / target
        if not full_path.exists():
            continue
        code = full_path.read_text(encoding="utf-8", errors="replace")
        result = executor.run(code=code, module_name=target)
        findings.append({
            "file": target,
            "safe": result.get("safe", False),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
            "duration_ms": result.get("duration_ms", 0),
        })

    clean = sum(1 for f in findings if f["safe"])
    _out({
        "operation": "security_scan",
        "findings": findings,
        "summary": f"{clean}/{len(findings)} files passed security scan",
    })


def _op_governance_digest(payload: dict) -> None:
    events_raw = payload.get("events", [])
    try:
        from core.tool_llm_caller import call_llm_for_tool
    except Exception as exc:
        _fail(f"import_llm: {exc}")
        return

    events_text = "\n".join(
        f"- {e.get('ts', '')} [{e.get('action', '')}] actor={e.get('actor', '')} risk={e.get('risk_score', 0)}"
        for e in events_raw[:50]
    ) or "No events available."

    digest = call_llm_for_tool(
        f"Analyze these AI system audit events and write a governance digest (under 300 words):\n\n"
        f"{events_text}\n\n"
        f"Cover: key activities, risk patterns, anomalies, and recommendations."
    )
    _out({
        "operation": "governance_digest",
        "digest": digest or "LLM unavailable — cannot generate digest.",
    })


def _op_llm_status(payload: dict) -> None:
    import urllib.request as _req

    ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    groq_key = os.environ.get("GROQ_API_KEY", "")

    ollama_ok = False
    ollama_models = []
    try:
        with _req.urlopen(f"{ollama_host}/api/tags", timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
            ollama_models = [m.get("name", "") for m in data.get("models", [])]
            ollama_ok = True
    except Exception:
        pass

    _out({
        "operation": "llm_status",
        "ollama": {"online": ollama_ok, "host": ollama_host, "models": ollama_models},
        "groq": {"configured": bool(groq_key), "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")},
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _out(data: dict) -> None:
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def _fail(reason: str) -> None:
    _out({"ok": False, "error": reason})


if __name__ == "__main__":
    main()

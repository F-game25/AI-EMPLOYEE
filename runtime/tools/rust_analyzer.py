"""Rust analysis tool using the installed cargo toolchain.

Runs cargo check + cargo clippy + rustfmt --check on a .rs file or Cargo project.
Returns a list of { severity, file, line, col, message, code, suggestion } dicts.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CARGO_BIN = os.path.expanduser("~/.cargo/bin/cargo")
RUSTFMT_BIN = os.path.expanduser("~/.cargo/bin/rustfmt")

_MINIMAL_CARGO_TOML = """\
[package]
name = "analysis_target"
version = "0.1.0"
edition = "2021"

[lib]
path = "src/lib.rs"
"""


def _find_cargo_root(file_path: str) -> Path | None:
    """Walk up from file_path looking for Cargo.toml."""
    p = Path(file_path).resolve().parent
    for candidate in [p, *p.parents]:
        if (candidate / "Cargo.toml").exists():
            return candidate
    return None


def _parse_cargo_json(output: str, project_root: str) -> list[dict]:
    issues = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("reason") != "compiler-message":
            continue
        msg = obj.get("message", {})
        level = msg.get("level", "")
        if level not in ("error", "warning", "note", "help"):
            continue
        severity = "error" if level == "error" else ("warning" if level == "warning" else "info")
        text = msg.get("message", "")
        code_obj = msg.get("code") or {}
        code = code_obj.get("code")
        spans = msg.get("spans", [])
        if spans:
            span = spans[0]
            fname = span.get("file_name", "")
            line_no = span.get("line_start")
            col = span.get("column_start")
            suggestion = span.get("suggested_replacement")
        else:
            fname, line_no, col, suggestion = "", None, None, None
        issues.append({
            "severity": severity,
            "file": fname,
            "line": line_no,
            "col": col,
            "message": text,
            "code": code,
            "suggestion": suggestion,
        })
    return issues


def _run_cargo_commands(project_root: str, source_file: str | None = None) -> list[dict]:
    """Run cargo check + clippy in project_root; optionally also run rustfmt on source_file."""
    env = {**os.environ, "CARGO_HOME": os.path.expanduser("~/.cargo")}
    issues = []

    for subcommand in ("check", "clippy"):
        result = subprocess.run(
            [CARGO_BIN, subcommand, "--message-format=json"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        combined = result.stdout + result.stderr
        issues.extend(_parse_cargo_json(combined, project_root))

    # rustfmt --check
    target_file = source_file or str(next(Path(project_root).rglob("*.rs"), Path("")))
    if target_file and Path(target_file).exists():
        fmt = subprocess.run(
            [RUSTFMT_BIN, "--check", "--edition", "2021", target_file],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if fmt.returncode != 0:
            issues.append({
                "severity": "info",
                "file": target_file,
                "line": None,
                "col": None,
                "message": f"File is not rustfmt-formatted. Run: rustfmt --edition 2021 {target_file}",
                "code": None,
                "suggestion": None,
            })

    return issues


def analyze_rust_file(file_path: str) -> list[dict]:
    """Analyze a .rs file using cargo check + cargo clippy.

    If the file is inside a Cargo project, runs against that project.
    Otherwise wraps it in a minimal temp project.

    Returns list of { severity, file, line, col, message, code, suggestion }.
    """
    cargo_root = _find_cargo_root(file_path)
    if cargo_root:
        return _run_cargo_commands(str(cargo_root), source_file=file_path)

    # Standalone file — create temp project
    tmpdir = tempfile.mkdtemp(prefix="rust_analyze_")
    try:
        src_dir = Path(tmpdir, "src")
        src_dir.mkdir()
        Path(tmpdir, "Cargo.toml").write_text(_MINIMAL_CARGO_TOML)
        lib_rs = src_dir / "lib.rs"
        shutil.copy(file_path, lib_rs)
        return _run_cargo_commands(tmpdir, source_file=str(lib_rs))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def analyze_cargo_project(project_dir: str) -> list[dict]:
    """Run cargo check + clippy + rustfmt on an entire Cargo project directory."""
    return _run_cargo_commands(project_dir)

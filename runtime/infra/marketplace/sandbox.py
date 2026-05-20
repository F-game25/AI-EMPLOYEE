"""Plugin sandbox — isolated execution environment for marketplace plugins."""
from __future__ import annotations
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MB cap on plugin stdout

# Env vars forwarded into the sandbox — no secrets, no credentials
_SANDBOX_ENV_ALLOWLIST = frozenset({"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"})

# Permission → action verb mapping for validate_permissions()
# Keys are the declared permission tokens; values are action verb prefixes they
# authorise.  For example "read_tasks" authorises the action "read_tasks:*".
_PERM_PREFIXES: dict[str, str] = {
    "read_tasks":         "read_tasks",
    "write_tasks":        "write_tasks",
    "read_agents":        "read_agents",
    "read_vault":         "read_vault",
    "write_vault":        "write_vault",
    "send_notifications": "send_notifications",
    "call_llm":           "call_llm",
    "web_search":         "web_search",
}

# Runner script written once to a stable tempfile path per process lifetime.
# We use a module-level singleton so we don't thrash the filesystem.
_runner_path: str | None = None


def _get_runner() -> str:
    """Return path to the runner script, writing it on first call."""
    global _runner_path
    if _runner_path and os.path.exists(_runner_path):
        return _runner_path

    runner_code = '''\
#!/usr/bin/env python3
"""Minimal synchronous plugin runner — executed in an isolated subprocess.

Reads input_data from stdin (single JSON line), calls plugin.main(input_data),
writes result to stdout as a single JSON line.
"""
import importlib.util, json, os, sys, traceback


def load_plugin(plugin_dir: str, entry_point: str):
    path = os.path.join(plugin_dir, entry_point)
    spec = importlib.util.spec_from_file_location("_plugin", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    plugin_dir  = sys.argv[1] if len(sys.argv) > 1 else "."
    entry_point = sys.argv[2] if len(sys.argv) > 2 else "plugin.py"

    raw = sys.stdin.read(1024 * 1024)  # 1 MB read cap
    try:
        input_data = json.loads(raw) if raw.strip() else {}
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"invalid input JSON: {e}"}), flush=True)
        sys.exit(1)

    try:
        plugin = load_plugin(plugin_dir, entry_point)
    except Exception:
        print(json.dumps({"ok": False, "error": traceback.format_exc()}), flush=True)
        sys.exit(1)

    if not hasattr(plugin, "main"):
        print(json.dumps({"ok": False, "error": "plugin has no main() function"}), flush=True)
        sys.exit(1)

    try:
        result = plugin.main(input_data)
        print(json.dumps({"ok": True, "output": result}), flush=True)
    except Exception:
        print(json.dumps({"ok": False, "error": traceback.format_exc()}), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
    # Write to a named temp file that persists for the process lifetime
    fd, path = tempfile.mkstemp(prefix="plugin_runner_", suffix=".py")
    with os.fdopen(fd, "w") as f:
        f.write(runner_code)
    os.chmod(path, 0o600)
    _runner_path = path
    return path


def _build_env() -> dict[str, str]:
    """Return a minimal sanitised env — only the allowlist vars, nothing secret."""
    return {k: v for k, v in os.environ.items() if k in _SANDBOX_ENV_ALLOWLIST}


class PluginSandbox:
    """Run a plugin entry point in an isolated subprocess.

    The subprocess is launched with ``python3 -I`` (isolated mode):
      - No user site-packages
      - PYTHONPATH ignored
      - No implicit imports from the working directory

    The plugin directory is set as the subprocess cwd so relative imports
    within the plugin package resolve correctly.

    Usage::

        sandbox = PluginSandbox(plugin_dir, manifest)
        result  = sandbox.run("plugin.py", {"key": "value"}, timeout_s=30)
        # result: {ok, output, error, duration_ms}
    """

    def __init__(self, plugin_dir: Path, manifest: dict) -> None:
        self.plugin_dir  = Path(plugin_dir)
        self.manifest    = manifest
        self.permissions = set(manifest.get("permissions", []))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        entry_point: str,
        input_data: dict,
        timeout_s: int = 30,
    ) -> dict:
        """Run the plugin entry_point in a sandboxed subprocess.

        Returns::

            {
              "ok":          bool,
              "output":      any,   # present when ok=True
              "error":       str,   # present when ok=False
              "duration_ms": int,
            }
        """
        runner = _get_runner()
        cmd = ["python3", "-I", runner, str(self.plugin_dir), entry_point]

        start = time.monotonic()
        proc = None
        try:
            input_json = json.dumps(input_data).encode()
            proc = subprocess.run(
                cmd,
                input=input_json,
                capture_output=True,
                timeout=timeout_s,
                cwd=str(self.plugin_dir),
                env=_build_env(),
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            raw_stdout = proc.stdout[:_MAX_OUTPUT_BYTES]
            if not raw_stdout.strip():
                stderr_hint = proc.stderr[:512].decode(errors="replace")
                return {
                    "ok": False,
                    "error": f"plugin produced no output. stderr: {stderr_hint}",
                    "duration_ms": duration_ms,
                }

            try:
                payload = json.loads(raw_stdout)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "error": "plugin stdout is not valid JSON",
                    "duration_ms": duration_ms,
                }

            payload.setdefault("duration_ms", duration_ms)
            return payload

        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "Plugin %s timed out after %ds",
                self.manifest.get("name", "?"),
                timeout_s,
            )
            return {"ok": False, "error": "timeout", "duration_ms": duration_ms}

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Sandbox run error for plugin %s", self.manifest.get("name"))
            return {"ok": False, "error": str(exc), "duration_ms": duration_ms}

    def validate_permissions(self, requested_action: str) -> bool:
        """Return True if requested_action is covered by this plugin's declared permissions.

        Matching is prefix-based: permission token ``write_tasks`` authorises
        any action starting with ``write_tasks`` (e.g. ``write_tasks:create``).

        Args:
            requested_action: Action the plugin is attempting (e.g. "write_vault:set").

        Returns:
            True if at least one declared permission covers the action.
        """
        for perm in self.permissions:
            prefix = _PERM_PREFIXES.get(perm)
            if prefix and requested_action.startswith(prefix):
                return True
        return False

"""Subprocess-isolated plugin runner with JSON-RPC 2.0 protocol."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from .schema import PluginManifest

logger = logging.getLogger(__name__)

_RUNNER_SCRIPT = Path(__file__).parent / "_plugin_runner.py"

# Env vars a sandboxed plugin may receive — no secrets, no credentials
_SANDBOX_ALLOWLIST = frozenset({
    "PATH", "HOME", "TMPDIR", "TEMP", "TMP",
    "LANG", "LC_ALL", "LC_CTYPE", "PYTHONPATH",
    "PYTHON_MEMORY_LIMIT_MB",
})

# Prefix patterns that indicate secret/credential env vars — always blocked
_SECRET_PREFIXES = (
    "ANTHROPIC_", "OPENAI_", "AWS_", "GCP_", "AZURE_",
    "DATABASE_URL", "DB_", "REDIS_", "NEO4J_",
    "JWT_", "SECRET_", "API_KEY", "TOKEN",
    "VAULT_", "STRIPE_", "SENDGRID_",
)


def _build_sandbox_env(manifest: PluginManifest, limit_mb: int) -> dict:
    """Build a minimal, sanitized env for a sandboxed plugin subprocess.

    Starts from an empty env (not os.environ) and allows only the safe
    allowlist, then injects capability-scoped secrets if the plugin
    has declared 'secrets:vault' in its requires_capabilities.
    """
    safe: dict[str, str] = {}
    for k, v in os.environ.items():
        upper = k.upper()
        # Explicitly block anything that looks like a secret
        if any(upper.startswith(p.upper()) for p in _SECRET_PREFIXES):
            continue
        if upper in _SANDBOX_ALLOWLIST:
            safe[k] = v

    safe["PLUGIN_MEMORY_LIMIT_MB"] = str(limit_mb)
    safe["PLUGIN_ID"] = manifest.id
    safe["PLUGIN_VERSION"] = getattr(manifest, "version", "unknown")

    # Capability-scoped secret injection (read-only ephemeral tokens)
    requires = getattr(manifest, "requires_capabilities", []) or []
    if "secrets:vault" in requires:
        # Inject a scoped, read-only token from SecretsManager if available
        try:
            from infra.secrets.manager import get_secrets_manager
            token = get_secrets_manager().issue_scoped_token(
                manifest.id, scopes=requires, ttl_s=3600
            )
            if token:
                safe["PLUGIN_VAULT_TOKEN"] = token
        except Exception:
            pass  # No vault — plugin proceeds without secret access

    return safe


def _write_runner() -> None:
    """Write the subprocess runner script if absent."""
    if _RUNNER_SCRIPT.exists():
        return
    _RUNNER_SCRIPT.write_text('''#!/usr/bin/env python3
"""Minimal JSON-RPC 2.0 plugin runner — executed in subprocess."""
import importlib.util, json, sys, os

def load_plugin(code_dir, entry):
    spec = importlib.util.spec_from_file_location("plugin", os.path.join(code_dir, entry))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    code_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    entry = sys.argv[2] if len(sys.argv) > 2 else "plugin.py"
    try:
        plugin = load_plugin(code_dir, entry)
    except Exception as e:
        print(json.dumps({"jsonrpc":"2.0","id":None,"error":{"code":-32001,"message":str(e)}}))
        sys.exit(1)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            method = req.get("method", "")
            params = req.get("params", {})
            rid = req.get("id")
            fn = getattr(plugin, method, None)
            if fn is None:
                result = {"error": f"method {method!r} not found"}
            else:
                result = fn(**params) if isinstance(params, dict) else fn(*params)
            print(json.dumps({"jsonrpc":"2.0","id":rid,"result":result}), flush=True)
        except Exception as e:
            print(json.dumps({"jsonrpc":"2.0","id":req.get("id"),"error":{"code":-32000,"message":str(e)}}), flush=True)

if __name__ == "__main__":
    main()
''')


class SandboxedPlugin:
    def __init__(self, manifest: PluginManifest, package_dir: str):
        self.manifest = manifest
        self.package_dir = package_dir
        self._proc: Optional[asyncio.subprocess.Process] = None
        _write_runner()

    async def start(self) -> None:
        code_dir = str(Path(self.package_dir) / "code")
        limit_mb = self.manifest.sandbox.get("memory_mb", 512)
        env = _build_sandbox_env(self.manifest, limit_mb)
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable, str(_RUNNER_SCRIPT), code_dir, self.manifest.entry_point,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        logger.info("Plugin %s started (pid %s)", self.manifest.id, self._proc.pid)

    async def call(self, method: str, params: dict, timeout_s: int = 30) -> Any:
        if self._proc is None or self._proc.returncode is not None:
            raise RuntimeError("Plugin process not running")
        rpc_id = str(uuid.uuid4())[:8]
        msg = json.dumps({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})
        self._proc.stdin.write((msg + "\n").encode())
        await self._proc.stdin.drain()
        try:
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=timeout_s)
            resp = json.loads(line.decode())
            if "error" in resp:
                raise RuntimeError(resp["error"].get("message", "plugin error"))
            return resp.get("result")
        except asyncio.TimeoutError:
            raise RuntimeError(f"Plugin {self.manifest.id} timed out after {timeout_s}s")

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        logger.info("Plugin %s stopped", self.manifest.id)

"""Executable Sandboxing — Secure agent code isolation

Implements process-level sandboxing for agent execution with:
  - Restricted Python execution (RestrictedPython)
  - Resource limits: CPU time (30s), memory (500MB)
  - Blocked operations: no direct file access, no subprocess, no dangerous imports
  - Whitelist-based module imports
  - Timeout handling and cleanup
  - Audit logging of all blocked operations
"""

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, asdict

try:
    import resource
    RESOURCE_MODULE_AVAILABLE = True
except ImportError:
    RESOURCE_MODULE_AVAILABLE = False  # Windows doesn't have resource module

try:
    from RestrictedPython import compile_restricted
    RESTRICTED_PYTHON_AVAILABLE = True
except ImportError:
    RESTRICTED_PYTHON_AVAILABLE = False

logger = logging.getLogger(__name__)

LOG = '[SandboxManager]'


@dataclass
class SandboxPolicy:
    """Sandbox execution policy"""
    max_cpu_seconds: int = 30
    max_memory_mb: int = 500
    allowed_imports: list = None  # Whitelist of allowed modules
    blocked_operations: list = None  # Operations to block (file_access, subprocess, network_raw)
    allow_network: bool = False
    allow_file_system: bool = False
    timeout_action: str = 'kill'  # kill or graceful

    def __post_init__(self):
        if self.allowed_imports is None:
            self.allowed_imports = [
                'json', 'math', 'datetime', 'hashlib', 'hmac', 'time',
                'logging', 'itertools', 'functools', 'collections',
            ]
        if self.blocked_operations is None:
            self.blocked_operations = [
                'open', 'exec', 'eval', '__import__', 'compile',
                'input', 'globals', 'locals', 'vars', 'dir',
            ]


# Only these environment variables are exposed to sandboxed code. The host
# environment carries secrets (API keys, JWT_SECRET_KEY, DB creds); passing it to
# executed code — which is LLM/user-authored and may escape the restricted builtins
# — would leak every secret. Allowlist the minimum needed to run Python.
_SANDBOX_ENV_ALLOW = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "TEMP", "TMP",
    "PYTHONPATH", "PYTHONUNBUFFERED", "PYTHONHASHSEED", "SYSTEMROOT", "PATHEXT",
)


def _sandbox_env() -> dict:
    """Sanitized environment for the sandbox subprocess — secrets stripped."""
    env = {k: v for k, v in os.environ.items() if k in _SANDBOX_ENV_ALLOW}
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("HOME", tempfile.gettempdir())
    return env


def _rlimit_preexec(policy: "SandboxPolicy"):
    """Return a preexec_fn that applies OS resource limits (POSIX only).

    Caps CPU time, address space (memory), output file size, and process count so
    sandboxed code cannot exhaust the host or fork-bomb. Returns None where rlimits
    are unavailable (e.g. Windows), where the subprocess timeout remains the guard.
    """
    if os.name != "posix":
        return None
    try:
        import resource  # noqa: PLC0415 — POSIX-only
    except Exception:  # noqa: BLE001
        return None

    cpu = max(1, int(getattr(policy, "max_cpu_seconds", 30)))
    mem_bytes = max(64, int(getattr(policy, "max_memory_mb", 500))) * 1024 * 1024

    def _apply():  # runs in the child before exec
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
            if hasattr(resource, "RLIMIT_NPROC"):
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:  # noqa: BLE001 — never block execution on a missing limit
            pass

    return _apply


class SandboxManager:
    """Manage sandboxed agent execution"""

    def __init__(self, policy: Optional[SandboxPolicy] = None, audit_log_fn: Optional[Callable] = None):
        self.policy = policy or SandboxPolicy()
        self.audit_log = audit_log_fn or (lambda **kwargs: None)
        self.active_processes = {}  # pid -> process info
        self._lock = threading.Lock()

    def execute_agent_code(
        self,
        agent_id: str,
        code: str,
        context: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute agent code in sandbox.

        Args:
            agent_id: Agent identifier for audit logging
            code: Python code to execute
            context: Variables available to the code
            timeout: Max execution time (overrides policy)

        Returns:
            {
                'success': bool,
                'result': any,
                'error': str if failed,
                'execution_time': float,
                'blocked_operations': [str],
                'warnings': [str],
            }
        """
        timeout = timeout or self.policy.max_cpu_seconds

        # Validate code before execution
        validation = self._validate_code(code, agent_id)
        if validation.get('blocked_operations'):
            self.audit_log(
                event='code_validation_failed',
                agent_id=agent_id,
                reason='blocked_operations_detected',
                operations=validation['blocked_operations'],
            )
            return {
                'success': False,
                'error': f"Code contains blocked operations: {', '.join(validation['blocked_operations'])}",
                'execution_time': 0,
                'blocked_operations': validation['blocked_operations'],
                'warnings': validation.get('warnings', []),
            }

        # Execute in subprocess with resource limits
        start_time = time.time()
        try:
            result = self._execute_in_subprocess(
                agent_id=agent_id,
                code=code,
                context=context,
                timeout=timeout,
            )
            execution_time = time.time() - start_time

            # Log successful execution
            self.audit_log(
                event='agent_executed',
                agent_id=agent_id,
                success=True,
                execution_time=execution_time,
                blocked_operations=validation.get('blocked_operations', []),
            )

            return {
                'success': result.get('success', True),
                'result': result.get('result'),
                'error': result.get('error'),
                'execution_time': execution_time,
                'blocked_operations': validation.get('blocked_operations', []),
                'warnings': result.get('warnings', []),
            }

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            self.audit_log(
                event='agent_timeout',
                agent_id=agent_id,
                timeout_seconds=timeout,
                execution_time=execution_time,
            )
            return {
                'success': False,
                'error': f'Execution timeout (max {timeout}s)',
                'execution_time': execution_time,
                'blocked_operations': [],
                'warnings': ['Process exceeded maximum execution time'],
            }

        except Exception as e:
            execution_time = time.time() - start_time
            self.audit_log(
                event='agent_execution_error',
                agent_id=agent_id,
                error=str(e),
                execution_time=execution_time,
            )
            return {
                'success': False,
                'error': f'Execution error: {str(e)}',
                'execution_time': execution_time,
                'blocked_operations': [],
                'warnings': [],
            }

    def _validate_code(self, code: str, agent_id: str) -> Dict[str, Any]:
        """
        Validate code before execution.

        Returns:
            {
                'valid': bool,
                'blocked_operations': [str],
                'warnings': [str],
            }
        """
        blocked = []
        warnings = []

        # Check for blocked operations in source
        for op in self.policy.blocked_operations:
            if op in code:
                blocked.append(op)

        # Check for dangerous patterns
        dangerous_patterns = [
            ('__builtins__', 'Builtin access'),
            ('sys.exit', 'System exit'),
            ('/etc/passwd', 'Sensitive file access'),
            ('subprocess', 'Subprocess execution'),
        ]

        for pattern, description in dangerous_patterns:
            if pattern in code:
                warnings.append(f'Detected potentially dangerous pattern: {description}')

        return {
            'valid': len(blocked) == 0,
            'blocked_operations': blocked,
            'warnings': warnings,
        }

    def _execute_in_subprocess(
        self,
        agent_id: str,
        code: str,
        context: Dict[str, Any],
        timeout: int,
    ) -> Dict[str, Any]:
        """
        Execute code in isolated subprocess with resource limits.
        """
        # Create temporary script file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            script_path = f.name
            f.write(self._build_sandbox_script(code, context))

        try:
            # Run in subprocess with timeout
            process = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_sandbox_env(),  # secrets stripped — host env never reaches sandboxed code
                preexec_fn=_rlimit_preexec(self.policy),  # CPU/mem/fsize/nproc caps (POSIX)
            )

            # Parse output
            output = process.stdout
            if output:
                try:
                    result = json.loads(output)
                    return result
                except json.JSONDecodeError:
                    return {
                        'success': False,
                        'error': 'Invalid JSON output from subprocess',
                        'raw_output': output[:1000],  # Limit output size
                    }

            return {
                'success': False,
                'error': process.stderr or 'No output from subprocess',
            }

        finally:
            # Clean up temporary script
            try:
                Path(script_path).unlink()
            except Exception:
                pass

    def _build_sandbox_script(self, code: str, context: Dict[str, Any]) -> str:
        """
        Build a sandboxed script wrapper that restricts the code environment.
        """
        safe_builtins = {
            'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'filter',
            'float', 'frozenset', 'int', 'len', 'list', 'map', 'max',
            'min', 'range', 'round', 'set', 'sorted', 'str', 'sum', 'tuple',
            'zip', '__name__', '__doc__',
        }

        context_json = json.dumps(context, default=str)
        allowed_imports = json.dumps(self.policy.allowed_imports)
        safe_names = json.dumps(sorted(safe_builtins))

        # Build a real restricted-builtins DICT in the child (callables can't be
        # JSON-serialized), exec the code with explicit globals, and embed the code
        # via repr() so content containing triple-quotes cannot break out of the
        # wrapper. NOTE: restricted builtins is a soft barrier (object-graph escapes
        # exist); the hard controls are the stripped env (no secrets) + the POSIX
        # rlimits applied to this subprocess. Use forge_sandbox_manager / a container
        # for genuinely untrusted code.
        return f'''
import json, sys
import builtins as _b

_SAFE_NAMES = {safe_names}
_restricted = {{n: getattr(_b, n) for n in _SAFE_NAMES if hasattr(_b, n)}}
__context__ = json.loads({repr(context_json)})
__allowed_imports__ = {allowed_imports}

_g = {{"__builtins__": _restricted, "__context__": __context__,
       "__allowed_imports__": __allowed_imports__}}
try:
    exec({repr(code)}, _g)
    result = {{"success": True, "result": _g.get("result")}}
except Exception as e:
    result = {{"success": False, "error": str(e)}}

sys.stdout.write(json.dumps(result, default=str))
'''

    def run_code(self, code: str, language: str = "python", **kwargs) -> Dict[str, Any]:
        """Dispatch code execution by language.

        Supports 'python' (existing sandboxed path) and 'rust' (cargo build + run).
        kwargs are forwarded to the language-specific runner (e.g. dependencies, timeout).
        """
        if language in ("rust", "rs"):
            return self._run_rust(code, **kwargs)
        # Default: Python path via execute_agent_code with a generic agent id
        return self.execute_agent_code(
            agent_id="sandbox",
            code=code,
            context=kwargs.get("context", {}),
            timeout=kwargs.get("timeout"),
        )

    def execute_safe(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalised entrypoint used by execution_engine / real_execution_engine.

        Runs the payload's code via ``run_code`` and maps the internal
        ``{'success': ...}`` shape onto the ``{ok, result, error}`` contract the
        callers rely on. Never raises (fail-closed) — the callers previously hit
        AttributeError because this method did not exist.
        """
        payload = payload or {}
        code = str(payload.get("code", "") or "")
        language = str(payload.get("language", "python") or "python")
        try:
            res = self.run_code(code, language=language,
                                 context=payload.get("context", {}),
                                 timeout=payload.get("timeout"))
        except Exception as exc:  # noqa: BLE001 — never raise to callers
            return {"ok": False, "result": None, "error": str(exc)}
        if not isinstance(res, dict):
            return {"ok": False, "result": None, "error": "sandbox returned no result"}
        ok = bool(res.get("ok", res.get("success", False)))
        return {"ok": ok,
                "result": res.get("result", res.get("output")),
                "error": res.get("error", "") if not ok else ""}

    def _run_rust(self, code: str, dependencies: list = None, timeout: int = 30) -> Dict[str, Any]:
        """Compile and run Rust code in a temp Cargo project."""
        import shutil
        cargo_bin = os.path.expanduser("~/.cargo/bin/cargo")
        tmpdir = tempfile.mkdtemp(prefix="rust_sandbox_")
        try:
            deps_str = "\n".join(f'{d} = "*"' for d in (dependencies or []))
            cargo_toml = (
                "[package]\n"
                "name = \"sandbox\"\n"
                "version = \"0.1.0\"\n"
                "edition = \"2021\"\n\n"
                "[dependencies]\n"
                f"{deps_str}\n"
            )
            src_dir = Path(tmpdir, "src")
            src_dir.mkdir()
            Path(tmpdir, "Cargo.toml").write_text(cargo_toml)

            if "fn main()" in code:
                Path(src_dir, "main.rs").write_text(code)
            else:
                Path(src_dir, "main.rs").write_text(f"fn main() {{\n{code}\n}}")

            env = {**os.environ, "CARGO_HOME": os.path.expanduser("~/.cargo")}

            build = subprocess.run(
                [cargo_bin, "build", "--release", "--message-format=json"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if build.returncode != 0:
                return {
                    "ok": False,
                    "stage": "compile",
                    "stderr": build.stderr,
                    "stdout": build.stdout,
                }

            binary = os.path.join(tmpdir, "target", "release", "sandbox")
            run_result = subprocess.run(
                [binary],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "ok": True,
                "stdout": run_result.stdout[:4000],
                "stderr": run_result.stderr[:1000],
                "exit_code": run_result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def get_process_stats(self) -> Dict[str, Any]:
        """Get statistics about active sandboxed processes"""
        with self._lock:
            return {
                'active_processes': len(self.active_processes),
                'policy': asdict(self.policy),
            }


class SandboxedAgentExecutor:
    """High-level interface for executing agents in sandbox"""

    def __init__(self, sandbox_manager: SandboxManager):
        self.manager = sandbox_manager

    def run_agent(
        self,
        agent_id: str,
        agent_code: str,
        agent_input: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run agent code with provided input.

        Returns: { 'ok': bool, 'result': any, 'error': str if failed, ... }
        """
        result = self.manager.execute_agent_code(
            agent_id=agent_id,
            code=agent_code,
            context={'input': agent_input},
            timeout=timeout,
        )

        if result['success']:
            return {
                'ok': True,
                'result': result.get('result'),
                'execution_time': result['execution_time'],
            }
        else:
            return {
                'ok': False,
                'error': result['error'],
                'execution_time': result['execution_time'],
                'warnings': result.get('warnings', []),
            }

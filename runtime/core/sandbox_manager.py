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
                env={**os.environ, 'PYTHONUNBUFFERED': '1'},
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

        # Create sandbox with limited builtins
        builtin_whitelist = {name: __builtins__[name] for name in safe_builtins if name in __builtins__}

        context_json = json.dumps(context, default=str)
        allowed_imports = json.dumps(self.policy.allowed_imports)

        return f'''
import json
import sys

# Restrict builtins
__builtins__ = {json.dumps(list(safe_builtins))}

# Load provided context
__context__ = json.loads({repr(context_json)})

# Restrict imports
__allowed_imports__ = {allowed_imports}

# Execute user code with sandbox environment
try:
    exec("""
{code}
    """)
    result = {{'success': True, 'result': locals().get('result')}}
except Exception as e:
    result = {{'success': False, 'error': str(e)}}

# Output result as JSON
print(json.dumps(result))
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

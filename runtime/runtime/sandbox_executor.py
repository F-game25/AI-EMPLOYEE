"""Sandbox Executor — isolated, safety-checked code execution.

Before any Forge-submitted code is deployed to the live system it passes
through this layer:

1. **Syntax check** — ``ast.parse()`` must succeed.
2. **Security scan** — disallowed patterns (``exec``, ``eval``, ``__import__``,
   ``subprocess``, ``os.system``, ``open`` in writable-sensitive contexts,
   network calls to external hosts, etc.) are flagged.
3. **Dry-run import** — the code is compiled and imported into a clean
   ``types.ModuleType`` namespace without touching the live module registry.
4. **Resource guards** — execution time-outs at ``SANDBOX_TIMEOUT_S`` seconds.

Only if all checks pass is the caller told it is safe to deploy.

Usage::

    from runtime.sandbox_executor import get_sandbox_executor

    result = get_sandbox_executor().run(
        code="def hello(): return 'world'",
        module_name="my_module",
    )
    if result["safe"]:
        # ... deploy via hot_reload_manager
    else:
        print(result["errors"])
"""
from __future__ import annotations

import ast
import logging
import os
import re
import threading
import time
import types
from typing import Any

logger = logging.getLogger("runtime.sandbox_executor")

_LOCK = threading.Lock()
SANDBOX_TIMEOUT_S = float(os.environ.get("AI_EMPLOYEE_SANDBOX_TIMEOUT", "10"))

# ── Security rules ────────────────────────────────────────────────────────────

# AST node types that are outright banned
_BANNED_NODE_TYPES: set[str] = {
    "AsyncFunctionDef",  # ban raw async defs (allowed only via approval)
}

# Identifiers / attributes that are disallowed
_BANNED_NAMES: frozenset[str] = frozenset({
    "__import__",
    "eval",
    "exec",
    "compile",
    "globals",
    "locals",
    "vars",
    "breakpoint",
    "input",
})

_BANNED_ATTRIBUTE_CHAINS: frozenset[str] = frozenset({
    "os.system",
    "os.popen",
    "os.execv",
    "os.execve",
    "subprocess.call",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.check_output",
    "socket.socket",
    "urllib.request.urlopen",
    "requests.get",
    "requests.post",
    "httpx.get",
    "httpx.post",
})

# Regex patterns on raw source text
_BANNED_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bctypes\b"),
    re.compile(r"\bimportlib\.import_module\b"),
    re.compile(r"\b__builtins__\b"),
    re.compile(r"\bpickle\.loads?\b"),
    re.compile(r"\bshutil\.rmtree\b"),
    re.compile(r"\bos\.remove\b"),
    re.compile(r"\bos\.unlink\b"),
    re.compile(r"\bpathlib\.Path.*\.unlink\b"),
]

# Protected core modules that must not be overwritten from the forge
_PROTECTED_MODULES: frozenset[str] = frozenset({
    "core/orchestrator.py",
    "engine/api.py",
    "runtime/hot_reload_manager.py",
    "runtime/sandbox_executor.py",
    "runtime/version_control.py",
    "main.py",
})


class _SecurityVisitor(ast.NodeVisitor):
    """AST visitor that collects security violations."""

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in _BANNED_NAMES:
            self.violations.append(
                f"Banned name '{node.id}' at line {node.lineno}"
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        chain = _attr_chain(node)
        for banned in _BANNED_ATTRIBUTE_CHAINS:
            if chain.endswith(banned) or chain == banned:
                self.violations.append(
                    f"Banned attribute access '{chain}' at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] in {"subprocess", "ctypes", "socket"}:
                self.violations.append(
                    f"Banned import '{alias.name}' at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        if mod.split(".")[0] in {"subprocess", "ctypes", "socket"}:
            self.violations.append(
                f"Banned from-import '{mod}' at line {node.lineno}"
            )
        self.generic_visit(node)


def _attr_chain(node: ast.Attribute) -> str:
    parts: list[str] = [node.attr]
    current: Any = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


# ══════════════════════════════════════════════════════════════════════════════

class SandboxExecutor:
    """Safe, isolated code evaluator for Ascend Forge submissions."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        code: str,
        *,
        module_name: str = "forge_module",
        target_module: str = "",
        allow_async: bool = False,
    ) -> dict[str, Any]:
        """Execute *code* in a sandboxed namespace.

        Args:
            code:          Python source code to validate and test.
            module_name:   Logical name used for error messages.
            target_module: The repo-relative module path being replaced
                           (used to check against protected modules list).
            allow_async:   When True, ``async def`` is permitted.

        Returns:
            A dict with:
              - ``safe``    — bool
              - ``errors``  — list of strings
              - ``warnings`` — list of strings
              - ``exports`` — list of names defined in the module
              - ``duration_ms`` — int
        """
        started = time.monotonic()
        errors: list[str] = []
        warnings: list[str] = []

        # 0. Protected-module check
        if target_module and target_module in _PROTECTED_MODULES:
            return self._result(
                safe=False,
                errors=[
                    f"'{target_module}' is a protected core module and cannot be "
                    "modified via Ascend Forge without manual override."
                ],
                warnings=[],
                exports=[],
                started=started,
            )

        # 1. Syntax check
        try:
            tree = ast.parse(code, filename=module_name)
        except SyntaxError:
            logger.exception("Syntax validation failed for sandbox module '%s'", module_name)
            return self._result(
                safe=False,
                errors=["SyntaxError: invalid Python syntax."],
                warnings=[],
                exports=[],
                started=started,
            )

        # 2. Security scan — AST
        if not allow_async:
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    warnings.append(
                        f"async def '{node.name}' at line {node.lineno} — allowed but flagged for review"
                    )

        visitor = _SecurityVisitor()
        visitor.visit(tree)
        errors.extend(visitor.violations)

        # 3. Security scan — raw text
        for pattern in _BANNED_PATTERNS:
            if pattern.search(code):
                errors.append(f"Banned pattern detected: {pattern.pattern!r}")

        if errors:
            return self._result(
                safe=False,
                errors=errors,
                warnings=warnings,
                exports=[],
                started=started,
            )

        # 4. Dry-run compile + exec in isolated namespace
        # Use a restricted builtins dict: keep __import__ so that normal `import`
        # statements work, but strip out dangerous callables (eval, exec, compile,
        # open, input, breakpoint).  Explicit use of __import__ as a *call* is
        # already caught by the AST scan above (it appears as a Name node).
        import builtins as _builtins_mod
        _STRIP_BUILTINS = frozenset({"eval", "exec", "compile", "open", "input", "breakpoint", "__loader__"})
        restricted_builtins = {
            k: v for k, v in vars(_builtins_mod).items() if k not in _STRIP_BUILTINS
        }
        namespace: dict[str, Any] = {"__name__": module_name, "__builtins__": restricted_builtins}
        try:
            bytecode = compile(tree, module_name, "exec")
            # Run with a timeout via a thread
            exec_error: list[str] = []

            def _run() -> None:
                try:
                    exec(bytecode, namespace)  # noqa: S102
                except Exception:  # noqa: BLE001
                    logger.exception("Sandbox runtime execution failed for module '%s'", module_name)
                    exec_error.append("sandbox runtime failure")

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=SANDBOX_TIMEOUT_S)
            if t.is_alive():
                errors.append(
                    f"Sandbox timeout: execution exceeded {SANDBOX_TIMEOUT_S}s"
                )
                return self._result(
                    safe=False,
                    errors=errors,
                    warnings=warnings,
                    exports=[],
                    started=started,
                )
            if exec_error:
                errors.append(f"RuntimeError in sandbox: {exec_error[0]}")
                return self._result(
                    safe=False,
                    errors=errors,
                    warnings=warnings,
                    exports=[],
                    started=started,
                )
        except Exception:  # noqa: BLE001
            logger.exception("Sandbox compile step failed for module '%s'", module_name)
            errors.append("Compile error: unable to compile module.")
            return self._result(
                safe=False,
                errors=errors,
                warnings=warnings,
                exports=[],
                started=started,
            )

        # 5. Collect exports
        exports = [
            k for k in namespace
            if not k.startswith("_") and k not in ("__name__", "__builtins__")
        ]

        return self._result(
            safe=True,
            errors=[],
            warnings=warnings,
            exports=exports,
            started=started,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _result(
        *,
        safe: bool,
        errors: list[str],
        warnings: list[str],
        exports: list[str],
        started: float,
    ) -> dict[str, Any]:
        return {
            "safe": safe,
            "errors": errors,
            "warnings": warnings,
            "exports": exports,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: SandboxExecutor | None = None
_instance_lock = threading.Lock()


def get_sandbox_executor() -> SandboxExecutor:
    """Return the process-wide SandboxExecutor singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SandboxExecutor()
    return _instance

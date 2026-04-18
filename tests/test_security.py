"""Security layer tests.

Validates zero-trust permission system, input sanitisation, and sandbox checks.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))


# ---------------------------------------------------------------------------
# Test: Permission grant and revoke
# ---------------------------------------------------------------------------

class TestPermissionManagement:
    """Verify the zero-trust permission lifecycle."""

    def test_security_layer_importable(self) -> None:
        from core.security_layer import SecurityLayer, get_security_layer
        sl = get_security_layer()
        assert sl is not None

    def test_grant_and_check_permission(self) -> None:
        from core.security_layer import SecurityLayer, MEMORY_WRITE
        sl = SecurityLayer()
        sl.grant("agent-1", {MEMORY_WRITE})
        assert sl.has_permission("agent-1", MEMORY_WRITE) is True

    def test_no_permission_by_default(self) -> None:
        """Agents should have zero permissions by default."""
        from core.security_layer import SecurityLayer, MEMORY_WRITE
        sl = SecurityLayer()
        assert sl.has_permission("unknown-agent", MEMORY_WRITE) is False

    def test_revoke_permission(self) -> None:
        from core.security_layer import SecurityLayer, TOOL_EXECUTION
        sl = SecurityLayer()
        sl.grant("agent-2", {TOOL_EXECUTION})
        assert sl.has_permission("agent-2", TOOL_EXECUTION) is True
        sl.revoke("agent-2", {TOOL_EXECUTION})
        assert sl.has_permission("agent-2", TOOL_EXECUTION) is False

    def test_revoke_all_permissions(self) -> None:
        from core.security_layer import SecurityLayer, MEMORY_WRITE, FORGE_ACCESS
        sl = SecurityLayer()
        sl.grant("agent-3", {MEMORY_WRITE, FORGE_ACCESS})
        sl.revoke("agent-3")
        assert sl.permissions_for("agent-3") == frozenset()

    def test_grant_unknown_permission_raises(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        with pytest.raises(ValueError, match="Unknown permissions"):
            sl.grant("agent-4", {"nonexistent_permission"})

    def test_permissions_for_returns_frozenset(self) -> None:
        from core.security_layer import SecurityLayer, ECONOMY_ACTIONS
        sl = SecurityLayer()
        sl.grant("agent-5", {ECONOMY_ACTIONS})
        perms = sl.permissions_for("agent-5")
        assert isinstance(perms, frozenset)
        assert ECONOMY_ACTIONS in perms


# ---------------------------------------------------------------------------
# Test: Permission enforcement (require)
# ---------------------------------------------------------------------------

class TestPermissionEnforcement:
    """Verify that require() raises on missing permissions."""

    def test_require_with_permission_succeeds(self) -> None:
        from core.security_layer import SecurityLayer, FORGE_ACCESS
        sl = SecurityLayer()
        sl.grant("agent-ok", {FORGE_ACCESS})
        # Should not raise
        sl.require("agent-ok", FORGE_ACCESS, action="forge_submit")

    def test_require_without_permission_raises(self) -> None:
        from core.security_layer import SecurityLayer, PermissionDeniedError, FORGE_ACCESS
        sl = SecurityLayer()
        with pytest.raises(PermissionDeniedError):
            sl.require("agent-denied", FORGE_ACCESS, action="forge_submit")


# ---------------------------------------------------------------------------
# Test: Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Verify payload sanitisation and injection detection."""

    def test_valid_payload_accepted(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        sl.validate_input({"goal": "improve logging", "priority": "low"})

    def test_non_dict_payload_rejected(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        with pytest.raises(ValueError, match="must be a JSON object"):
            sl.validate_input("not a dict")

    def test_shell_injection_detected(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        with pytest.raises(ValueError, match="disallowed characters"):
            sl.validate_input({"cmd": "ls; rm -rf /"})

    def test_oversized_value_rejected(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        with pytest.raises(ValueError, match="exceeds maximum length"):
            sl.validate_input({"data": "x" * 10000})

    def test_missing_required_keys_rejected(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        with pytest.raises(ValueError, match="missing required fields"):
            sl.validate_input({"priority": "low"}, required_keys=["goal"])


# ---------------------------------------------------------------------------
# Test: Sandbox check
# ---------------------------------------------------------------------------

class TestSandboxCheck:
    """Verify the static code safety pre-screen."""

    def test_safe_code_passes(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        result = sl.sandbox_check("def add(a, b): return a + b")
        assert result["safe"] is True
        assert result["violations"] == []

    def test_eval_detected(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        result = sl.sandbox_check("result = eval(user_input)")
        assert result["safe"] is False
        assert any("eval" in v for v in result["violations"])

    def test_os_system_detected(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        result = sl.sandbox_check("import os\nos.system('rm -rf /')")
        assert result["safe"] is False

    def test_subprocess_detected(self) -> None:
        from core.security_layer import SecurityLayer
        sl = SecurityLayer()
        result = sl.sandbox_check("import subprocess; subprocess.run(['ls'])")
        assert result["safe"] is False


# ---------------------------------------------------------------------------
# Test: Forge operation validation
# ---------------------------------------------------------------------------

class TestForgeOperationValidation:
    """Verify end-to-end Forge validation (permission + input)."""

    def test_forge_operation_without_permission_denied(self) -> None:
        from core.security_layer import SecurityLayer, PermissionDeniedError
        sl = SecurityLayer()
        with pytest.raises(PermissionDeniedError):
            sl.validate_forge_operation("agent-no-perm", {"goal": "improve performance"})

    def test_forge_operation_with_permission_succeeds(self) -> None:
        from core.security_layer import SecurityLayer, FORGE_ACCESS
        sl = SecurityLayer()
        sl.grant("agent-forge", {FORGE_ACCESS})
        sl.validate_forge_operation("agent-forge", {"goal": "improve performance"})

    def test_forge_operation_with_injection_fails(self) -> None:
        from core.security_layer import SecurityLayer, FORGE_ACCESS
        sl = SecurityLayer()
        sl.grant("agent-inject", {FORGE_ACCESS})
        with pytest.raises(ValueError, match="disallowed characters"):
            sl.validate_forge_operation("agent-inject", {"goal": "test; rm -rf /"})

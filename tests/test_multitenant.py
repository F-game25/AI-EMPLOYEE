"""Multi-tenancy tests — verify tenant isolation and data segregation."""
import json
import pytest
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent / "runtime"))

import jwt
from fastapi import HTTPException

from core.tenancy import (
    TenantManager,
    TenantContext,
    get_current_tenant_from_jwt,
    get_tenant_manager,
    init_tenant_manager,
)
from core.file_lock import read_json_safe, write_json_safe


class TestTenantCreation:
    """Test tenant lifecycle."""

    def test_create_tenant(self, tmp_path):
        """Creating a tenant should create directory structure."""
        manager = TenantManager(tmp_path)
        tenant_id = manager.create_tenant("Test Org", "user@example.com")

        assert len(tenant_id) >= 8
        assert (tmp_path / "tenants" / tenant_id / "state").exists()
        assert (tmp_path / "tenants" / tenant_id / "config").exists()

    def test_get_tenant_dirs(self, tmp_path):
        """Should retrieve tenant state and config directories."""
        manager = TenantManager(tmp_path)
        tenant_id = manager.create_tenant("Test Org", "user@example.com")

        state_dir = manager.get_tenant_state_dir(tenant_id)
        config_dir = manager.get_tenant_config_dir(tenant_id)

        assert state_dir.exists()
        assert config_dir.exists()

    def test_nonexistent_tenant_error(self, tmp_path):
        """Accessing non-existent tenant should raise error."""
        manager = TenantManager(tmp_path)

        with pytest.raises(ValueError, match="Tenant .* not found"):
            manager.get_tenant_state_dir("nonexistent")


class TestTenantContext:
    """Test tenant context management."""

    def test_set_and_get_context(self, tmp_path):
        """Setting and getting tenant context should work."""
        init_tenant_manager(tmp_path)
        manager = get_tenant_manager()

        context = TenantContext(
            tenant_id="test-tenant",
            org_name="Test Org",
            user_email="user@example.com"
        )
        manager.set_current_tenant(context)

        retrieved = manager.get_current_tenant()
        assert retrieved.tenant_id == "test-tenant"
        assert retrieved.org_name == "Test Org"

    def test_require_current_tenant(self, tmp_path):
        """Requiring context when none is set should raise error."""
        init_tenant_manager(tmp_path)
        manager = get_tenant_manager()
        manager.clear_current_tenant()

        with pytest.raises(RuntimeError, match="No tenant context"):
            manager.require_current_tenant()

    def test_clear_context(self, tmp_path):
        """Clearing context should remove it."""
        init_tenant_manager(tmp_path)
        manager = get_tenant_manager()

        context = TenantContext(tenant_id="testtenantid", org_name="Test", user_email="test@example.com")
        manager.set_current_tenant(context)
        manager.clear_current_tenant()

        assert manager.get_current_tenant() is None

    def test_extract_tenant_from_signed_jwt(self, monkeypatch):
        """Tenant extraction should require and accept a valid JWT signature."""
        secret = "test-secret-key-long-enough-for-hs256"
        monkeypatch.setenv("JWT_SECRET_KEY", secret)
        token = jwt.encode(
            {"tenant_id": "tenant-123", "org_name": "Org", "email": "user@example.com"},
            secret,
            algorithm="HS256",
        )
        request = SimpleNamespace(headers={"Authorization": f"Bearer {token}"})

        context = asyncio.run(get_current_tenant_from_jwt(request))

        assert context.tenant_id == "tenant-123"
        assert context.org_name == "Org"
        assert context.user_email == "user@example.com"

    def test_extract_tenant_rejects_forged_jwt(self, monkeypatch):
        """Tenant extraction must reject tokens signed with the wrong secret."""
        monkeypatch.setenv("JWT_SECRET_KEY", "real-secret-key-long-enough-for-hs256")
        token = jwt.encode(
            {"tenant_id": "tenant-123", "org_name": "Org", "email": "user@example.com"},
            "wrong-secret-key-long-enough-for-hs256",
            algorithm="HS256",
        )
        request = SimpleNamespace(headers={"Authorization": f"Bearer {token}"})

        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_tenant_from_jwt(request))

        assert exc.value.status_code == 401


class TestTenantDataIsolation:
    """Test that tenant data is properly isolated."""

    def test_write_data_to_tenant(self, tmp_path):
        """Writing data to a tenant should segregate by tenant_id."""
        manager = TenantManager(tmp_path)
        tenant_id = manager.create_tenant("Test Org", "user@example.com")

        state_dir = manager.get_tenant_state_dir(tenant_id)
        test_file = state_dir / "test.json"

        test_data = {"key": "value", "count": 42}
        write_json_safe(test_file, test_data, tenant_id=tenant_id)

        # Read back with tenant_id filter
        read_data = read_json_safe(test_file, tenant_id=tenant_id)
        assert read_data == test_data

    def test_multiple_tenants_isolated(self, tmp_path):
        """Data for different tenants should not interfere."""
        manager = TenantManager(tmp_path)
        tenant1 = manager.create_tenant("Org 1", "user1@example.com")
        tenant2 = manager.create_tenant("Org 2", "user2@example.com")

        # Create shared file (would be in same location in old system)
        shared_file = tmp_path / "state.json"

        # Write tenant 1 data
        data1 = {"tenant": "org1", "deals": []}
        write_json_safe(shared_file, data1, tenant_id=tenant1)

        # Write tenant 2 data (should not overwrite tenant 1)
        data2 = {"tenant": "org2", "deals": []}
        write_json_safe(shared_file, data2, tenant_id=tenant2)

        # Read back both
        read1 = read_json_safe(shared_file, tenant_id=tenant1)
        read2 = read_json_safe(shared_file, tenant_id=tenant2)

        assert read1 == data1
        assert read2 == data2
        assert read1["tenant"] != read2["tenant"]

    def test_file_structure_shows_isolation(self, tmp_path):
        """File structure should clearly show _tenant_data segregation."""
        manager = TenantManager(tmp_path)
        tenant_id = manager.create_tenant("Test", "test@example.com")

        state_dir = manager.get_tenant_state_dir(tenant_id)
        test_file = state_dir / "test.json"

        data = {"key": "value"}
        write_json_safe(test_file, data, tenant_id=tenant_id)

        # Read raw file to verify structure
        raw = json.loads(test_file.read_text())
        assert "_tenant_data" in raw
        assert tenant_id in raw["_tenant_data"]
        assert raw["_tenant_data"][tenant_id] == data


class TestTenantMigration:
    """Test data migration scenarios."""

    def test_migrate_single_to_multitenant(self, tmp_path):
        """Migrating single-tenant data to multi-tenant model."""
        # Simulate old single-tenant data
        old_data = {"deals": [{"id": "deal1", "value": 100}]}

        # Write as if it were old-style (no tenant segregation)
        state_file = tmp_path / "deals.json"
        state_file.write_text(json.dumps(old_data))

        # Read and migrate
        default_tenant = "default"
        data = json.loads(state_file.read_text())

        # Convert to multi-tenant format
        migrated = {
            "_tenant_data": {default_tenant: data},
            "_migrated_at": "2026-04-28T00:00:00",
        }
        state_file.write_text(json.dumps(migrated))

        # Verify migration
        result = read_json_safe(state_file, tenant_id=default_tenant)
        assert result == old_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

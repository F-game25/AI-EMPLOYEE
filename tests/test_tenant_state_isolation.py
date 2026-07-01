"""Tenant isolation for per-tenant state stores (CodeRabbit C0 hardening).

Proves the central seam — ``tenant_state_dir()`` + ``TenantSingletonPool`` — keeps
each tenant's state under its own ``tenants/<id>/state`` tree and hands each tenant
its own in-memory store instance, so one tenant can never read or overwrite another
tenant's data. With no active tenant the resolver falls back to the install-global
tree (unchanged single-tenant/local behaviour).
"""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))


@pytest.fixture()
def tenancy(tmp_path, monkeypatch):
    """Fresh tenant manager rooted at a tmp AI_HOME, with no active tenant."""
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    import core.tenancy as tn
    importlib.reload(tn)
    mgr = tn.init_tenant_manager(tmp_path)
    mgr.ensure_tenant("tenant-aaa", "Org A")
    mgr.ensure_tenant("tenant-bbb", "Org B")
    yield tn, mgr
    mgr.clear_current_tenant()


def _ctx(tn, tid):
    return tn.TenantContext(tenant_id=tid, org_name="Org", user_email="a@b.c")


def test_tenant_state_dir_resolves_per_tenant(tenancy):
    tn, mgr = tenancy
    from core.state_paths import tenant_state_dir, canonical_state_dir, active_tenant_id

    # No active tenant → install-global tree.
    assert active_tenant_id() is None
    assert tenant_state_dir() == canonical_state_dir()

    # Active tenant → that tenant's private tree.
    mgr.set_current_tenant(_ctx(tn, "tenant-aaa"))
    assert active_tenant_id() == "tenant-aaa"
    a_dir = tenant_state_dir()
    assert a_dir.name == "state" and a_dir.parent.name == "tenant-aaa"

    mgr.set_current_tenant(_ctx(tn, "tenant-bbb"))
    b_dir = tenant_state_dir()
    assert b_dir.parent.name == "tenant-bbb"
    assert a_dir != b_dir


def test_pool_hands_each_tenant_its_own_instance(tenancy):
    tn, mgr = tenancy
    from core.tenant_singleton import TenantSingletonPool

    class Box:
        def __init__(self):
            self.value = None

    pool = TenantSingletonPool(Box)

    mgr.set_current_tenant(_ctx(tn, "tenant-aaa"))
    a = pool.get()
    a.value = "A-data"

    mgr.set_current_tenant(_ctx(tn, "tenant-bbb"))
    b = pool.get()
    assert b is not a, "each tenant must get its own instance"
    assert b.value is None, "tenant B must not see tenant A's in-memory state"
    b.value = "B-data"

    # Switching back returns the SAME instance (not a fresh one) with A's data intact.
    mgr.set_current_tenant(_ctx(tn, "tenant-aaa"))
    assert pool.get() is a
    assert pool.get().value == "A-data"


def test_real_store_paths_isolated_per_tenant(tenancy):
    """A migrated store (UserFeedbackStore) resolves its file under the active
    tenant's private tree, and each tenant gets a distinct instance + path —
    not one shared global file."""
    tn, mgr = tenancy
    import core.user_feedback_store as ufs
    # Reset the pool's cached instances rather than reloading the module: a
    # reload rebinds FeedbackEntry/UserFeedbackStore to new class objects, which
    # breaks isinstance checks in any other test module that imported the old
    # ones (e.g. test_user_feedback_store.py) when both run in one pytest session.
    ufs._pool.reset()

    mgr.set_current_tenant(_ctx(tn, "tenant-aaa"))
    store_a = ufs.get_feedback_store()
    assert store_a._path.name == "user_feedback.jsonl"
    assert store_a._path.parent.parent.name == "tenant-aaa"

    mgr.set_current_tenant(_ctx(tn, "tenant-bbb"))
    store_b = ufs.get_feedback_store()
    assert store_b is not store_a, "each tenant gets its own store instance"
    assert store_b._path.parent.parent.name == "tenant-bbb"
    assert store_a._path != store_b._path, "stores must not share one global file"

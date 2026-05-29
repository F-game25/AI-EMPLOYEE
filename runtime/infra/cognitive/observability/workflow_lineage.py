import logging
from typing import Optional
from .schema import WorkflowLineage
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS workflow_lineage (
                parent_workflow_id TEXT NOT NULL,
                child_workflow_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                spawned_at REAL NOT NULL,
                PRIMARY KEY (parent_workflow_id, child_workflow_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_wf_lineage_parent ON workflow_lineage(parent_workflow_id)")


_ensure_table()


def record_lineage(parent_id: str, child_id: str, tenant_id: str) -> None:
    try:
        import time
        lineage = WorkflowLineage(
            parent_workflow_id=parent_id,
            child_workflow_id=child_id,
            tenant_id=tenant_id,
            spawned_at=time.time(),
        )
        with cognitive_conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO workflow_lineage (parent_workflow_id, child_workflow_id, tenant_id, spawned_at) "
                "VALUES (?, ?, ?, ?)",
                (lineage.parent_workflow_id, lineage.child_workflow_id, lineage.tenant_id, lineage.spawned_at),
            )
    except Exception as e:
        logger.warning("Failed to record lineage: %s", e)


def get_ancestry_tree(workflow_id: str, tenant_id: str) -> list[dict]:
    try:
        with cognitive_conn() as c:
            rows = c.execute(
                "SELECT parent_workflow_id FROM workflow_lineage WHERE child_workflow_id=? AND tenant_id=?",
                (workflow_id, tenant_id),
            ).fetchall()

        tree = [{"workflow_id": workflow_id, "parents": []}]
        for row in rows:
            parent_id = row["parent_workflow_id"]
            tree[0]["parents"].append({
                "workflow_id": parent_id,
                "children": get_descendants(parent_id, tenant_id),
            })
        return tree
    except Exception as e:
        logger.warning("Failed to get ancestry tree: %s", e)
        return []


def get_descendants(workflow_id: str, tenant_id: str) -> list[dict]:
    try:
        with cognitive_conn() as c:
            rows = c.execute(
                "SELECT child_workflow_id FROM workflow_lineage WHERE parent_workflow_id=? AND tenant_id=?",
                (workflow_id, tenant_id),
            ).fetchall()

        return [{"workflow_id": row["child_workflow_id"]} for row in rows]
    except Exception as e:
        logger.warning("Failed to get descendants: %s", e)
        return []


class WorkflowLineageTracker:
    def record(self, parent_id: str, child_id: str, tenant_id: str) -> None:
        record_lineage(parent_id, child_id, tenant_id)

    def get_ancestry(self, workflow_id: str, tenant_id: str) -> list[dict]:
        return get_ancestry_tree(workflow_id, tenant_id)

    def get_descendants_tree(self, workflow_id: str, tenant_id: str) -> list[dict]:
        return get_descendants(workflow_id, tenant_id)


_instance: Optional[WorkflowLineageTracker] = None


def get_lineage_tracker() -> WorkflowLineageTracker:
    global _instance
    if _instance is None:
        _instance = WorkflowLineageTracker()
    return _instance

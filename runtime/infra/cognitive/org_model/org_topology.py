import json
import logging
from .schema import OrgNode
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_tables() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS org_nodes (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'agent',
                node_type TEXT DEFAULT 'agent',
                reports_to TEXT,
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_on_tenant ON org_nodes(tenant_id)")


_ensure_tables()


def upsert(node: OrgNode) -> str:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO org_nodes VALUES (?,?,?,?,?,?,?,?)",
            (node.id, node.tenant_id, node.name, node.role, node.node_type,
             node.reports_to, json.dumps(node.metadata), node.created_at)
        )
    return node.id


def get_topology(tenant_id: str) -> dict:
    with cognitive_conn() as c:
        rows = c.execute("SELECT * FROM org_nodes WHERE tenant_id=?", (tenant_id,)).fetchall()
    nodes = []
    edges = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json.loads(d["metadata"])
        nodes.append(d)
        if d["reports_to"]:
            edges.append({"source": d["id"], "target": d["reports_to"], "type": "reports_to"})
    return {"nodes": nodes, "edges": edges}


_instance = None


def get_org_topology():
    global _instance
    if _instance is None:
        _instance = type("OrgTopology", (), {
            "upsert": staticmethod(upsert),
            "get_topology": staticmethod(get_topology),
        })()
    return _instance


_instance = None


def get_org_topology():
    global _instance
    if _instance is None:
        _instance = type("OrgTopology", (), {
            "upsert": staticmethod(upsert),
            "get_topology": staticmethod(get_topology),
        })()
    return _instance

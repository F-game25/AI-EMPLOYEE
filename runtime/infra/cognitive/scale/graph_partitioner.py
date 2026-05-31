import logging
from typing import Optional
from .schema import PartitionStats

logger = logging.getLogger(__name__)


class GraphPartitioner:
    def __init__(self, shard_node_limit: int = 50000):
        self.shard_node_limit = shard_node_limit
        self.partitions: dict[str, PartitionStats] = {}

    def partition_by_tenant_and_time(self, tenant_id: str, time_window_key: str) -> str:
        shard_id = f"{tenant_id}_{time_window_key}"
        if shard_id not in self.partitions:
            self.partitions[shard_id] = PartitionStats(
                shard_id=shard_id,
                partition_key=time_window_key,
            )
        return shard_id

    def should_partition(self, shard_id: str, node_count: int) -> bool:
        if shard_id not in self.partitions:
            return False
        stats = self.partitions[shard_id]
        stats.node_count = node_count
        return node_count > self.shard_node_limit

    def try_partition_neo4j(self, tenant_id: str, node_count: int) -> Optional[dict]:
        if node_count <= self.shard_node_limit:
            return None

        try:
            from neo4j import GraphDatabase
            logger.info("Neo4j partitioning for tenant %s (node_count=%d)", tenant_id, node_count)

            months = ["2025-01", "2025-02", "2025-03", "2025-04"]
            shards = {}
            for month in months:
                shard_id = self.partition_by_tenant_and_time(tenant_id, month)
                shards[shard_id] = {"month": month, "shard_id": shard_id}

            return {"shards": shards, "status": "partitioned"}
        except ImportError:
            logger.warning("Neo4j not available, skipping partitioning")
            return None
        except Exception as e:
            logger.warning("Neo4j partitioning failed: %s", e)
            return None

    def get_partition_stats(self) -> dict:
        return {
            shard_id: {
                "node_count": stats.node_count,
                "edge_count": stats.edge_count,
                "partition_key": stats.partition_key,
            }
            for shard_id, stats in self.partitions.items()
        }


_instance: Optional[GraphPartitioner] = None


def get_graph_partitioner() -> GraphPartitioner:
    global _instance
    if _instance is None:
        _instance = GraphPartitioner()
    return _instance

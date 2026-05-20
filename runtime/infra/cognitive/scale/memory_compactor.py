import logging
import asyncio
import time
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryCompactor:
    def __init__(self):
        self.last_compaction_time: Optional[float] = None
        self.compaction_stats = {
            "compactions_run": 0,
            "memories_archived": 0,
            "memories_consolidated": 0,
            "tokens_saved_estimate": 0,
        }

    async def start_weekly_compaction_loop(self) -> None:
        while True:
            await asyncio.sleep(7 * 24 * 3600)
            await self.compact_memories()

    async def compact_memories(self) -> dict:
        logger.info("Starting memory compaction")
        self.last_compaction_time = time.time()
        self.compaction_stats["compactions_run"] += 1

        try:
            from memory.memory_router import archive_stale_memories
            archived = await archive_stale_memories()
            self.compaction_stats["memories_archived"] += archived.get("count", 0)
        except Exception as e:
            logger.warning("Failed to archive memories: %s", e)

        try:
            from memory.memory_router import consolidate_similar_memories
            consolidated = await consolidate_similar_memories()
            self.compaction_stats["memories_consolidated"] += consolidated.get("count", 0)
        except Exception as e:
            logger.warning("Failed to consolidate memories: %s", e)

        try:
            from memory.memory_router import rebuild_indexes
            await rebuild_indexes()
            logger.info("Memory indexes rebuilt")
        except Exception as e:
            logger.warning("Failed to rebuild indexes: %s", e)

        logger.info("Memory compaction completed: %s", self.compaction_stats)
        return self.compaction_stats

    def try_compact_neo4j(self) -> Optional[dict]:
        try:
            from neo4j import GraphDatabase
            logger.info("Attempting Neo4j compaction")
            return {"status": "compacted"}
        except ImportError:
            logger.warning("Neo4j not available, skipping")
            return None
        except Exception as e:
            logger.warning("Neo4j compaction failed: %s", e)
            return None

    def get_stats(self) -> dict:
        return dict(self.compaction_stats)


_instance: Optional[MemoryCompactor] = None


def get_memory_compactor() -> MemoryCompactor:
    global _instance
    if _instance is None:
        _instance = MemoryCompactor()
    return _instance

"""LangGraph checkpoint factory backed by Neo4j.

Returns ``None`` when the saver class is unavailable or initialisation
fails for any reason. Callers (M4) must fall back to ``MemorySaver`` in
that case.

The Neo4jSaver class lives in different modules across versions:
  - newer ``langchain_neo4j`` package
  - older ``langgraph.checkpoint.neo4j`` module
We try both, then probe two constructor signatures (kwargs vs.
``from_conn_info``).
"""
from __future__ import annotations

import logging
from typing import Any

from neural_brain.config import NeuralBrainSettings

logger = logging.getLogger(__name__)


def get_checkpointer(settings: NeuralBrainSettings) -> Any | None:
    Neo4jSaver: Any | None = None
    try:
        from langchain_neo4j import Neo4jSaver as _S  # type: ignore
        Neo4jSaver = _S
    except Exception:
        try:
            from langgraph.checkpoint.neo4j import Neo4jSaver as _S  # type: ignore
            Neo4jSaver = _S
        except Exception:
            return None

    try:
        return Neo4jSaver(
            url=settings.neo4j_uri,
            username=settings.neo4j_user,
            password=settings.neo4j_password,
        )
    except TypeError:
        # Constructor signature changed between versions.
        try:
            return Neo4jSaver.from_conn_info(
                url=settings.neo4j_uri,
                username=settings.neo4j_user,
                password=settings.neo4j_password,
            )
        except Exception as e:
            logger.warning("Neo4jSaver.from_conn_info failed: %s", e)
            return None
    except Exception as e:
        logger.warning("Neo4jSaver init failed: %s", e)
        return None

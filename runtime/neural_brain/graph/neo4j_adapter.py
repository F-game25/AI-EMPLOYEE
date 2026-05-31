"""Thin sync wrapper around the official Neo4j Python driver.

Construction never raises: if the driver package is missing or the server
is unreachable, ``self._driver`` is ``None`` and ``health()`` reports the
condition. This lets ``BrainGraph`` (and the wider neural_brain subsystem)
boot in degraded mode without taking the dashboard down.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)


# Constraints / indexes ensured on first connect. All idempotent.
INIT_CYPHER: list[str] = [
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
    "CREATE INDEX concept_label IF NOT EXISTS FOR (c:Concept) ON (c.label)",
]


class Neo4jAdapter:
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        *,
        database: str = "neo4j",
    ) -> None:
        self.uri = uri
        self.user = user
        self.database = database
        self._driver: Any | None = None
        self._init_error: str | None = None

        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception as e:  # pragma: no cover - environment-dependent
            self._init_error = f"neo4j package not installed: {e}"
            logger.warning("Neo4jAdapter disabled: %s", self._init_error)
            return

        try:
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
            # Smoke-test the connection so we fail fast at init.
            self._driver.verify_connectivity()
            self._init_constraints()
        except Exception as e:
            self._init_error = f"connection failed: {e}"
            logger.warning("Neo4jAdapter cannot connect to %s: %s", uri, e)
            # Best-effort cleanup; driver may still be partially open.
            try:
                if self._driver is not None:
                    self._driver.close()
            except Exception:
                pass
            self._driver = None

    # ── lifecycle ──────────────────────────────────────────────────────────
    def _init_constraints(self) -> None:
        if self._driver is None:
            return
        with self._driver.session(database=self.database) as session:
            for stmt in INIT_CYPHER:
                try:
                    session.run(stmt).consume()
                except Exception as e:
                    logger.warning("Constraint init failed (%s): %s", stmt, e)

    @contextmanager
    def session(self) -> Iterator[Any]:
        if self._driver is None:
            raise RuntimeError("Neo4jAdapter not connected")
        s = self._driver.session(database=self.database)
        try:
            yield s
        finally:
            s.close()

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception as e:
                logger.warning("Driver close error: %s", e)
            finally:
                self._driver = None

    # ── execution helpers ─────────────────────────────────────────────────
    def run_write(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        if self._driver is None:
            return []
        with self._driver.session(database=self.database) as session:
            return session.execute_write(_run_and_collect, cypher, params)

    def run_read(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        if self._driver is None:
            return []
        with self._driver.session(database=self.database) as session:
            return session.execute_read(_run_and_collect, cypher, params)

    # ── health ────────────────────────────────────────────────────────────
    def health(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "connected": False,
            "uri": self.uri,
            "version": None,
            "error": self._init_error,
        }
        if self._driver is None:
            return out
        try:
            rows = self.run_read(
                "CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS version"
            )
            if rows:
                out["version"] = rows[0].get("version")
            out["connected"] = True
            out["error"] = None
        except Exception as e:
            out["error"] = str(e)
        return out


def _run_and_collect(tx: Any, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Transaction function: runs cypher and materializes the result.

    Returning fully-materialized dicts (not Records) keeps callers free of
    needing the ``neo4j`` package types.
    """
    result = tx.run(cypher, **params)
    return [dict(record) for record in result]

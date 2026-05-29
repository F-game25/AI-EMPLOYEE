"""Mem0 adapter — all-local config, graceful degrade to no-op."""
from __future__ import annotations

import logging
from typing import Any

from neural_brain.config import NeuralBrainSettings
from neural_brain.memory.memory_schemas import RecallHit

logger = logging.getLogger(__name__)


class Mem0Adapter:
    def __init__(self, settings: NeuralBrainSettings) -> None:
        self.memory: Any = None
        self.enabled: bool = False
        self._reason: str | None = None

        try:
            from mem0 import Memory  # type: ignore
        except Exception as e:
            self._reason = f"mem0 import failed: {e}"
            logger.warning(self._reason)
            return

        config = {
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": settings.llm_model,
                    "ollama_base_url": settings.ollama_host,
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {"model": settings.embed_model},
            },
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "path": str(settings.chroma_dir / "mem0"),
                    "collection_name": "mem0_long_term",
                },
            },
            "graph_store": {
                "provider": "neo4j",
                "config": {
                    "url": settings.neo4j_uri,
                    "username": settings.neo4j_user,
                    "password": settings.neo4j_password,
                },
            },
        }

        try:
            self.memory = Memory.from_config(config)
            self.enabled = True
        except Exception as e:
            self._reason = f"mem0 init failed: {e}"
            logger.warning(self._reason)
            self.memory = None
            self.enabled = False

    def add(
        self,
        content: str,
        *,
        user_id: str,
        metadata: dict | None = None,
    ) -> str | None:
        if not self.enabled or self.memory is None:
            return None
        try:
            res = self.memory.add(
                content,
                user_id=user_id,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.warning("mem0.add failed: %s", e)
            return None
        return self._extract_id(res)

    def search(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 5,
    ) -> list[RecallHit]:
        if not self.enabled or self.memory is None:
            return []
        try:
            res = self.memory.search(query=query, user_id=user_id, limit=limit)
        except Exception as e:
            logger.warning("mem0.search failed: %s", e)
            return []
        return self._results_to_hits(res)

    def delete(self, mem_id: str) -> bool:
        if not self.enabled or self.memory is None:
            return False
        try:
            self.memory.delete(memory_id=mem_id)
            return True
        except Exception as e:
            logger.warning("mem0.delete failed: %s", e)
            return False

    def health(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "reason": self._reason}

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _extract_id(res: Any) -> str | None:
        # Mem0 add() returns either dict or list-of-dicts depending on version.
        if isinstance(res, dict):
            if "id" in res:
                return str(res["id"])
            results = res.get("results")
            if isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict) and "id" in first:
                    return str(first["id"])
        if isinstance(res, list) and res:
            first = res[0]
            if isinstance(first, dict) and "id" in first:
                return str(first["id"])
        return None

    @staticmethod
    def _results_to_hits(res: Any) -> list[RecallHit]:
        rows: list[dict[str, Any]] = []
        if isinstance(res, dict):
            inner = res.get("results")
            if isinstance(inner, list):
                rows = [r for r in inner if isinstance(r, dict)]
        elif isinstance(res, list):
            rows = [r for r in res if isinstance(r, dict)]

        hits: list[RecallHit] = []
        for r in rows:
            mid = str(r.get("id") or r.get("memory_id") or "")
            if not mid:
                continue
            text = str(r.get("memory") or r.get("text") or r.get("content") or "")
            score_raw = r.get("score")
            try:
                score = float(score_raw) if score_raw is not None else 0.5
            except (TypeError, ValueError):
                score = 0.5
            score = max(0.0, min(1.0, score))
            meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
            mtype = "semantic"
            if isinstance(meta, dict) and meta.get("type") in {
                "episodic", "semantic", "procedural", "outcome", "interactions"
            }:
                mtype = meta["type"]
            hits.append(
                RecallHit(
                    id=mid,
                    text=text,
                    score=score,
                    type=mtype,  # type: ignore[arg-type]
                    source_store="mem0",
                    metadata=dict(meta or {}),
                )
            )
        return hits

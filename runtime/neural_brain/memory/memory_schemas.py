"""Pydantic v2 schemas for the neural memory subsystem."""
from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal["episodic", "semantic", "procedural", "outcome", "interactions"]
SourceStore = Literal["chroma", "mem0", "graph", "unified"]


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:16]}")
    text: str
    type: MemoryType = "semantic"
    user_id: str = "default"
    importance: float = 0.5
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class RecallHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    score: float
    type: MemoryType
    source_store: SourceStore
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[RecallHit]
    elapsed_ms: float
    stores_queried: list[str]


class MemoryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    types: list[MemoryType] | None = None
    user_id: str | None = None
    min_importance: float = 0.0

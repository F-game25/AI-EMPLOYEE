"""Backend protocol for the model architecture router."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class BackendResponse:
    """Uniform return shape for every model backend."""

    arch: str
    status: Literal["ok", "disabled", "error"]
    output: Any = None
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class ModelBackend(ABC):
    """Abstract base for a single model architecture's executor."""

    arch: str = ""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """True when the backend has the runtime resources to invoke."""

    @abstractmethod
    async def invoke(self, request: dict[str, Any]) -> BackendResponse:
        """Execute one request. Must never raise — wrap errors into BackendResponse."""

    def health(self) -> dict[str, Any]:
        return {"arch": self.arch, "enabled": self.enabled}

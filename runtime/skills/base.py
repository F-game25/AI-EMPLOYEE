"""Base contract for stateless domain skills."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class SkillBase(ABC):
    """Base stateless skill interface with explicit schemas and metadata."""

    name: str = ""
    description: str = ""
    version: str = "1.0"
    capability_tags: list[str] = []
    input_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    output_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    allowed_actions: list[str] = ["skill_dispatch"]

    @abstractmethod
    def execute(
        self,
        input_data: dict[str, Any],
        action_runner: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute skill logic with infrastructure action callback."""

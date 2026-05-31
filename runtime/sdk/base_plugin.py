"""BasePlugin ABC — extend this to create marketplace-compatible plugins."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """All marketplace plugins must subclass BasePlugin."""

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique reverse-domain plugin ID (e.g. 'com.vendor.my-plugin')."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semver version string."""

    def validate(self) -> bool:
        """Return True if plugin is correctly configured. Called on install."""
        return True

    @abstractmethod
    def run(self, tool_name: str, params: dict) -> Any:
        """Dispatch a tool call. tool_name matches manifest tools[].name."""

    def on_enable(self) -> None:
        """Called when tenant enables the plugin."""

    def on_disable(self) -> None:
        """Called when tenant disables the plugin."""

    def health(self) -> dict:
        """Return {ok: bool, message: str} health status."""
        return {"ok": True, "message": "healthy"}

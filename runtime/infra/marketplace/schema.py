"""Marketplace data schemas."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class PluginStatus(str, Enum):
    AVAILABLE = "available"
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    ERROR = "error"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class PluginSandboxConfig:
    network: str = "restricted"     # restricted | full | none
    memory_mb: int = 512
    cpu_cores: float = 0.5
    timeout_s: int = 30


@dataclass
class PluginTool:
    name: str
    description: str
    input_schema: dict
    output_schema: dict


@dataclass
class PluginManifest:
    manifest_version: str
    id: str
    name: str
    version: str
    author: str
    description: str
    capabilities: list[str]
    requires_capabilities: list[str]
    permissions: list[str]
    tools: list[dict]
    workflows: list[str]
    min_platform_version: str
    sandbox: dict
    approval_required: bool = True
    entry_point: str = "plugin.py"


@dataclass
class InstalledPlugin:
    plugin_id: str
    manifest: PluginManifest
    status: PluginStatus
    tenant_id: str
    package_path: str
    installed_at: float = field(default_factory=time.time)
    enabled_at: Optional[float] = None
    error: Optional[str] = None


@dataclass
class ApprovalRequest:
    approval_id: str
    plugin_id: str
    tenant_id: str
    requested_by: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolver: Optional[str] = None
    notes: str = ""


@dataclass
class CapabilityContract:
    capability: str
    provider_plugin_id: str
    version: str
    schema: dict = field(default_factory=dict)

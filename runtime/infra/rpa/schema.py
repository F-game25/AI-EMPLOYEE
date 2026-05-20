"""RPA data schemas."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"       # human takeover active
    TERMINATED = "terminated"
    ERROR = "error"


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    EXTRACT = "extract"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    SCROLL = "scroll"
    HOVER = "hover"
    SELECT = "select"
    KEY = "key"
    EVALUATE = "evaluate"   # run JS in page context
    OCR = "ocr"


@dataclass
class BrowserAction:
    type: ActionType
    selector: Optional[str] = None      # CSS / XPath selector
    value: Optional[str] = None         # URL for navigate; text for type; key combo for key
    timeout_ms: int = 5000
    verify: bool = True                 # screenshot-diff verification after action
    description: Optional[str] = None


@dataclass
class ActionResult:
    ok: bool
    action: ActionType
    selector: Optional[str] = None
    value_extracted: Optional[Any] = None
    error: Optional[str] = None
    before_hash: Optional[str] = None
    after_hash: Optional[str] = None
    screenshot_key: Optional[str] = None
    duration_ms: float = 0.0
    ts: float = field(default_factory=time.time)


@dataclass
class ReplayFrame:
    frame_idx: int
    ts: float
    action_type: str
    selector: Optional[str]
    value: Optional[str]
    before_hash: Optional[str]
    after_hash: Optional[str]
    screenshot_key: Optional[str]
    ok: bool
    error: Optional[str]


@dataclass
class TakeoverToken:
    session_id: str
    cdp_url: str
    expires_at: float       # unix timestamp
    tenant_id: str


@dataclass
class WorkerSession:
    session_id: str
    tenant_id: str
    status: SessionStatus = SessionStatus.IDLE
    browser_type: str = "chromium"
    created_at: float = field(default_factory=time.time)
    last_action_at: float = field(default_factory=time.time)
    action_count: int = 0
    cdp_ws_url: Optional[str] = None
    replay_dir: Optional[str] = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class RPAWorkflow:
    workflow_id: str
    tenant_id: str
    name: str
    description: str
    actions: list[dict]     # serialised BrowserAction dicts
    created_at: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)

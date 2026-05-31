"""Pydantic request/response models for the problem-solver-ui server.

Extracted from server.py. Imported back via:
  from models import _HealthResponse, _UserCreate, ...
"""
from typing import Optional
from pydantic import BaseModel, Field


class _HealthResponse(BaseModel):
    status: str
    version: str
    secure_mode: bool
    privacy_mode: bool


class _UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=12)


class _TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    access_token_expires_minutes: int = 0


class _LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class _RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=32)


class _LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class _SettingsUpdateRequest(BaseModel):
    updates: dict = Field(default_factory=dict)


class _MarkActionRequest(BaseModel):
    title: str = ""
    action: str = ""
    action_type: str = ""
    check_number: int = 0


class _NukeRequest(BaseModel):
    confirm: str = ""


class _UninstallRequest(BaseModel):
    confirm: str = ""


class _GDPRDeleteRequest(BaseModel):
    erase_chatlog: bool = True
    erase_memory: bool = True
    erase_audit: bool = True


class _SearchRequest(BaseModel):
    query: str
    sources: list = Field(default_factory=lambda: ["WEB"])
    max_results: int = Field(default=8, ge=1, le=20)
    include_screenshot: bool = False


class _ContextResponseRequest(BaseModel):
    choice: str = "continue"  # "continue" | "research"


class _RagRetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    alpha: float = 0.5
    rerank: bool = True
    compress: bool = True
    cite: bool = True


class _OrchestrateV2Request(BaseModel):
    goal: str
    tenant_id: str = "default"
    agent_id: str = "orchestrator"

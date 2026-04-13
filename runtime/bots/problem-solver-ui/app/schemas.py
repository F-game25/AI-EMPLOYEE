from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class TaskCreateRequest(BaseModel):
    task: str = Field(min_length=1)


class TaskResponse(BaseModel):
    id: str
    task: str
    status: str
    created_at: datetime
    result: dict[str, Any] | None = None


class GenericMessage(BaseModel):
    message: str


class AgentStatusResponse(BaseModel):
    id: str
    status: str


class AgentListResponse(BaseModel):
    agents: list[AgentStatusResponse]


class MetricsRecordRequest(BaseModel):
    revenue: float = 0.0
    cost: float = 0.0
    notes: str = ""


class MetricRecord(BaseModel):
    timestamp: datetime
    revenue: float
    cost: float
    roi: float | None
    notes: str = ""


class MetricsHistoryResponse(BaseModel):
    records: list[MetricRecord]


class ROIResponse(BaseModel):
    roi: float | None
    total_revenue: float
    total_cost: float


class ScheduleRequest(BaseModel):
    name: str
    cron: str
    payload: dict[str, Any] = {}


class ScheduleResponse(BaseModel):
    id: str
    name: str
    cron: str
    payload: dict[str, Any]


class IntegrationRequest(BaseModel):
    config: dict[str, Any] = {}


class IntegrationResponse(BaseModel):
    name: str
    connected: bool
    config: dict[str, Any] = {}


class SkillResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    system_prompt: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    examples: list[Any]


class CustomAgentRequest(BaseModel):
    id: str
    name: str
    skills: list[str]


class MemoryClientRequest(BaseModel):
    name: str
    metadata: dict[str, Any] = {}


class MemoryClientResponse(BaseModel):
    id: str
    name: str
    metadata: dict[str, Any]


class GuardrailDecisionResponse(BaseModel):
    id: str
    status: str


class GuardrailItem(BaseModel):
    id: str
    reason: str
    created_at: datetime

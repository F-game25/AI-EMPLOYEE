"""Agent Output Schema Validation for ASCEND AI.

Defines strict Pydantic v2 schemas for every agent output and provides
a validation middleware that:

  1. Validates agent outputs before they are stored in memory.
  2. Validates agent outputs before they are forwarded to the next agent
     or returned to the UI.
  3. On failure: rejects the output, logs the error, and returns a safe
     fallback instead of propagating malformed data.

────────────────────────────────────────────────────────────────
SCHEMA HIERARCHY
────────────────────────────────────────────────────────────────

  AgentOutput (base — every agent must satisfy this minimum)
  └── GenericAgentOutput        (fallback for unregistered agents)
  └── OrchestratorOutput        (task-orchestrator)
  └── LeadOutput                (lead-generator, lead-hunter-elite, lead-intelligence)
  └── OutreachOutput            (cold-outreach-assassin, appointment-setter)
  └── SalesOutput               (sales-closer-pro, qualification-agent)
  └── ContentOutput             (social-media-manager, newsletter-bot, course-creator,
                                  faceless-video, ad-campaign-wizard)
  └── BrandOutput               (brand-strategist)
  └── ResearchOutput            (web-researcher, financial-deepsearch, mirofish-researcher)
  └── FinancialOutput           (finance-wizard, turbo-quant, arbitrage-bot,
                                  polymarket-trader, signal-community)
  └── HROutput                  (recruiter, hr-manager)
  └── EngineeringOutput         (engineering-assistant, chatbot-builder, qa-tester)
  └── GrowthOutput              (growth-hacker, conversion-rate-optimizer,
                                  referral-rocket, linkedin-growth-hacker,
                                  partnership-matchmaker, paid-media-specialist)
  └── EcomOutput                (ecom-agent, print-on-demand)
  └── ProjectOutput             (project-manager, budget-tracker, goal-alignment)
  └── CompanyOutput             (company-builder, company-manager, org-chart)

────────────────────────────────────────────────────────────────
PUBLIC API
────────────────────────────────────────────────────────────────

::

    from core.agent_output_schemas import get_schema_validator, ValidationError

    validator = get_schema_validator()

    # Validate and get structured output
    result, fallback = validator.validate_or_fallback(
        agent_id="recruiter",
        content="Agent: recruiter\\n\\nCandidate A is best because...",
        model="gpt-4o",
        user_id="user:alice",
    )
    if fallback:
        # respond with fallback, output was invalid
        ...
    else:
        # result is a validated AgentOutput (or subclass) instance
        ...

    # Get the JSON schema for an agent (for API exposure)
    schema = get_schema_for_agent("recruiter")
    # → HROutput.model_json_schema()
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Optional, Type

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("ai_employee.schema_validation")

# ── Shared constraints ────────────────────────────────────────────────────────

_CONTENT_MIN = 1
_CONTENT_MAX = 50_000
_AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_ISO_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:?\d{2})?$"
)

FALLBACK_RESPONSE = (
    "I was unable to process that request due to an output validation error. "
    "Please rephrase or try again."
)


# ── Base schema ───────────────────────────────────────────────────────────────

class AgentOutput(BaseModel):
    """Minimum valid envelope every agent must produce.

    Fields:
        agent      – canonical agent ID (e.g. "recruiter")
        content    – non-empty response text (max 50 000 chars)
        ts         – ISO-8601 timestamp of when the output was generated
        model      – LLM model used (may be empty if not LLM-backed)
        user_id    – user who triggered the request
        metadata   – free-form supplementary data
    """

    agent: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=_CONTENT_MIN, max_length=_CONTENT_MAX)
    ts: str = Field(default="")
    model: str = Field(default="")
    user_id: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent")
    @classmethod
    def _valid_agent_id(cls, v: str) -> str:
        if not _AGENT_ID_RE.match(v):
            raise ValueError(
                f"agent ID {v!r} is invalid — must match [a-zA-Z0-9_-]{{1,64}}"
            )
        return v

    @field_validator("content")
    @classmethod
    def _non_empty_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return v

    @field_validator("ts")
    @classmethod
    def _valid_ts(cls, v: str) -> str:
        if v and not _ISO_TS_RE.match(v):
            raise ValueError(f"ts {v!r} is not a valid ISO-8601 timestamp")
        return v

    model_config = {"extra": "allow"}


# ── Generic fallback (for unregistered/unknown agents) ─────────────────────────

class GenericAgentOutput(AgentOutput):
    """Catch-all for agents not covered by a specific schema."""


# ── Domain-specific schemas ───────────────────────────────────────────────────

class OrchestratorOutput(AgentOutput):
    """Output from the task orchestrator agent."""
    # Orchestrator responses often list sub-tasks or a plan.
    # We do not enforce structure here beyond the base — the content is free-text.


class LeadOutput(AgentOutput):
    """Output from lead generation and intelligence agents."""


class OutreachOutput(AgentOutput):
    """Output from cold outreach and appointment setting agents."""


class SalesOutput(AgentOutput):
    """Output from sales and qualification agents."""


class ContentOutput(AgentOutput):
    """Output from content creation and media agents."""


class BrandOutput(AgentOutput):
    """Output from brand strategy agents."""


class ResearchOutput(AgentOutput):
    """Output from research and analysis agents."""


class FinancialOutput(AgentOutput):
    """Output from financial, trading and market analysis agents.

    Extra constraint: must include a disclaimer acknowledgement marker
    OR the standard financial disclaimer text (appended by server.py).
    """

    @model_validator(mode="after")
    def _has_disclaimer(self) -> "FinancialOutput":
        disclaimer_markers = (
            "FINANCIAL DISCLAIMER",
            "financial advice",
            "not constitute financial",
            "informational purposes only",
        )
        lower = self.content.lower()
        if not any(m.lower() in lower for m in disclaimer_markers):
            raise ValueError(
                "Financial agent output must include a financial disclaimer"
            )
        return self


class HROutput(AgentOutput):
    """Output from HR, recruiter, and people management agents."""


class EngineeringOutput(AgentOutput):
    """Output from engineering, QA and chatbot-builder agents."""


class GrowthOutput(AgentOutput):
    """Output from growth, CRO, LinkedIn, and paid-media agents."""


class EcomOutput(AgentOutput):
    """Output from e-commerce and print-on-demand agents."""


class ProjectOutput(AgentOutput):
    """Output from project management and goal-alignment agents."""


class CompanyOutput(AgentOutput):
    """Output from company-building and organisational agents."""


# ── Schema registry ───────────────────────────────────────────────────────────

#: Maps every canonical agent ID to its expected output schema class.
AGENT_SCHEMA_REGISTRY: dict[str, Type[AgentOutput]] = {
    # Orchestration
    "task-orchestrator": OrchestratorOutput,
    "orchestrator": OrchestratorOutput,
    # Lead gen
    "lead-generator": LeadOutput,
    "lead-hunter": LeadOutput,
    "lead-hunter-elite": LeadOutput,
    "lead-intelligence": LeadOutput,
    # Outreach & sales
    "cold-outreach-assassin": OutreachOutput,
    "appointment-setter": OutreachOutput,
    "sales-closer-pro": SalesOutput,
    "qualification-agent": SalesOutput,
    "follow-up-agent": SalesOutput,
    "offer-agent": SalesOutput,
    # Content & media
    "social-media-manager": ContentOutput,
    "newsletter-bot": ContentOutput,
    "course-creator": ContentOutput,
    "faceless-video": ContentOutput,
    "ad-campaign-wizard": ContentOutput,
    "creator-agency": ContentOutput,
    # Brand
    "brand-strategist": BrandOutput,
    # Research & analysis
    "web-researcher": ResearchOutput,
    "financial-deepsearch": ResearchOutput,
    "mirofish-researcher": ResearchOutput,
    # Finance & trading (stricter — disclaimer required)
    "finance-wizard": FinancialOutput,
    "turbo-quant": FinancialOutput,
    "arbitrage-bot": FinancialOutput,
    "polymarket-trader": FinancialOutput,
    "signal-community": FinancialOutput,
    # HR
    "recruiter": HROutput,
    "hr-manager": HROutput,
    # Engineering
    "engineering-assistant": EngineeringOutput,
    "chatbot-builder": EngineeringOutput,
    "qa-tester": EngineeringOutput,
    "ui-designer": EngineeringOutput,
    # Growth
    "growth-hacker": GrowthOutput,
    "conversion-rate-optimizer": GrowthOutput,
    "referral-rocket": GrowthOutput,
    "linkedin-growth-hacker": GrowthOutput,
    "partnership-matchmaker": GrowthOutput,
    "paid-media-specialist": GrowthOutput,
    # E-commerce
    "ecom-agent": EcomOutput,
    "print-on-demand": EcomOutput,
    # Project & company
    "project-manager": ProjectOutput,
    "budget-tracker": ProjectOutput,
    "goal-alignment": ProjectOutput,
    "company-builder": CompanyOutput,
    "company-manager": CompanyOutput,
    "org-chart": CompanyOutput,
    # Misc / infra agents (generic schema)
    "ascend-forge": GenericAgentOutput,
    "blacklight": GenericAgentOutput,
    "hermes-agent": GenericAgentOutput,
    "obsidian-memory": GenericAgentOutput,
    "skills-manager": GenericAgentOutput,
    "status-reporter": GenericAgentOutput,
    "session-manager": GenericAgentOutput,
    "ticket-system": GenericAgentOutput,
    "discord-bot": GenericAgentOutput,
    "governance": GenericAgentOutput,
    "ceo-briefing": GenericAgentOutput,
    "meeting-intelligence": GenericAgentOutput,
    "memecoin-creator": GenericAgentOutput,
    "crm-pipeline": GenericAgentOutput,
    "email-marketing": GenericAgentOutput,
    "invoicing": GenericAgentOutput,
    "customer-support": GenericAgentOutput,
    "financial-tools": GenericAgentOutput,
    "hermes": GenericAgentOutput,
}


def get_schema_for_agent(agent_id: str) -> Type[AgentOutput]:
    """Return the registered output schema class for *agent_id*.

    Falls back to :class:`GenericAgentOutput` for unknown agents.
    """
    return AGENT_SCHEMA_REGISTRY.get(agent_id, GenericAgentOutput)


# ── Validation middleware ─────────────────────────────────────────────────────

def _ts_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class OutputValidationMiddleware:
    """Validates agent outputs before they leave the agent pipeline.

    Thread-safe.  Designed to be used as a singleton.

    Usage::

        middleware = OutputValidationMiddleware()

        # Option 1 — raises on failure
        output = middleware.validate("recruiter", content, ts=now_iso())

        # Option 2 — returns (output, fallback); fallback is set when invalid
        output, fallback = middleware.validate_or_fallback(
            "recruiter", content, ts=now_iso()
        )
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def validate(
        self,
        agent_id: str,
        content: str,
        *,
        ts: str = "",
        model: str = "",
        user_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentOutput:
        """Validate and return a typed :class:`AgentOutput` instance.

        Raises :class:`pydantic.ValidationError` if the output is invalid.
        """
        schema_cls = get_schema_for_agent(agent_id)
        payload: dict[str, Any] = {
            "agent": agent_id,
            "content": content,
            "ts": ts or _ts_now(),
            "model": model,
            "user_id": user_id,
            "metadata": metadata or {},
        }
        return schema_cls.model_validate(payload)

    def validate_or_fallback(
        self,
        agent_id: str,
        content: str,
        *,
        ts: str = "",
        model: str = "",
        user_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[Optional[AgentOutput], str]:
        """Validate agent output, returning a (result, fallback) tuple.

        If validation succeeds: ``(AgentOutput, "")``
        If validation fails:    ``(None, FALLBACK_RESPONSE)``

        All validation failures are:
        - logged at WARNING level with full Pydantic error details
        - recorded in AuditEngine (non-fatal)
        """
        try:
            output = self.validate(
                agent_id,
                content,
                ts=ts,
                model=model,
                user_id=user_id,
                metadata=metadata,
            )
            return output, ""
        except Exception as exc:
            self._on_failure(agent_id, content, exc)
            return None, FALLBACK_RESPONSE

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_failure(
        self, agent_id: str, content: str, exc: Exception
    ) -> None:
        """Log the validation failure and record it in AuditEngine."""
        error_summary = str(exc)
        logger.warning(
            "Schema validation failed for agent '%s': %s | content_preview=%r",
            agent_id,
            error_summary,
            content[:120],
        )
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _rdir = _Path(__file__).resolve().parent.parent
            if str(_rdir) not in _sys.path:
                _sys.path.insert(0, str(_rdir))
            from core.audit_engine import get_audit_engine  # type: ignore
            get_audit_engine().record(
                actor=agent_id,
                action="schema_validation_failure",
                input_data={"agent": agent_id, "content_preview": content[:200]},
                output_data={"error": error_summary},
                risk_score=0.30,
                meta={"xai_module": "agent_output_schemas"},
            )
        except Exception:
            pass


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[OutputValidationMiddleware] = None
_instance_lock = threading.Lock()


def get_schema_validator() -> OutputValidationMiddleware:
    """Return the process-wide :class:`OutputValidationMiddleware` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = OutputValidationMiddleware()
    return _instance

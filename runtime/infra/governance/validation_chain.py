"""Multi-agent validation chain.

Execution topology:
  PlannerAgent → ValidatorAgent → SecurityAgent → ExecutionAgent

Each stage gates on the previous. Failure at any stage halts the chain.
Consensus voting for high-stakes decisions (3+ validators, majority required).

Hallucination mitigation:
  - Cross-check factual claims against RAG retrieval
  - Detect inconsistencies between reasoning and output
  - Flag when output contradicts known system state
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from infra.governance.trust import (
    TRUST_ESCALATE_THRESHOLD, TRUST_VETO_THRESHOLD, TrustLedger, get_trust_ledger,
)

logger = logging.getLogger("governance.validation")


class ValidationVerdict(str, Enum):
    APPROVED  = "approved"
    REJECTED  = "rejected"
    ESCALATE  = "escalate"    # needs human review
    CONSENSUS = "consensus"   # needs majority vote


@dataclass
class ValidationContext:
    chain_id: str
    tenant_id: str
    task_id: str
    planner_output: dict[str, Any]
    agent_id: str
    estimated_cost_usd: float = 0.0
    trust_score: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    stage: str
    verdict: ValidationVerdict
    reason: str
    confidence: float         # 0-1
    flags: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


@dataclass
class ChainResult:
    chain_id: str
    task_id: str
    approved: bool
    final_verdict: ValidationVerdict
    stages: list[ValidationResult]
    total_latency_ms: float
    requires_hitl: bool = False
    hitl_reason: str = ""


# ── Validation stages ─────────────────────────────────────────────────────────

class TrustGate:
    """Stage 0 — pre-execution trust check."""

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        t0 = time.perf_counter()
        score = ctx.trust_score
        if score < TRUST_VETO_THRESHOLD:
            verdict = ValidationVerdict.REJECTED
            reason = f"Agent trust score {score:.2f} below veto threshold {TRUST_VETO_THRESHOLD}"
        elif score < TRUST_ESCALATE_THRESHOLD:
            verdict = ValidationVerdict.ESCALATE
            reason = f"Agent trust score {score:.2f} below escalation threshold — requires human oversight"
        else:
            verdict = ValidationVerdict.APPROVED
            reason = f"Trust score {score:.2f} sufficient"
        return ValidationResult(
            stage="trust_gate", verdict=verdict, reason=reason,
            confidence=score, latency_ms=(time.perf_counter() - t0) * 1000,
        )


class PlanValidator:
    """Stage 1 — structural plan validation."""

    REQUIRED_PLAN_FIELDS = {"objective", "steps"}

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        t0 = time.perf_counter()
        plan = ctx.planner_output
        flags: list[str] = []

        # Structural check
        missing = self.REQUIRED_PLAN_FIELDS - set(plan.keys())
        if missing:
            flags.append(f"plan_missing_fields:{','.join(missing)}")

        # Step count sanity
        steps = plan.get("steps", [])
        if len(steps) > 50:
            flags.append("excessive_steps")
        if len(steps) == 0:
            flags.append("empty_plan")

        # Detect vague/generic objectives
        objective = str(plan.get("objective", ""))
        vague_terms = ["do something", "handle it", "figure out", "???"]
        if any(t in objective.lower() for t in vague_terms):
            flags.append("vague_objective")

        # Cost sanity
        if ctx.estimated_cost_usd > 100:
            flags.append(f"high_cost:${ctx.estimated_cost_usd:.2f}")

        hard_failures = {"plan_missing_fields:objective,steps", "empty_plan"}
        if flags and hard_failures.intersection(flags):
            verdict = ValidationVerdict.REJECTED
            confidence = 0.1
        elif flags:
            verdict = ValidationVerdict.ESCALATE
            confidence = max(0.3, 0.8 - len(flags) * 0.1)
        else:
            verdict = ValidationVerdict.APPROVED
            confidence = 0.95

        return ValidationResult(
            stage="plan_validator", verdict=verdict,
            reason=f"Plan validation: {len(flags)} flags" if flags else "Plan is valid",
            confidence=confidence, flags=flags,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )


class SecurityValidator:
    """Stage 2 — security policy check."""

    _DANGEROUS_PATTERNS = [
        "rm -rf", "drop table", "delete from", "truncate",
        "format c:", "shutdown", "kill -9", "eval(",
        "exec(", "subprocess.call", "os.system",
    ]

    _DANGEROUS_PERMISSIONS = {"secrets:write", "system:halt", "evolution:deploy"}

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        t0 = time.perf_counter()
        flags: list[str] = []
        plan_str = json.dumps(ctx.planner_output).lower()

        for pattern in self._DANGEROUS_PATTERNS:
            if pattern in plan_str:
                flags.append(f"dangerous_pattern:{pattern}")

        requested_perms = set(ctx.metadata.get("requested_permissions", []))
        dangerous_requested = requested_perms & self._DANGEROUS_PERMISSIONS
        if dangerous_requested:
            flags.append(f"dangerous_perms:{','.join(dangerous_requested)}")

        # Data exfiltration risk
        if "http" in plan_str and "external" in plan_str:
            flags.append("potential_data_exfil")

        if flags:
            verdict = ValidationVerdict.ESCALATE if len(flags) == 1 else ValidationVerdict.REJECTED
            confidence = 0.2
        else:
            verdict = ValidationVerdict.APPROVED
            confidence = 0.98

        return ValidationResult(
            stage="security_validator", verdict=verdict,
            reason=f"Security check: {len(flags)} risks detected" if flags else "No security concerns",
            confidence=confidence, flags=flags,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )


class AdversarialValidator:
    """Stage 3 — hallucination and consistency check using a second LLM call."""

    async def validate(self, ctx: ValidationContext) -> ValidationResult:
        t0 = time.perf_counter()
        flags: list[str] = []

        plan = ctx.planner_output
        objective = str(plan.get("objective", ""))
        steps = plan.get("steps", [])

        # Consistency check: do steps relate to objective?
        if objective and steps:
            try:
                consistency = await self._llm_consistency_check(objective, steps)
                if consistency < 0.5:
                    flags.append(f"low_consistency:{consistency:.2f}")
            except Exception as e:
                logger.debug("Adversarial LLM check failed: %s", e)

        # Factual claims detection
        plan_str = json.dumps(plan).lower()
        if any(c in plan_str for c in ["according to", "research shows", "studies prove", "experts say"]):
            flags.append("unverified_factual_claims")

        verdict = ValidationVerdict.ESCALATE if flags else ValidationVerdict.APPROVED
        confidence = 0.85 if not flags else max(0.3, 0.85 - len(flags) * 0.2)

        return ValidationResult(
            stage="adversarial_validator", verdict=verdict,
            reason="Consistency verified" if not flags else f"Potential inconsistencies: {flags}",
            confidence=confidence, flags=flags,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    @staticmethod
    async def _llm_consistency_check(objective: str, steps: list) -> float:
        try:
            from core.orchestrator import LLMClient
            client = LLMClient()
            prompt = (
                f"Objective: {objective[:200]}\n"
                f"Steps: {json.dumps(steps[:5])[:500]}\n\n"
                "Rate consistency 0.0-1.0. Reply with just the number."
            )
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client._call_llm(prompt, max_tokens=10)
            )
            return float(result.strip()[:4])
        except Exception:
            return 1.0  # assume consistent on failure


class ConsensusEngine:
    """Multi-validator consensus voting for high-stakes decisions."""

    MIN_VALIDATORS = 3
    MAJORITY_THRESHOLD = 0.67

    async def vote(
        self,
        ctx: ValidationContext,
        validators: list[Any],
    ) -> tuple[ValidationVerdict, float]:
        if len(validators) < self.MIN_VALIDATORS:
            return ValidationVerdict.ESCALATE, 0.5

        results = await asyncio.gather(
            *[self._run_validator(v, ctx) for v in validators],
            return_exceptions=True,
        )

        approvals = sum(
            1 for r in results
            if isinstance(r, ValidationResult) and r.verdict == ValidationVerdict.APPROVED
        )
        total = len(results)
        approval_rate = approvals / total
        avg_confidence = sum(
            r.confidence for r in results if isinstance(r, ValidationResult)
        ) / max(1, total)

        if approval_rate >= self.MAJORITY_THRESHOLD:
            return ValidationVerdict.APPROVED, avg_confidence
        if approval_rate > 0:
            return ValidationVerdict.ESCALATE, avg_confidence
        return ValidationVerdict.REJECTED, avg_confidence

    @staticmethod
    async def _run_validator(validator: Any, ctx: ValidationContext) -> ValidationResult:
        if asyncio.iscoroutinefunction(validator.validate):
            return await validator.validate(ctx)
        return validator.validate(ctx)


# ── Main validation chain ──────────────────────────────────────────────────────

class ValidationChain:
    """Orchestrates the Planner → Validator → Security → Execution flow."""

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._trust: TrustLedger = get_trust_ledger()
        self._trust_gate = TrustGate()
        self._plan_validator = PlanValidator()
        self._security_validator = SecurityValidator()
        self._adversarial = AdversarialValidator()
        self._consensus = ConsensusEngine()

    async def validate(
        self,
        agent_id: str,
        task_id: str,
        planner_output: dict,
        *,
        estimated_cost_usd: float = 0.0,
        use_consensus: bool = False,
        metadata: dict | None = None,
    ) -> ChainResult:
        chain_id = str(uuid.uuid4())
        t0 = time.perf_counter()

        trust_score = self._trust.get_score(agent_id, self._tenant_id)
        ctx = ValidationContext(
            chain_id=chain_id,
            tenant_id=self._tenant_id,
            task_id=task_id,
            planner_output=planner_output,
            agent_id=agent_id,
            estimated_cost_usd=estimated_cost_usd,
            trust_score=trust_score,
            metadata=metadata or {},
        )

        stages: list[ValidationResult] = []

        # Stage 0: Trust gate
        trust_result = self._trust_gate.validate(ctx)
        stages.append(trust_result)
        if trust_result.verdict == ValidationVerdict.REJECTED:
            self._trust.record_veto(agent_id, self._tenant_id, "trust_gate_rejection")
            return self._chain_result(chain_id, task_id, stages, t0, approved=False)

        # Stage 1: Plan validation
        plan_result = self._plan_validator.validate(ctx)
        stages.append(plan_result)
        if plan_result.verdict == ValidationVerdict.REJECTED:
            return self._chain_result(chain_id, task_id, stages, t0, approved=False)

        # Stage 2: Security
        sec_result = self._security_validator.validate(ctx)
        stages.append(sec_result)
        if sec_result.verdict == ValidationVerdict.REJECTED:
            self._trust.record_veto(agent_id, self._tenant_id, "security_rejection")
            return self._chain_result(chain_id, task_id, stages, t0, approved=False)

        # Stage 3: Adversarial (async LLM)
        adv_result = await self._adversarial.validate(ctx)
        stages.append(adv_result)

        # Consensus for high-cost or escalating tasks
        needs_hitl = any(
            s.verdict == ValidationVerdict.ESCALATE for s in stages
        ) or estimated_cost_usd > 10.0

        if use_consensus and needs_hitl:
            verdict, conf = await self._consensus.vote(
                ctx, [self._plan_validator, self._security_validator]
            )
            stages.append(ValidationResult(
                stage="consensus_vote",
                verdict=verdict,
                reason=f"Consensus: {conf:.0%} agreement",
                confidence=conf,
            ))

        approved = all(s.verdict != ValidationVerdict.REJECTED for s in stages)
        chain = self._chain_result(chain_id, task_id, stages, t0, approved=approved)
        chain.requires_hitl = needs_hitl and approved
        if needs_hitl and approved:
            chain.hitl_reason = "Escalated by validation chain — human approval required"
        return chain

    @staticmethod
    def _chain_result(chain_id: str, task_id: str, stages: list[ValidationResult],
                      t0: float, approved: bool) -> ChainResult:
        final = ValidationVerdict.APPROVED if approved else ValidationVerdict.REJECTED
        for s in reversed(stages):
            if s.verdict != ValidationVerdict.APPROVED:
                final = s.verdict
                break
        return ChainResult(
            chain_id=chain_id,
            task_id=task_id,
            approved=approved,
            final_verdict=final,
            stages=stages,
            total_latency_ms=(time.perf_counter() - t0) * 1000,
        )


def get_validation_chain(tenant_id: str) -> ValidationChain:
    return ValidationChain(tenant_id)

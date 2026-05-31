import logging
from .decision_recorder import get as get_decision
from .causal_tracer import trace as causal_trace
from .memory_provenance import get_provenance
from .schema import ExplanationReport
from ..db import cognitive_conn

logger = logging.getLogger(__name__)
_cache: dict[str, dict] = {}


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS explanation_cache (
                decision_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                generated_at REAL NOT NULL
            )
        """)


_ensure_table()


def build(decision_id: str, tenant_id: str) -> ExplanationReport:
    if decision_id in _cache:
        cached = _cache[decision_id]
        return ExplanationReport(**cached)

    decision = get_decision(decision_id)
    if not decision:
        return ExplanationReport(decision_id=decision_id, tenant_id=tenant_id, summary="Decision not found.")

    provenance = get_provenance(decision_id)
    causal = causal_trace(decision_id, tenant_id)

    agent = decision.get("agent_id", "unknown")
    dtype = decision.get("decision_type", "action")
    conf = decision.get("confidence", 0)

    summary = (
        f"Agent '{agent}' made a '{dtype}' decision with {conf:.0%} confidence. "
        f"It was influenced by {len(provenance)} memory record(s) "
        f"and triggered {len(causal.chain)} downstream events."
    )

    try:
        from core.orchestrator import LLMClient
        import asyncio
        client = LLMClient()
        loop = asyncio.get_event_loop()
        if loop.is_running():
            pass  # skip LLM in sync context
        else:
            result = loop.run_until_complete(client.complete(
                prompt=f"Explain this AI decision in 2 sentences for a non-technical user:\n{decision.get('input_summary','')} → {decision.get('output_summary','')}",
                system="You are an AI explainability assistant. Be concise and factual.",
            ))
            if result:
                summary = result
    except Exception:
        pass

    report = ExplanationReport(
        decision_id=decision_id,
        tenant_id=tenant_id,
        summary=summary,
        memories_used=[p["memory_id"] for p in provenance],
        causal_events=len(causal.chain),
    )
    _cache[decision_id] = {
        "decision_id": decision_id,
        "tenant_id": tenant_id,
        "summary": summary,
        "memories_used": report.memories_used,
        "causal_events": report.causal_events,
        "generated_at": report.generated_at,
    }
    return report

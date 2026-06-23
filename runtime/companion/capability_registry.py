"""In-process registry of capabilities the companion can route to.

Holds typed ``Capability`` descriptors only — no subsystem calls live here.
The execution broker (later phase) is responsible for actually invoking a
subsystem once routing + the safety gate have cleared a capability.
"""
from __future__ import annotations

import threading
from typing import Any

from companion.schemas import (
    Capability,
    L0,
    L1,
    L3,
)


class CapabilityRegistry:
    """Thread-safe registry of ``Capability`` descriptors."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._caps: dict[str, Capability] = {}

    def register(self, cap: Capability) -> None:
        with self._lock:
            self._caps[cap.id] = cap

    def get(self, cap_id: str) -> Capability | None:
        with self._lock:
            return self._caps.get(cap_id)

    def all(self) -> list[Capability]:
        with self._lock:
            return list(self._caps.values())

    def by_subsystem(self, name: str) -> list[Capability]:
        with self._lock:
            return [c for c in self._caps.values() if c.subsystem == name]

    def find_for_intent(self, intent: str, task_type: str | None = None) -> list[Capability]:
        """Keyword/subsystem match for an intent — no LLM (yet).

        Scores each capability by overlap between the intent tokens and the
        capability's id/name/description/subsystem, with a bonus when
        ``task_type`` matches the subsystem. Returns matches best-first.
        """
        tokens = {t for t in _tokenize(intent) if t}
        if not tokens:
            return []
        task = (task_type or "").strip().lower()

        scored: list[tuple[int, Capability]] = []
        with self._lock:
            caps = list(self._caps.values())

        for cap in caps:
            hay = _tokenize(
                f"{cap.id} {cap.name} {cap.description} {cap.subsystem}"
            )
            score = len(tokens & hay)
            if task and (task == cap.subsystem or task in cap.id):
                score += 2
            if score > 0:
                scored.append((score, cap))

        scored.sort(key=lambda sc: sc[0], reverse=True)
        return [cap for _score, cap in scored]

    def to_dicts(self) -> list[dict[str, Any]]:
        """Serialize for the ``/api/companion/capabilities`` endpoint."""
        with self._lock:
            return [c.to_dict() for c in self._caps.values()]


def _tokenize(text: str) -> set[str]:
    out: set[str] = set()
    for raw in (text or "").lower().replace(".", " ").replace("_", " ").split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if tok:
            out.add(tok)
    return out


# ── Seed descriptors (read-only / low-risk first) ────────────────────────────
# Descriptors only — wiring to real subsystems is the execution broker's job.

def _seed(reg: CapabilityRegistry) -> None:
    caps = [
        Capability(
            id="system.health.read",
            subsystem="system",
            name="Read system health",
            description="Current health, uptime and active-agent counts from the metrics collector.",
            input_schema={},
            output_schema={"uptime_ms": "int", "agents_active": "int", "status": "str"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["how is the system doing", "are all agents up"],
        ),
        Capability(
            id="system.tasks.active",
            subsystem="system",
            name="List active tasks",
            description="Currently running and queued tasks from the task orchestrator.",
            input_schema={"status": "str?"},
            output_schema={"tasks": "list"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["what's running right now", "show active tasks"],
        ),
        Capability(
            id="system.logs.search",
            subsystem="system",
            name="Search logs",
            description="Search the backend log for a query string (read-only).",
            input_schema={"query": "str", "limit": "int?"},
            output_schema={"lines": "list"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["find errors in the logs", "search logs for timeout"],
        ),
        Capability(
            id="briefing.morning",
            subsystem="system",
            name="Morning briefing",
            description=("Read-only conversational morning/daily executive briefing "
                         "from local system, task, CRM, revenue, approval, and activity state."),
            input_schema={"date": "str?"},
            output_schema={
                "headline": "str",
                "summary": "str",
                "metrics": "dict",
                "focus": "list",
                "risks": "list",
                "sources": "list",
            },
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["give me my morning brief", "daily briefing", "what should I focus on today"],
        ),
        Capability(
            id="teammate.routine.status",
            subsystem="teammate",
            name="Read teammate routines",
            description="Read local teammate preferences and routine configuration.",
            input_schema={},
            output_schema={"routines": "dict", "preferences": "dict"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["morning brief settings", "what is my briefing routine"],
        ),
        Capability(
            id="teammate.routine.configure",
            subsystem="teammate",
            name="Configure teammate routine",
            description="Persist a local teammate routine preference such as morning briefing time.",
            input_schema={"routine": "str", "enabled": "bool", "time": "str?", "channel": "str?"},
            output_schema={"routine": "dict", "stored": "bool"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["writes teammate preferences to local state"],
            examples=["brief me every morning at 8", "turn off morning brief"],
        ),
        Capability(
            id="teammate.briefing.create_task",
            subsystem="teammate",
            name="Create task from briefing",
            description="Turn a recent briefing focus item into a local task draft.",
            input_schema={"focus_index": "int?", "title": "str?"},
            output_schema={"task": "dict", "stored": "bool"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["writes local task draft to tasks.json"],
            examples=["turn that into a task", "make the first item a task"],
        ),
        Capability(
            id="memory.search",
            subsystem="memory",
            name="Search memory",
            description="Semantic/keyword search across the memory and knowledge store.",
            input_schema={"query": "str", "top_k": "int?"},
            output_schema={"results": "list"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["what do we know about X", "recall the pricing decision"],
        ),
        Capability(
            id="memory.write_structured",
            subsystem="memory",
            name="Write structured memory",
            description="Persist a structured fact/note into the memory store.",
            input_schema={"key": "str", "value": "any", "tags": "list?"},
            output_schema={"stored": "bool", "id": "str"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["writes to memory store"],
            examples=["remember that the launch is on Friday"],
        ),
        Capability(
            id="research.deep.start",
            subsystem="research",
            name="Start deep research",
            description="Kick off an adaptive-depth autonomous research session for a topic.",
            input_schema={"topic": "str", "max_hops": "int?"},
            output_schema={"session_id": "str"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["network fetches", "writes findings to knowledge store"],
            examples=["research the competitor landscape for X"],
        ),
        Capability(
            id="money.analyze_idea",
            subsystem="money",
            name="Analyze monetization idea",
            description="Score and break down a monetization idea (no execution).",
            input_schema={"idea": "str"},
            output_schema={"score": "float", "breakdown": "dict"},
            risk_level=L1,
            requires_approval=False,
            side_effects=[],
            examples=["is selling lead lists worth it"],
        ),
        Capability(
            id="forge.search_code",
            subsystem="forge",
            name="Search code",
            description="Search the codebase for symbols, files or strings (read-only).",
            input_schema={"query": "str", "path": "str?"},
            output_schema={"matches": "list"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["where is the auth middleware", "find usages of require_approval"],
        ),
        Capability(
            id="forge.plan_change",
            subsystem="forge",
            name="Plan a code change",
            description="Produce a structured change plan (diff sketch) without writing files.",
            input_schema={"goal": "str", "scope": "list?"},
            output_schema={"plan": "dict"},
            risk_level=L1,
            requires_approval=False,
            side_effects=[],
            examples=["plan adding rate limiting to the orders route"],
        ),
        Capability(
            id="forge.run_tests",
            subsystem="forge",
            name="Run tests",
            description="Execute the test suite (or a subset) and report results.",
            input_schema={"selector": "str?"},
            output_schema={"passed": "int", "failed": "int", "report": "str"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["spawns test processes"],
            examples=["run the companion tests"],
        ),
        Capability(
            id="forge.apply_patch",
            subsystem="forge",
            name="Apply code patch",
            description="Write a code patch to the working tree. Mutates source files.",
            input_schema={"patch": "str", "files": "list"},
            output_schema={"applied": "bool", "files": "list"},
            risk_level=L3,
            requires_approval=True,
            side_effects=["modifies source files on disk"],
            examples=["apply the rate-limit patch"],
        ),
        Capability(
            id="browser.open",
            subsystem="browser",
            name="Open browser session",
            description="Open a URL in a fresh ephemeral headless-browser session (URL-guarded, read-only fetch).",
            input_schema={"url": "str", "profile": "str?"},
            output_schema={"session_id": "str", "title": "str", "url": "str"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["open example.com in the browser", "load this page"],
        ),
        Capability(
            id="browser.snapshot",
            subsystem="browser",
            name="Snapshot page",
            description="Accessibility-style snapshot of an open page with stable @eN element refs (read-only).",
            input_schema={"session_id": "str"},
            output_schema={"tree": "dict", "refs": "list", "ref_count": "int", "truncated": "bool"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["what's on this page", "snapshot the open browser tab"],
        ),
        Capability(
            id="browser.extract",
            subsystem="browser",
            name="Extract page content",
            description="Extract text/html/value/title/url/attr from an open page, bounded to 20KB (read-only).",
            input_schema={"session_id": "str", "kind": "str", "target": "str?"},
            output_schema={"data": "str", "truncated": "bool"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["get the text of this page", "extract the page title"],
        ),
        Capability(
            id="browser.capture",
            subsystem="browser",
            name="Capture page",
            description="Screenshot (PNG) or PDF of an open page into the rotated captures directory (read-only).",
            input_schema={"session_id": "str", "kind": "str?"},
            output_schema={"path": "str"},
            risk_level=L0,
            requires_approval=False,
            side_effects=["writes a capture file under ~/.ai-employee/state"],
            examples=["screenshot the page", "save this page as pdf"],
        ),
        Capability(
            id="browser.close",
            subsystem="browser",
            name="Close browser session",
            description="Close one browser session (or all sessions when none is named).",
            input_schema={"session_id": "str?"},
            output_schema={"closed": "bool"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["close the browser", "close that tab"],
        ),
        Capability(
            id="browser.act",
            subsystem="browser",
            name="Act on page",
            description="Click/fill/type/press/scroll/select on a live page. Mutates external site state.",
            input_schema={"session_id": "str", "action": "str", "target": "str?", "value": "any?"},
            output_schema={"ok": "bool", "side_effect_class": "str"},
            risk_level=L3,
            requires_approval=True,
            side_effects=["interacts with external website"],
            examples=["click the submit button", "fill in the search box"],
        ),
        Capability(
            id="context.retrieve",
            subsystem="context",
            name="Retrieve context",
            description="Tiered (L0/L1) hybrid retrieval over the context database with a visible trace (read-only).",
            input_schema={"query": "str", "project_id": "str?", "filters": "dict?", "top_k": "int?"},
            output_schema={"nodes": "list", "trace": "list"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["what context do we have on pricing", "find the launch decision"],
        ),
        Capability(
            id="context.write",
            subsystem="context",
            name="Write context node",
            description="Persist a node into the filesystem-style context tree (path-validated, tenant-scoped).",
            input_schema={"path": "str", "content": "str", "metadata": "dict?"},
            output_schema={"node_id": "str", "path": "str"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["writes a node under the context_db state directory"],
            examples=["save this decision to project context"],
        ),
        Capability(
            id="context.compress_session",
            subsystem="context",
            name="Compress session to context",
            description="Extract durable decisions/preferences/facts from a conversation into the context tree.",
            input_schema={"messages": "list", "project_id": "str?"},
            output_schema={"written_nodes": "list"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["writes nodes under the context_db state directory"],
            examples=["remember the important parts of this conversation"],
        ),
        Capability(
            id="security.score_action",
            subsystem="security",
            name="Score action risk",
            description="Return an anomaly/risk score for a proposed action (read-only).",
            input_schema={"action": "str", "payload": "dict?"},
            output_schema={"risk_score": "float", "factors": "list"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["how risky is deleting the deals file"],
        ),
        Capability(
            id="forge.lifecycle_plan",
            subsystem="forge",
            name="Spec-driven lifecycle plan",
            description="Run the spec->plan->review->ship-gate lifecycle for a build goal (planning only; no file edits, no apply).",
            input_schema={"goal": "str", "context": "dict?"},
            output_schema={"spec": "dict", "plan": "dict", "ship": "dict", "status": "str"},
            risk_level=L1,
            requires_approval=False,
            side_effects=[],
            examples=["plan how to build the orders export feature", "spec out the new login flow"],
        ),
        Capability(
            id="research.audit_quality",
            subsystem="research",
            name="Audit research quality",
            description="Run citation anchoring, fabricated-reference detection and the integrity gate over a research report (read-only).",
            input_schema={"report": "dict"},
            output_schema={"quality": "dict", "publishable": "bool"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["check this research report for fabricated sources", "is this report publishable"],
        ),
        Capability(
            id="skills.run",
            subsystem="skills",
            name="Run a production skill",
            description=("Run a production skill from the shared skill library. Handles business, "
                         "marketing, content, writing, sales, research, analytics, finance, operations, "
                         "coding, codebase reading, architecture mapping, debugging, error trace analysis, "
                         "refactor planning, security review, test generation, UI/UX audit, API inspection, "
                         "database schema analysis, agent task planning, local file planning, browser research, "
                         "source credibility checks, documentation, prompt/context engineering, memory linking, "
                         "model routing evaluation, LLM output judging, failure forensics, regression detection, "
                         "sandbox test planning, command safety classification, HITL approval planning, remote "
                         "compute planning, resource optimization, startup diagnostics, frontend/backend/Python "
                         "health checks, Ollama checks, skill registry validation, dashboard skill sync checks, "
                         "end-to-end task execution planning, growth strategy, SEO, paid ads planning, "
                         "conversion funnel analysis, reporting, finance review, invoice/payment planning, "
                         "budget guardrails, hiring and people ops, project communications, message routing, "
                         "web monitoring, threat-intelligence briefing, tool policy review, token budgeting, "
                         "API and commerce integration checks, data extraction/export validation, batch and "
                         "cron planning, backup/archive readiness, release rollout and rollback review, "
                         "diagnostic reporting, anomaly alert planning, provider fallback, session persistence, "
                         "vault retrieval quality, trigger auditing, multi-agent orchestration review, customer "
                         "support workflows, FAQ and ticket handling, refund review, lead generation and "
                         "enrichment, cold outreach safety, email deliverability and campaign approval, content "
                         "and copy review, design quality checks, market monitoring, trading/portfolio review, "
                         "web search planning, web fetch safety, fact-checking workflows, action item tracking, "
                         "meeting note structuring, project timelines, task scheduling, goal health, workflow "
                         "audits, company operating systems, org hierarchy, workload balance, ecommerce research, "
                         "supplier sync review, inventory alerts, order routing, shipment updates, pricing rules, "
                         "stock monitoring, product ranking, customer segmentation, agent memory health, skill "
                         "generation planning, AI/ML implementation review, chat dispatch, chatbot flows, context "
                         "injection safety, shell command review, prompt-injection scans, memory writeback review, "
                         "task routing policy, defensive OSINT, source synthesis, legal/contract review, investor "
                         "updates, valuation, tax/payment validation, invoices, PnL, profit alerts, email A/B "
                         "tests, accessibility audits, brand positioning, campaign planning, candidate outreach, "
                         "comment automation safety, component specs, content curation, conversion tracking, "
                         "email deliverability, DNS verification, follow-up sequencing, image prompt review, "
                         "keyword search planning, improvement proposal prioritization, lesson and script "
                         "writing, list segmentation, market entry and positioning, messaging frameworks, "
                         "meta/PPC ad strategy review, risk mitigation planning, notification and WhatsApp "
                         "dispatch review, order aggregation, outreach sequencing, performance diagnosis and "
                         "prediction, buyer personas, PLG and viral strategy, prediction/price market briefs, "
                         "profit margin and prospect research, report generation review, RSS and trend scans, "
                         "schema markup and SEO/website audits, self-improvement and swarm simulation review, "
                         "smart contract and trading-bot code review, brand storytelling, strategic analysis, "
                         "subscriber management, thought leadership, TikTok scripting, touchpoint mapping, "
                         "typography/UX/visual-identity review, and email warmup planning."),
            input_schema={"goal": "str", "skill_id": "str?", "context": "str?"},
            output_schema={"skill_id": "str", "skill_name": "str", "output": "str", "match_score": "float"},
            risk_level=L1,
            requires_approval=False,
            side_effects=[],
            examples=["map the repository architecture", "analyze this stack trace",
                      "generate tests for this route", "check if this command is safe",
                      "validate the skill registry", "review this invoice draft",
                      "audit seo opportunities", "write a stakeholder update",
                      "test this api integration contract", "review the rollback plan",
                      "review this cold email draft", "verify these claims",
                      "audit workflow management", "review auto reorder policy",
                      "review this shell command", "build a legal review checklist",
                      "check accessibility audit", "check email deliverability optimization",
                      "review this outreach sequence", "review trading bot code",
                      "build a strategic analysis brief", "check the website audit"],
        ),
        Capability(
            id="content.produce",
            subsystem="content",
            name="Produce multi-platform content (Content Factory)",
            description=("Generate real content for one or more platforms (blog/twitter/linkedin/"
                         "instagram/tiktok), save artifacts, and stage them in the approval-gated "
                         "publish queue. Supports batches/variants. Never auto-publishes."),
            input_schema={"topic": "str", "platforms": "list?", "content_type": "str?", "variants": "int?"},
            output_schema={"artifacts": "list", "queued": "list", "real_drafts": "int"},
            risk_level=L1,
            requires_approval=False,
            side_effects=["writes content artifacts; stages items in the publish queue (no posting)"],
            examples=["make a content batch about our launch for twitter and linkedin",
                      "produce 3 blog variants about ai pricing",
                      "create a content calendar piece for instagram"],
        ),
        Capability(
            id="finance.draft",
            subsystem="finance",
            name="Finance draft (advisory only)",
            description=("Draft a business model, pricing analysis, revenue forecast, or investor "
                         "pitch/memo. ADVISORY ONLY — estimates for human review, no transaction, "
                         "trade, payment, or final tax/legal advice."),
            input_schema={"request": "str", "context": "str?", "inputs": "dict?"},
            output_schema={"kind": "str", "draft": "str", "advisory": "bool", "requires_human_signoff": "bool"},
            risk_level=L1,
            requires_approval=False,
            side_effects=[],
            examples=["draft a business model for an ai note-taker",
                      "pricing analysis for our pro tier", "revenue forecast for next year",
                      "write an investor pitch memo"],
        ),
        Capability(
            id="company.validate",
            subsystem="company",
            name="Validate a business idea before building (CompanyOS)",
            description=("Score real market demand/competition/monetization/feasibility for a "
                         "business idea and return a verdict (build/pivot/need_evidence/reject). "
                         "Validate-before-build: refuses weak ideas instead of wasting time/money."),
            input_schema={"idea": "str", "answers": "dict?"},
            output_schema={"verdict": "str", "composite": "float", "recommendation": "str"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["validate the idea: an ai note-taker for lawyers",
                      "should we build a meal-prep app — validate demand first",
                      "is this business idea worth building"],
        ),
        Capability(
            id="company.refine",
            subsystem="company",
            name="Refine a weak idea into a buildable one (CompanyOS)",
            description=("Turn a weak business idea into a usable one: validates it, then proposes "
                         "concrete pivots targeting its weakest dimensions (demand/competition/"
                         "monetization/feasibility) plus an improved idea statement."),
            input_schema={"idea": "str"},
            output_schema={"suggestions": "list", "improved_idea": "str", "weak_dimensions": "list"},
            risk_level=L0,
            requires_approval=False,
            side_effects=[],
            examples=["this idea seems weak, how do we make it work",
                      "turn 'a social app for cats' into something buildable",
                      "improve my business idea"],
        ),
    ]
    for c in caps:
        reg.register(c)


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: CapabilityRegistry | None = None
_instance_lock = threading.Lock()


def get_capability_registry() -> CapabilityRegistry:
    """Return the process-wide seeded ``CapabilityRegistry`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            reg = CapabilityRegistry()
            _seed(reg)
            _instance = reg
    return _instance

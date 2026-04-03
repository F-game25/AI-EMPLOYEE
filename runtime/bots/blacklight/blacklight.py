"""BLACKLIGHT — Autonomous money-making agent layer.

Sits ABOVE Hermes (Ollama) and turns the system into an autonomous operator.

This layer does NOT replace Hermes — it orchestrates it.

Flow (repeating loop):
  goal → find opportunities → analyze (Hermes) → plan → execute skills
       → evaluate results → improve strategy → repeat

State file: ~/.ai-employee/state/blacklight.state.json
Log file:   ~/.ai-employee/state/blacklight.log.jsonl
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "blacklight.state.json"
LOG_FILE   = AI_HOME / "state" / "blacklight.log.jsonl"
CRM_FILE   = AI_HOME / "state" / "leads-crm.json"

# How long to wait between autonomous cycles (seconds)
LOOP_INTERVAL = int(os.environ.get("BLACKLIGHT_LOOP_INTERVAL", "30"))
# Maximum cycles to run (0 = unlimited)
MAX_CYCLES = int(os.environ.get("BLACKLIGHT_MAX_CYCLES", "0"))
# Maximum log entries to keep on disk
MAX_LOG_LINES = 500

# Opportunity analysis / evaluation tuning
MAX_OPPORTUNITIES_TO_ANALYZE = 5   # how many raw leads to score per cycle
MAX_PLANS_TO_EXECUTE = 3           # how many plans to run per cycle
POINTS_PER_LEAD = 2                # evaluation score weight: stored lead
POINTS_PER_MESSAGE = 3             # evaluation score weight: outreach message
MAX_EVALUATION_SCORE = 10          # evaluation score cap
SUCCESS_SCORE_THRESHOLD = 4        # minimum score to consider a cycle successful

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("blacklight")

# ── Dependency imports (graceful fallback) ────────────────────────────────────

_ai_router_path   = AI_HOME / "bots" / "ai-router"
_lead_intel_path  = AI_HOME / "bots" / "lead-intelligence"

for _p in [_ai_router_path, _lead_intel_path]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from ai_router import query_ai_for_agent, search_web  # type: ignore
    _ROUTER_AVAILABLE = True
except ImportError:
    _ROUTER_AVAILABLE = False

try:
    from lead_hunter_agent import scrape_leads, filter_leads  # type: ignore
    _LEAD_HUNTER_AVAILABLE = True
except ImportError:
    _LEAD_HUNTER_AVAILABLE = False

try:
    from outreach_agent import draft_message  # type: ignore
    _OUTREACH_AVAILABLE = True
except ImportError:
    _OUTREACH_AVAILABLE = False


# ── State & logging helpers ───────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "running": False,
        "goal": "",
        "cycle": 0,
        "opportunities_found": 0,
        "actions_taken": 0,
        "last_activity": None,
        "strategy": {},
    }


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _append_log(entry: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    # Trim to max lines
    try:
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > MAX_LOG_LINES:
            LOG_FILE.write_text("\n".join(lines[-MAX_LOG_LINES:]) + "\n")
    except Exception:
        pass


def _log(level: str, msg: str, data: dict | None = None) -> None:
    entry: dict = {"ts": _now_iso(), "level": level, "msg": msg}
    if data:
        entry["data"] = data
    _append_log(entry)
    logger.info("blacklight [%s]: %s", level, msg)


def _load_crm() -> list:
    if not CRM_FILE.exists():
        return []
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return []


def _save_crm(leads: list) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(leads, indent=2))


# ── Hermes / Ollama interface ─────────────────────────────────────────────────

def _ask_hermes(prompt: str, system: str = "") -> str:
    """Route a reasoning request through Ollama/Hermes via ai_router."""
    if not _ROUTER_AVAILABLE:
        return ""
    result = query_ai_for_agent("blacklight", prompt, system_prompt=system)
    return result.get("answer", "")


# ── Skills ────────────────────────────────────────────────────────────────────

def skill_hunt_leads(niche: str, location: str = "") -> dict:
    """Skill: find and qualify business leads."""
    if _LEAD_HUNTER_AVAILABLE:
        try:
            raw = scrape_leads(niche, location)
            qualified = filter_leads(raw)
            return {"skill": "hunt_leads", "found": len(raw),
                    "qualified": len(qualified), "leads": qualified}
        except Exception as exc:
            return {"skill": "hunt_leads", "found": 0, "qualified": 0,
                    "leads": [], "error": str(exc)}

    # Fallback: web search
    if _ROUTER_AVAILABLE:
        query = f"local businesses {niche} {location} needing help".strip()
        results = search_web(query, max_results=5)
        leads = [
            {
                "id": f"lead-{uuid.uuid4().hex[:8]}",
                "name": r.get("title", "Unknown"),
                "website": r.get("url", ""),
                "description": r.get("snippet", ""),
                "industry": niche,
                "location": location,
                "status": "new",
                "created_at": _now_iso(),
            }
            for r in results
        ]
        return {"skill": "hunt_leads", "found": len(leads),
                "qualified": len(leads), "leads": leads}

    return {"skill": "hunt_leads", "found": 0, "qualified": 0, "leads": []}


def skill_generate_outreach(lead: dict, offer: str) -> dict:
    """Skill: write a cold outreach message for a lead."""
    # Try the outreach_agent if available
    if _OUTREACH_AVAILABLE:
        try:
            msg = draft_message(lead, channel="email")
            return {"skill": "generate_outreach",
                    "lead": lead.get("name", ""), "message": msg}
        except Exception:
            pass  # fall through to Hermes

    # Use Hermes directly
    prompt = (
        f"Write a short personalized cold outreach email for a business called "
        f"'{lead.get('name', 'this company')}' in the "
        f"{lead.get('industry', 'local')} space.\n"
        f"My offer: {offer}.\n"
        f"Keep it under 80 words. Direct, friendly, no fluff."
    )
    msg = _ask_hermes(
        prompt,
        system="You are a digital sales expert. Write concise, high-converting cold outreach.",
    )
    return {"skill": "generate_outreach",
            "lead": lead.get("name", ""), "message": msg}


def skill_store_lead(lead: dict) -> dict:
    """Skill: persist a lead into the shared CRM."""
    crm = _load_crm()
    existing_ids = {l.get("id") for l in crm}
    if lead.get("id") not in existing_ids:
        crm.append(lead)
        _save_crm(crm)
        return {"skill": "store_lead", "stored": True, "lead": lead.get("name", "")}
    return {"skill": "store_lead", "stored": False,
            "lead": lead.get("name", ""), "reason": "duplicate"}


# ── Opportunity Engine ────────────────────────────────────────────────────────

def find_opportunities(goal: str, strategy: dict) -> list[dict]:
    """Scan for leads/opportunities aligned with the current goal and strategy."""
    _log("info", f"Scanning for opportunities — {goal}")

    niche    = strategy.get("niche", "")
    location = strategy.get("location", "")

    if not niche and _ROUTER_AVAILABLE:
        prompt = (
            f"Extract the business niche or service type from this goal: '{goal}'\n"
            f"Reply with 2–5 words only."
        )
        niche = _ask_hermes(prompt).strip() or goal

    result = skill_hunt_leads(niche, location)
    opps   = result.get("leads", [])
    _log("info", f"Found {len(opps)} raw opportunities",
         {"niche": niche, "location": location})
    return opps


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyze_opportunity(opp: dict, goal: str) -> dict:
    """Ask Hermes whether this opportunity is valuable."""
    if not _ROUTER_AVAILABLE:
        return {"score": 5, "valuable": True, "reason": "no AI", "action": "outreach"}

    prompt = (
        f"Goal: '{goal}'\n\n"
        f"Business: {opp.get('name', 'Unknown')}\n"
        f"Industry: {opp.get('industry', 'Unknown')}\n"
        f"Description: {opp.get('description', '')[:200]}\n\n"
        f"Rate this opportunity 1–10 for money-making potential.\n"
        f"Reply with exactly:\n"
        f"Score: <number>\nReason: <one sentence>\nAction: <best next action>"
    )
    answer = _ask_hermes(
        prompt,
        system="You are a business development analyst. Be decisive and concise.",
    )

    score = 5
    reason = ""
    action = "outreach"
    for line in answer.splitlines():
        ll = line.lower()
        if ll.startswith("score:"):
            try:
                score = int(line.split(":", 1)[1].strip().split()[0])
            except Exception:
                pass
        elif ll.startswith("reason:"):
            reason = line.split(":", 1)[1].strip()
        elif ll.startswith("action:"):
            action = line.split(":", 1)[1].strip()

    return {"score": score, "valuable": score >= 6,
            "reason": reason, "action": action}


def prioritize_opportunities(opps: list[dict], goal: str) -> list[dict]:
    """Analyze top candidates and return sorted by score."""
    scored = []
    for opp in opps[:MAX_OPPORTUNITIES_TO_ANALYZE]:
        analysis = analyze_opportunity(opp, goal)
        opp["bl_score"]  = analysis["score"]
        opp["bl_action"] = analysis.get("action", "outreach")
        opp["bl_reason"] = analysis.get("reason", "")
        if analysis["valuable"]:
            scored.append(opp)
    scored.sort(key=lambda x: x.get("bl_score", 0), reverse=True)
    return scored


# ── Planning ──────────────────────────────────────────────────────────────────

def plan_actions(opps: list[dict], goal: str, strategy: dict) -> list[dict]:
    """Generate short, executable action plans for each opportunity."""
    offer = strategy.get(
        "offer",
        "a professional AI-powered service that helps your business grow faster",
    )
    plans = []
    for opp in opps[:MAX_PLANS_TO_EXECUTE]:
        plans.append({
            "id":    f"plan-{uuid.uuid4().hex[:6]}",
            "lead":  opp,
            "offer": offer,
            "action": opp.get("bl_action", "outreach"),
        })
    return plans


# ── Execution ─────────────────────────────────────────────────────────────────

def execute_plan(plan: dict) -> dict:
    """Run a single plan: store lead + generate outreach."""
    lead  = plan["lead"]
    offer = plan.get("offer", "")

    store_result    = skill_store_lead(lead)
    outreach_result = skill_generate_outreach(lead, offer)

    _log("action", f"Executed plan for {lead.get('name', 'Unknown')}", {
        "stored":  store_result.get("stored"),
        "preview": (outreach_result.get("message") or "")[:80],
    })

    return {
        "plan_id":          plan["id"],
        "lead":             lead.get("name", "Unknown"),
        "steps_completed":  2,
        "stored":           store_result.get("stored", False),
        "outreach_message": outreach_result.get("message", ""),
    }


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_results(executions: list[dict], cycle: int) -> dict:
    """Did this cycle generate value? Move toward money?"""
    if not executions:
        return {"success": False, "score": 0,
                "reason": "No actions executed", "leads_stored": 0,
                "messages_generated": 0}

    leads_stored        = sum(1 for e in executions if e.get("stored"))
    messages_generated  = sum(1 for e in executions if e.get("outreach_message"))

    # Score: POINTS_PER_LEAD pts per lead stored, POINTS_PER_MESSAGE pts per message generated
    score   = min(MAX_EVALUATION_SCORE,
                  leads_stored * POINTS_PER_LEAD + messages_generated * POINTS_PER_MESSAGE)
    success = score >= SUCCESS_SCORE_THRESHOLD
    reason  = (
        f"Cycle {cycle}: {leads_stored} lead(s) stored, "
        f"{messages_generated} outreach message(s) generated"
    )
    _log("eval", reason, {"score": score, "success": success})
    return {
        "success":            success,
        "score":              score,
        "reason":             reason,
        "leads_stored":       leads_stored,
        "messages_generated": messages_generated,
    }


# ── Improvement ───────────────────────────────────────────────────────────────

def improve_strategy(strategy: dict, eval_result: dict, goal: str) -> dict:
    """If results were weak, ask Hermes for one concrete adjustment."""
    if eval_result.get("success"):
        return strategy  # already working — keep it

    if not _ROUTER_AVAILABLE:
        return strategy

    prompt = (
        f"Goal: {goal}\n"
        f"Current strategy: {json.dumps(strategy)}\n"
        f"Last cycle result: {eval_result.get('reason', 'weak')}\n\n"
        f"Suggest ONE small adjustment to improve results.\n"
        f"Reply with:\n"
        f"Niche: <adjusted niche>\n"
        f"Location: <city or blank>\n"
        f"Offer: <adjusted offer>"
    )
    answer = _ask_hermes(
        prompt,
        system=(
            "You are a growth strategist. Give one concrete adjustment. "
            "Be specific. No preamble."
        ),
    )

    new_strategy = dict(strategy)
    for line in answer.splitlines():
        ll = line.lower()
        if ll.startswith("niche:"):
            new_strategy["niche"] = line.split(":", 1)[1].strip()
        elif ll.startswith("location:"):
            loc = line.split(":", 1)[1].strip()
            if loc and loc.lower() not in ("blank", "none", "any", ""):
                new_strategy["location"] = loc
        elif ll.startswith("offer:"):
            new_strategy["offer"] = line.split(":", 1)[1].strip()

    _log("improve", "Strategy adjusted", new_strategy)
    return new_strategy


# ── Main autonomous loop ──────────────────────────────────────────────────────

_run_thread: threading.Thread | None = None
_stop_event = threading.Event()


def is_running() -> bool:
    return _run_thread is not None and _run_thread.is_alive()


def start(goal: str) -> bool:
    """Launch BLACKLIGHT in a background daemon thread."""
    global _run_thread
    if is_running():
        return False  # already running

    _stop_event.clear()
    _run_thread = threading.Thread(
        target=_run_loop, args=(goal,), daemon=True, name="blacklight"
    )
    _run_thread.start()

    state = _load_state()
    state.update({
        "running":             True,
        "goal":                goal,
        "cycle":               0,
        "opportunities_found": 0,
        "actions_taken":       0,
        "started_at":          _now_iso(),
        "strategy":            {},
    })
    _save_state(state)
    _log("system", f"BLACKLIGHT started — goal: {goal}")
    return True


def stop() -> bool:
    """Signal the loop to stop after the current cycle."""
    global _run_thread
    if not is_running():
        return False

    _stop_event.set()
    state = _load_state()
    state["running"]    = False
    state["stopped_at"] = _now_iso()
    _save_state(state)
    _log("system", "BLACKLIGHT stopped by user")
    return True


def _run_loop(goal: str) -> None:
    """
    Core autonomous loop:
      goal → opportunities → analyze → plan → execute → evaluate → improve → repeat
    """
    strategy: dict = {}
    cycle = 0

    while not _stop_event.is_set():
        cycle += 1

        # Persist cycle progress
        state = _load_state()
        state["cycle"]         = cycle
        state["last_activity"] = _now_iso()
        state["running"]       = True
        _save_state(state)

        _log("cycle", f"=== Cycle {cycle} start ===", {"goal": goal})

        try:
            # 1. Find opportunities
            opps = find_opportunities(goal, strategy)
            state = _load_state()
            state["opportunities_found"] = (
                state.get("opportunities_found", 0) + len(opps)
            )
            _save_state(state)

            if not opps:
                _log("warn", "No opportunities found — will retry next cycle")
                _stop_event.wait(LOOP_INTERVAL)
                continue

            # 2. Analyze & prioritize
            prioritized = prioritize_opportunities(opps, goal)
            if not prioritized:
                _log("warn", "No valuable opportunities — adjusting strategy")
                strategy = improve_strategy(
                    strategy,
                    {"success": False, "reason": "No valuable opportunities"},
                    goal,
                )
                _stop_event.wait(LOOP_INTERVAL)
                continue

            # 3. Plan
            plans = plan_actions(prioritized, goal, strategy)

            # 4. Execute
            executions: list[dict] = []
            for plan in plans:
                if _stop_event.is_set():
                    break
                result = execute_plan(plan)
                executions.append(result)

            state = _load_state()
            state["actions_taken"] = state.get("actions_taken", 0) + sum(
                e.get("steps_completed", 0) for e in executions
            )
            _save_state(state)

            # 5. Evaluate
            eval_result = evaluate_results(executions, cycle)
            _log("result", f"Cycle {cycle} complete", eval_result)

            # 6. Improve
            strategy = improve_strategy(strategy, eval_result, goal)

        except Exception as exc:
            _log("error", f"Cycle {cycle} error: {exc}")
            logger.exception("blacklight: unhandled error in cycle %d", cycle)

        # Max cycles guard
        if MAX_CYCLES > 0 and cycle >= MAX_CYCLES:
            _log("system", f"Max cycles ({MAX_CYCLES}) reached — stopping")
            break

        # Wait between cycles (interruptible)
        _stop_event.wait(LOOP_INTERVAL)

    # Cleanup
    state = _load_state()
    state["running"]       = False
    state["last_activity"] = _now_iso()
    _save_state(state)
    _log("system", f"BLACKLIGHT loop ended after {cycle} cycle(s)")


# ── Public API (used by server.py) ────────────────────────────────────────────

def get_status() -> dict:
    """Return current BLACKLIGHT state (thread-safe snapshot)."""
    state = _load_state()
    state["running"] = is_running()
    return state


def get_logs(limit: int = 100) -> list:
    """Return the most recent *limit* log entries."""
    if not LOG_FILE.exists():
        return []
    try:
        lines = LOG_FILE.read_text().splitlines()
        entries = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        return entries
    except Exception:
        return []


# ── Standalone entry point ────────────────────────────────────────────────────

def main() -> None:
    """Run BLACKLIGHT as a standalone long-running process."""
    goal = os.environ.get(
        "BLACKLIGHT_GOAL",
        "Find local businesses that can benefit from AI services and generate leads",
    )
    logger.info("blacklight: standalone mode — goal: %s", goal)
    start(goal)
    try:
        while is_running():
            time.sleep(5)
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()

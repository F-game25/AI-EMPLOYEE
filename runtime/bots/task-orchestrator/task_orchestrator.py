"""Task Orchestrator — Multi-Agent Brain for AI Employee Company.

The orchestrator accepts any natural-language task and autonomously:
  1. Decomposes the task into subtasks using AI
  2. Selects which of the 20 agents and skills are needed
  3. Decides parallel vs sequential execution strategy
  4. Dispatches subtasks into each agent's queue file
  5. Runs up to 10+ subtasks concurrently via a thread-pool
  6. Validates results with peer-review between agents
  7. Monitors progress and aggregates final results
  8. Writes the combined result back to the chatlog

Commands (via chatlog / WhatsApp / Dashboard):
  task <description>               — submit a task for orchestration
  task status                      — current plan progress
  task list                        — recent task plans
  task cancel                      — cancel current active plan
  orchestrate <description>        — alias for task
  assign <agent> <subtask>         — manually dispatch to a specific agent

State files:
  ~/.ai-employee/state/task-orchestrator.state.json   — current orchestrator state
  ~/.ai-employee/config/task_plans.json               — active & recent task plans
  ~/.ai-employee/config/agent_capabilities.json       — 20-agent capabilities map
  ~/.ai-employee/state/agent_tasks/<agent>.queue.jsonl — per-agent task queues
"""
import concurrent.futures
import json
import logging
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "task-orchestrator.state.json"
TASK_PLANS_FILE = AI_HOME / "config" / "task_plans.json"
AGENT_CAPS_FILE = AI_HOME / "config" / "agent_capabilities.json"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("TASK_ORCHESTRATOR_POLL_INTERVAL", "5"))
MAX_PARALLEL = int(os.environ.get("TASK_ORCHESTRATOR_MAX_PARALLEL", "10"))
PLAN_TIMEOUT_SECS = int(os.environ.get("TASK_ORCHESTRATOR_TIMEOUT", "600"))
MAX_PLANS_HISTORY = int(os.environ.get("TASK_ORCHESTRATOR_MAX_HISTORY", "20"))
# Enable peer-review validation between agents (default: on)
PEER_REVIEW_ENABLED = os.environ.get("TASK_ORCHESTRATOR_PEER_REVIEW", "true").lower() == "true"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(message)s",
)
logger = logging.getLogger("task-orchestrator")

# ── AI router ────────────────────────────────────────────────────────────────

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai as _query_ai, query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False
    def _query_ai_for_agent(*args, **kwargs):  # type: ignore
        return {"answer": "", "provider": "error", "model": "", "error": "ai_router not available"}

# ── Feedback loop (optional) ─────────────────────────────────────────────────

_feedback_path = AI_HOME / "bots" / "feedback-loop"
if str(_feedback_path) not in sys.path:
    sys.path.insert(0, str(_feedback_path))

try:
    from feedback_loop import record_outcome as _record_outcome  # type: ignore
    _FEEDBACK_AVAILABLE = True
except ImportError:
    _FEEDBACK_AVAILABLE = False
    def _record_outcome(*args, **kwargs):  # type: ignore
        pass


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    entries = []
    try:
        for line in CHATLOG.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except Exception:
        pass
    return entries


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Agent Capabilities ────────────────────────────────────────────────────────

def load_agent_capabilities() -> dict:
    if not AGENT_CAPS_FILE.exists():
        return {}
    try:
        return json.loads(AGENT_CAPS_FILE.read_text())
    except Exception:
        return {}


# ── Task Plans ────────────────────────────────────────────────────────────────

def load_task_plans() -> list:
    if not TASK_PLANS_FILE.exists():
        return []
    try:
        return json.loads(TASK_PLANS_FILE.read_text())
    except Exception:
        return []


def save_task_plans(plans: list) -> None:
    TASK_PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_PLANS_FILE.write_text(json.dumps(plans, indent=2))


def get_active_plan(plans: list) -> dict | None:
    for p in plans:
        if p.get("status") in ("planning", "running"):
            return p
    return None


def update_plan(plans: list, plan_id: str, updates: dict) -> None:
    for p in plans:
        if p["id"] == plan_id:
            p.update(updates)
            return


# ── Per-Agent Task Queues ─────────────────────────────────────────────────────

def dispatch_to_agent(agent_id: str, subtask: dict) -> None:
    """Write a subtask to the agent's queue file."""
    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    queue_file = AGENT_TASKS_DIR / f"{agent_id}.queue.jsonl"
    with open(queue_file, "a") as f:
        f.write(json.dumps(subtask) + "\n")


def check_agent_result(agent_id: str, subtask_id: str) -> dict | None:
    """Check if an agent has written a result for the given subtask."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{subtask_id}.json"
    if result_file.exists():
        try:
            return json.loads(result_file.read_text())
        except Exception:
            return None
    # Also check the agent state file for recent results
    state_file = AI_HOME / "state" / f"{agent_id}.state.json"
    if state_file.exists():
        try:
            st = json.loads(state_file.read_text())
            recent = st.get("recent_results", [])
            for r in recent:
                if r.get("subtask_id") == subtask_id:
                    return r
        except Exception:
            pass
    return None


# ── Task Decomposition (AI-powered) ──────────────────────────────────────────

def decompose_task(task_description: str, capabilities: dict) -> list:
    """Use AI to decompose a task into agent-assigned subtasks."""
    agent_summaries = []
    for agent_id, info in capabilities.get("agents", {}).items():
        agent_summaries.append(
            f"- {agent_id}: {info.get('description', '')} "
            f"(skills: {', '.join(info.get('skills', [])[:5])})"
        )
    agents_text = "\n".join(agent_summaries)

    system_prompt = (
        "You are the Task Orchestrator for an AI employee company. "
        "Your job is to decompose a user's goal into concrete subtasks and assign each subtask "
        "to the most appropriate specialist agent. "
        "Always respond with valid JSON only — no markdown, no explanation outside JSON. "
        "Return a JSON array of subtask objects, each with: "
        '{"subtask_id": "unique-id", "agent_id": "agent-name", '
        '"title": "short title", "instructions": "detailed instructions", '
        '"depends_on": [], "parallel": true/false} '
        "Use depends_on to express sequential dependencies (list subtask_ids that must finish first). "
        "Set parallel=true for subtasks that can run simultaneously. "
        "Use only these agent IDs: "
        + ", ".join(capabilities.get("agents", {}).keys())
    )

    user_prompt = (
        f"Task: {task_description}\n\n"
        f"Available agents:\n{agents_text}\n\n"
        "Decompose this into 2-8 subtasks. Assign each to the best agent. "
        "Return JSON array only."
    )

    subtasks = []
    if _AI_AVAILABLE:
        try:
            result = _query_ai(user_prompt, system_prompt=system_prompt)
            raw = result.get("answer", "")
            # Extract JSON array from response
            match = re.search(r"\[[\s\S]*\]", raw)
            if match:
                parsed = json.loads(match.group(0))
                for st in parsed:
                    if isinstance(st, dict) and "agent_id" in st:
                        st.setdefault("subtask_id", str(uuid.uuid4())[:8])
                        st.setdefault("depends_on", [])
                        st.setdefault("parallel", True)
                        st.setdefault("status", "pending")
                        st.setdefault("result", None)
                        subtasks.append(st)
        except Exception as exc:
            logger.warning("task-orchestrator: AI decomposition failed — %s", exc)

    if not subtasks:
        # Fallback: create a single-agent subtask for orchestrator
        subtasks = [{
            "subtask_id": str(uuid.uuid4())[:8],
            "agent_id": "orchestrator",
            "title": "Complete task",
            "instructions": task_description,
            "depends_on": [],
            "parallel": False,
            "status": "pending",
            "result": None,
        }]

    return subtasks


def select_skills_for_agent(agent_id: str, subtask_instructions: str, capabilities: dict) -> list:
    """Suggest which skills from the agent's repertoire fit this subtask."""
    agent_info = capabilities.get("agents", {}).get(agent_id, {})
    agent_skills = agent_info.get("skills", [])
    if not agent_skills or not _AI_AVAILABLE:
        return agent_skills[:3]

    system_prompt = (
        "You select the most relevant skills for a subtask from an agent's skill list. "
        "Respond with a JSON array of skill IDs only (max 5). No explanation."
    )
    user_prompt = (
        f"Subtask: {subtask_instructions}\n"
        f"Available skills: {json.dumps(agent_skills)}\n"
        "Which skills are most relevant? Return JSON array of skill IDs."
    )
    try:
        result = _query_ai(user_prompt, system_prompt=system_prompt)
        raw = result.get("answer", "")
        match = re.search(r"\[[\s\S]*?\]", raw)
        if match:
            selected = json.loads(match.group(0))
            return [s for s in selected if s in agent_skills][:5]
    except Exception:
        pass
    return agent_skills[:3]


# ── Peer Review ───────────────────────────────────────────────────────────────

def peer_review_result(
    agent_id: str,
    subtask_title: str,
    result_text: str,
    reviewer_agent_type: str = "analytical",
) -> dict:
    """Have a 'reviewer' agent validate and improve a subtask result.

    Uses query_ai_for_agent() with an analytical model to check quality,
    flag issues, and optionally suggest improvements.

    Args:
        agent_id:           The agent whose result is being reviewed.
        subtask_title:      Short description of the subtask.
        result_text:        The raw result text to review.
        reviewer_agent_type: Agent type to use for the review model.

    Returns:
        dict with keys:
            approved    (bool)   — whether the result passes quality check
            feedback    (str)    — reviewer comments
            improved    (str)    — improved version (or original if no improvement needed)
            reviewer    (str)    — AI provider used for review
    """
    if not _AI_AVAILABLE or not result_text:
        return {"approved": True, "feedback": "", "improved": result_text, "reviewer": "none"}

    system_prompt = (
        "You are a quality-control reviewer for an AI agent company. "
        "Your job is to validate agent outputs and ensure they are accurate, "
        "complete, and actionable. Be concise and constructive. "
        "Respond with valid JSON only."
    )
    user_prompt = (
        f"Agent: {agent_id}\n"
        f"Task: {subtask_title}\n\n"
        f"Output to review:\n{result_text[:2000]}\n\n"
        "Review this output and respond with JSON:\n"
        '{"approved": true/false, "score": 1-10, "feedback": "...", '
        '"improved": "improved version or empty string if no improvement needed"}'
    )

    try:
        res = _query_ai_for_agent(reviewer_agent_type, user_prompt, system_prompt=system_prompt)
        raw = res.get("answer", "")
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            parsed = json.loads(match.group(0))
            improved = parsed.get("improved", "").strip() or result_text
            return {
                "approved": bool(parsed.get("approved", True)),
                "feedback": parsed.get("feedback", ""),
                "improved": improved,
                "reviewer": res.get("provider", "unknown"),
                "score": parsed.get("score", 7),
            }
    except Exception as exc:
        logger.debug("task-orchestrator: peer_review failed — %s", exc)

    return {"approved": True, "feedback": "", "improved": result_text, "reviewer": "error"}


# ── Async Subtask Execution ───────────────────────────────────────────────────

def _execute_subtask_inline(st: dict, plan: dict, capabilities: dict) -> dict:
    """Execute a single subtask inline using the best model for the agent type.

    This is called from a thread-pool worker. Returns the subtask dict
    updated with result, status, and completed_at.
    """
    agent_id = st.get("agent_id", "general")
    instructions = st.get("instructions", "")
    title = st.get("title", st["subtask_id"])
    skills = st.get("skills", [])

    # Build a rich system prompt from agent capabilities
    caps = capabilities.get("agents", {}).get(agent_id, {})
    agent_desc = caps.get("description", f"You are a specialist {agent_id} agent.")
    skills_text = ", ".join(skills[:5]) if skills else "general"

    system_prompt = (
        f"You are {agent_id}: {agent_desc}\n"
        f"Your active skills for this subtask: {skills_text}\n"
        "Deliver a complete, actionable result. Be specific and thorough."
    )

    # Use per-agent model routing
    res = _query_ai_for_agent(
        agent_id,
        instructions,
        system_prompt=system_prompt,
    )
    answer = res.get("answer", "")

    # Optionally run peer review on the result
    review = {"approved": True, "improved": answer, "feedback": ""}
    if PEER_REVIEW_ENABLED and answer and agent_id not in ("orchestrator",):
        review = peer_review_result(
            agent_id=agent_id,
            subtask_title=title,
            result_text=answer,
        )
        if review.get("feedback"):
            logger.info(
                "task-orchestrator: peer review for '%s' [%s] — approved=%s score=%s",
                title, agent_id, review["approved"], review.get("score", "?"),
            )

    final_result = review.get("improved") or answer

    st["status"] = "done"
    st["result"] = final_result
    st["peer_review"] = {
        "approved": review.get("approved", True),
        "feedback": review.get("feedback", ""),
        "reviewer": review.get("reviewer", "none"),
        "score": review.get("score", 7),
    }
    st["completed_at"] = now_iso()

    # Write result file for compatibility with check_agent_result()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{st['subtask_id']}.json"
    result_file.write_text(json.dumps({
        "subtask_id": st["subtask_id"],
        "agent_id": agent_id,
        "status": "done",
        "result": final_result,
        "peer_review": st["peer_review"],
        "completed_at": now_iso(),
    }, indent=2))

    logger.info(
        "task-orchestrator: subtask '%s' [%s] completed (provider=%s)",
        title, agent_id, res.get("provider", "?"),
    )
    return st


# ── Plan Execution ────────────────────────────────────────────────────────────

def execute_plan(plan: dict, capabilities: dict) -> None:
    """Drive a task plan forward using async parallel execution.

    Subtasks whose dependencies are satisfied are dispatched concurrently
    into a thread pool (up to MAX_PARALLEL workers). Each subtask is
    executed inline using query_ai_for_agent(), then optionally reviewed
    by a peer agent before the result is accepted.
    """
    subtasks = plan.get("subtasks", [])
    completed_ids = {st["subtask_id"] for st in subtasks if st["status"] == "done"}

    # Gather subtasks that are ready to run (dependencies satisfied, not yet started)
    ready = []
    for st in subtasks:
        if st["status"] != "pending":
            continue
        deps = st.get("depends_on", [])
        if any(d not in completed_ids for d in deps):
            continue
        ready.append(st)

    if not ready:
        # Also poll for external agent results (queue-based agents)
        for st in subtasks:
            if st["status"] != "running":
                continue
            result = check_agent_result(st["agent_id"], st["subtask_id"])
            if result:
                st["status"] = result.get("status", "done")
                st["result"] = result.get("result", "")
                st["completed_at"] = now_iso()
                completed_ids.add(st["subtask_id"])
    else:
        # Cap at MAX_PARALLEL
        batch = ready[:MAX_PARALLEL]
        for st in batch:
            st["status"] = "running"
            st["dispatched_at"] = now_iso()

        # Run the batch concurrently
        if len(batch) == 1:
            # Single subtask — run directly to avoid thread overhead
            _execute_subtask_inline(batch[0], plan, capabilities)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as pool:
                futures = {
                    pool.submit(_execute_subtask_inline, st, plan, capabilities): st
                    for st in batch
                }
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        st = futures[future]
                        st["status"] = "failed"
                        st["result"] = f"Error: {exc}"
                        st["completed_at"] = now_iso()
                        logger.error(
                            "task-orchestrator: subtask '%s' failed — %s",
                            st.get("subtask_id"), exc,
                        )

        for st in batch:
            completed_ids.add(st["subtask_id"])

    # Update plan status
    all_done = all(st["status"] in ("done", "failed") for st in subtasks)
    any_failed = any(st["status"] == "failed" for st in subtasks)

    if all_done:
        plan["status"] = "failed" if any_failed else "done"
        plan["completed_at"] = now_iso()
        aggregate_results(plan)


# ── Peer-Review Validation ────────────────────────────────────────────────────

def peer_review_subtask(subtask: dict, capabilities: dict) -> dict:
    """Ask a second agent to review and validate a completed subtask result.

    Returns an updated subtask dict with a "review" key added.
    The reviewer is the first agent in a complementary category.
    """
    if not _AI_AVAILABLE or not PEER_REVIEW_ENABLED:
        return subtask
    result_text = subtask.get("result", "")
    if not result_text:
        return subtask

    original_agent = subtask.get("agent_id", "")
    # Pick a reviewer: prefer a different category agent
    agents = capabilities.get("agents", {})
    reviewer_id = None
    original_category = agents.get(original_agent, {}).get("category", "")
    for aid, info in agents.items():
        if aid != original_agent and info.get("category") != original_category:
            reviewer_id = aid
            break
    if not reviewer_id:
        return subtask

    review_prompt = (
        f"You are acting as a quality reviewer ({reviewer_id}).\n"
        f"Review the following output from agent '{original_agent}':\n\n"
        f"Task: {subtask.get('title', subtask.get('subtask_id', ''))}\n"
        f"Instructions: {subtask.get('instructions', '')[:500]}\n\n"
        f"Output:\n{result_text[:1500]}\n\n"
        "Provide a brief review (2-4 sentences): Is the output accurate, complete, and useful? "
        "Note any issues or gaps. Rate quality 1-5."
    )
    try:
        review_result = _query_ai(
            review_prompt,
            system_prompt=(
                "You are a critical peer reviewer in a multi-agent AI company. "
                "Be concise, objective, and constructive."
            ),
        )
        review_text = review_result.get("answer", "")
        subtask["review"] = {
            "reviewer": reviewer_id,
            "text": review_text,
            "ts": now_iso(),
        }
        logger.info(
            "task-orchestrator: peer review for subtask '%s' by '%s'",
            subtask["subtask_id"], reviewer_id,
        )
    except Exception as exc:
        logger.debug("task-orchestrator: peer review failed — %s", exc)
    return subtask


# ── Async / Thread-Pool Execution ─────────────────────────────────────────────

def _execute_subtask_in_thread(subtask: dict, plan: dict, capabilities: dict) -> dict:
    """Execute a single subtask in a worker thread.

    Simulates agent work by generating an AI-driven result directly.
    In a real deployment agents run as separate processes; this provides
    immediate results for the thread-pool path.
    """
    try:
        agent_id = subtask.get("agent_id", "orchestrator")
        instructions = subtask.get("instructions", "")
        agent_info = capabilities.get("agents", {}).get(agent_id, {})

        if _AI_AVAILABLE:
            system_prompt = (
                f"You are the '{agent_id}' agent — {agent_info.get('description', '')}. "
                f"Complete the following subtask as part of a larger plan titled "
                f"'{plan.get('title', '')}'. "
                "Be thorough, specific, and return a complete, structured result."
            )
            result = _query_ai(instructions, system_prompt=system_prompt)
            answer = result.get("answer", "")
        else:
            answer = f"[{agent_id}] Subtask queued (AI unavailable): {instructions[:100]}"

        return {
            "subtask_id": subtask["subtask_id"],
            "status": "done",
            "result": answer,
            "completed_at": now_iso(),
        }
    except Exception as exc:
        logger.warning(
            "task-orchestrator: subtask '%s' failed in thread — %s",
            subtask.get("subtask_id"), exc,
        )
        return {
            "subtask_id": subtask["subtask_id"],
            "status": "failed",
            "result": f"Error: {exc}",
            "completed_at": now_iso(),
        }


def execute_plan_parallel(plan: dict, capabilities: dict) -> None:
    """Drive a task plan forward using a thread pool for concurrent execution.

    Dispatches all ready subtasks simultaneously (up to MAX_PARALLEL threads),
    waits for results, applies peer-review, then updates the plan.
    """
    subtasks = plan.get("subtasks", [])
    completed_ids = {st["subtask_id"] for st in subtasks if st["status"] == "done"}

    # Collect subtasks that are ready to run
    ready = []
    for st in subtasks:
        if st["status"] != "pending":
            continue
        deps = st.get("depends_on", [])
        if any(d not in completed_ids for d in deps):
            continue
        ready.append(st)

    if not ready:
        # Check for completed results from external agent processes
        for st in subtasks:
            if st["status"] != "running":
                continue
            result = check_agent_result(st["agent_id"], st["subtask_id"])
            if result:
                st["status"] = result.get("status", "done")
                st["result"] = result.get("result", "")
                st["completed_at"] = now_iso()
                completed_ids.add(st["subtask_id"])
    else:
        # Mark as running and dispatch the agent queue entries concurrently
        batch = ready[:MAX_PARALLEL]
        for st in batch:
            payload = {
                "subtask_id": st["subtask_id"],
                "plan_id": plan["id"],
                "task_title": plan.get("title", ""),
                "agent_id": st["agent_id"],
                "title": st.get("title", ""),
                "instructions": st.get("instructions", ""),
                "skills": st.get("skills", []),
                "dispatched_at": now_iso(),
            }
            dispatch_to_agent(st["agent_id"], payload)
            st["status"] = "running"
            st["dispatched_at"] = now_iso()

        # Execute in thread pool (provides direct AI results when agents are
        # embedded rather than separate processes)
        with ThreadPoolExecutor(max_workers=min(len(batch), MAX_PARALLEL)) as pool:
            futures = {
                pool.submit(_execute_subtask_in_thread, st, plan, capabilities): st
                for st in batch
            }
            for future in as_completed(futures):
                st = futures[future]
                try:
                    thread_result = future.result()
                    st["status"] = thread_result["status"]
                    st["result"] = thread_result["result"]
                    st["completed_at"] = thread_result["completed_at"]
                    completed_ids.add(st["subtask_id"])
                    logger.info(
                        "task-orchestrator: subtask '%s' completed (%s) via thread pool",
                        st["subtask_id"], st["status"],
                    )
                    # Peer-review the result
                    if st["status"] == "done":
                        peer_review_subtask(st, capabilities)
                except Exception as exc:
                    st["status"] = "failed"
                    st["result"] = f"Thread error: {exc}"
                    st["completed_at"] = now_iso()
                    logger.warning(
                        "task-orchestrator: subtask '%s' thread error — %s",
                        st["subtask_id"], exc,
                    )

    # Update plan status
    all_done = all(st["status"] in ("done", "failed") for st in subtasks)
    any_failed = any(st["status"] == "failed" for st in subtasks)

    if all_done:
        plan["status"] = "failed" if any_failed else "done"
        plan["completed_at"] = now_iso()
        aggregate_results(plan)


def aggregate_results(plan: dict) -> None:
    """Combine all subtask results and post a summary to the chatlog."""
    subtasks = plan.get("subtasks", [])
    results_parts = []
    for st in subtasks:
        if st.get("result"):
            peer_info = ""
            if st.get("peer_review", {}).get("feedback"):
                peer_info = f" _(reviewed, score {st['peer_review'].get('score','?')}/10)_"
            results_parts.append(
                f"**{st.get('title', st['subtask_id'])}** ({st['agent_id']}){peer_info}:\n{st['result']}"
            )

    if not results_parts:
        summary = f"Task '{plan.get('title')}' completed but no results were returned."
    else:
        results_text = "\n\n---\n\n".join(results_parts)
        if _AI_AVAILABLE:
            try:
                # Use the orchestrator/planning model for final synthesis
                synthesis = _query_ai_for_agent(
                    "orchestrator",
                    f"Synthesize these agent results into a coherent final answer:\n\n{results_text}",
                    system_prompt=(
                        "You are the final aggregator for a multi-agent AI company. "
                        "Combine the specialist outputs into a well-structured, comprehensive answer. "
                        "Preserve all important details but remove redundancy."
                    ),
                )
                summary = synthesis.get("answer", results_text)
            except Exception:
                summary = results_text
        else:
            summary = results_text

    status_emoji = "✅" if plan.get("status") == "done" else "⚠️"
    message = (
        f"{status_emoji} *Task Complete: {plan.get('title', 'Unnamed Task')}*\n\n"
        f"{summary}\n\n"
        f"_Agents used: {', '.join(set(st['agent_id'] for st in subtasks))}_\n"
        f"_Subtasks: {len(subtasks)} | Time: {plan.get('created_at', '?')} → {now_iso()}_"
    )
    append_chatlog({"ts": now_iso(), "type": "bot", "bot": "task-orchestrator", "message": message})
    logger.info("task-orchestrator: plan '%s' aggregated and posted", plan["id"])


# ── Command Handling ──────────────────────────────────────────────────────────

def handle_command(message: str, capabilities: dict, plans: list) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    # ── task <description> / orchestrate <description> ────────────────────────
    m = re.match(r"^(?:task|orchestrate)\s+(.+)$", msg_lower, re.DOTALL)
    if m and m.group(1).strip() not in ("status", "list", "cancel"):
        original_desc = msg[m.start(1):]
        active = get_active_plan(plans)
        if active:
            return (
                f"⚠️ A task is already running: *{active.get('title', active['id'])}*\n"
                f"Use `task cancel` to cancel it first, or `task status` to check progress."
            )
        task_id = str(uuid.uuid4())[:8]
        logger.info("task-orchestrator: decomposing task '%s'...", original_desc[:60])
        subtasks = decompose_task(original_desc, capabilities)

        # Enrich each subtask with selected skills
        for st in subtasks:
            st["skills"] = select_skills_for_agent(st["agent_id"], st["instructions"], capabilities)

        plan = {
            "id": task_id,
            "title": original_desc[:100],
            "status": "running",
            "created_at": now_iso(),
            "completed_at": None,
            "subtasks": subtasks,
        }
        plans.insert(0, plan)
        # Keep history bounded
        while len(plans) > MAX_PLANS_HISTORY:
            plans.pop()
        save_task_plans(plans)

        agent_list = ", ".join(set(st["agent_id"] for st in subtasks))
        return (
            f"🚀 *Task started!* ID: `{task_id}`\n"
            f"📋 Decomposed into {len(subtasks)} subtasks\n"
            f"🤖 Agents assigned: {agent_list}\n\n"
            + "\n".join(f"  {i+1}. [{st['agent_id']}] {st.get('title','')}" for i, st in enumerate(subtasks))
            + "\n\nResults will appear here when complete. Use `task status` to check progress."
        )

    # ── task status ───────────────────────────────────────────────────────────
    if msg_lower in ("task status", "task progress", "orchestrate status"):
        active = get_active_plan(plans)
        if not active:
            recent = [p for p in plans if p.get("status") == "done"][:3]
            if recent:
                lines = ["No active tasks. Recent completions:"]
                for p in recent:
                    lines.append(f"  ✅ {p.get('title','?')} (done {p.get('completed_at','?')})")
                return "\n".join(lines)
            return "No active or recent tasks. Submit one: `task <description>`"
        subtasks = active.get("subtasks", [])
        done = sum(1 for s in subtasks if s["status"] == "done")
        running = sum(1 for s in subtasks if s["status"] == "running")
        pending = sum(1 for s in subtasks if s["status"] == "pending")
        lines = [
            f"📊 *Task: {active.get('title','?')}*",
            f"Status: {active['status']} | {done}/{len(subtasks)} subtasks done",
            f"Running: {running} | Pending: {pending}",
            "",
        ]
        for st in subtasks:
            emoji = {"done": "✅", "running": "⏳", "pending": "⏸️", "failed": "❌"}.get(st["status"], "?")
            lines.append(f"  {emoji} [{st['agent_id']}] {st.get('title', st['subtask_id'])}")
        return "\n".join(lines)

    # ── task list ─────────────────────────────────────────────────────────────
    if msg_lower in ("task list", "tasks", "orchestrate list"):
        if not plans:
            return "No tasks found. Submit one: `task <description>`"
        lines = ["📋 *Recent Tasks:*"]
        for p in plans[:10]:
            emoji = {"done": "✅", "running": "⏳", "planning": "🧠", "failed": "❌"}.get(p.get("status", ""), "?")
            lines.append(f"  {emoji} `{p['id']}` — {p.get('title','?')[:60]} ({p.get('status','?')})")
        return "\n".join(lines)

    # ── task cancel ───────────────────────────────────────────────────────────
    if msg_lower in ("task cancel", "cancel task", "orchestrate cancel"):
        active = get_active_plan(plans)
        if not active:
            return "No active task to cancel."
        active["status"] = "cancelled"
        active["completed_at"] = now_iso()
        save_task_plans(plans)
        return f"🛑 Task `{active['id']}` cancelled: *{active.get('title','?')}*"

    # ── assign <agent> <subtask> ──────────────────────────────────────────────
    m = re.match(r"^assign\s+(\S+)\s+(.+)$", msg_lower, re.DOTALL)
    if m:
        agent_id = m.group(1).strip()
        instructions = msg[m.start(2):]
        known_agents = set(capabilities.get("agents", {}).keys())
        if agent_id not in known_agents:
            return f"Unknown agent '{agent_id}'. Available: {', '.join(sorted(known_agents))}"
        subtask_id = str(uuid.uuid4())[:8]
        payload = {
            "subtask_id": subtask_id,
            "plan_id": "manual",
            "task_title": "Manual assignment",
            "agent_id": agent_id,
            "title": f"Manual: {instructions[:40]}",
            "instructions": instructions,
            "skills": [],
            "dispatched_at": now_iso(),
        }
        dispatch_to_agent(agent_id, payload)
        return (
            f"✅ Subtask `{subtask_id}` dispatched to *{agent_id}*.\n"
            f"Instructions: {instructions[:100]}"
        )

    # ── agents ────────────────────────────────────────────────────────────────
    if msg_lower in ("agents", "list agents", "show agents"):
        agents = capabilities.get("agents", {})
        if not agents:
            return "No agent capabilities loaded."
        lines = ["🤖 *20 AI Agents:*\n"]
        for agent_id, info in agents.items():
            skills_preview = ", ".join(info.get("skills", [])[:3])
            lines.append(f"  • *{agent_id}* — {info.get('description','')[:60]}")
            if skills_preview:
                lines.append(f"    Skills: {skills_preview}...")
        return "\n".join(lines)

    return None  # not a recognized orchestrator command


# ── Timeout checker ───────────────────────────────────────────────────────────

def check_timeouts(plans: list) -> bool:
    """Mark overdue running plans as timed-out. Returns True if any changed."""
    changed = False
    now = now_ts()
    for p in plans:
        if p.get("status") not in ("running", "planning"):
            continue
        created = p.get("created_at", "")
        if not created:
            continue
        try:
            from datetime import datetime as _dt
            created_ts = _dt.fromisoformat(created.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if now - created_ts > PLAN_TIMEOUT_SECS:
            p["status"] = "timed_out"
            p["completed_at"] = now_iso()
            append_chatlog({
                "ts": now_iso(),
                "type": "bot",
                "bot": "task-orchestrator",
                "message": f"⏰ Task `{p['id']}` timed out after {PLAN_TIMEOUT_SECS}s: {p.get('title','?')}",
            })
            changed = True
    return changed


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available (limited mode)"
    print(
        f"[{now_iso()}] task-orchestrator started; "
        f"poll={POLL_INTERVAL}s max_parallel={MAX_PARALLEL}; {ai_status}"
    )

    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    last_processed_idx = len(load_chatlog())

    while True:
        capabilities = load_agent_capabilities()
        plans = load_task_plans()

        # Process new chatlog entries
        chatlog = load_chatlog()
        new_entries = chatlog[last_processed_idx:]
        last_processed_idx = len(chatlog)

        for entry in new_entries:
            if entry.get("type") != "user":
                continue
            message = entry.get("message", "").strip()
            if not message:
                continue
            response = handle_command(message, capabilities, plans)
            if response:
                append_chatlog({
                    "ts": now_iso(),
                    "type": "bot",
                    "bot": "task-orchestrator",
                    "message": response,
                })
                save_task_plans(plans)
                logger.info("task-orchestrator: handled command: %s", message[:60])

        # Drive active plan(s) forward (async thread-pool execution)
        active = get_active_plan(plans)
        if active:
            execute_plan_parallel(active, capabilities)
            save_task_plans(plans)

        # Timeout check
        if check_timeouts(plans):
            save_task_plans(plans)

        # Write state
        active_plan = get_active_plan(plans)
        write_state({
            "bot": "task-orchestrator",
            "ts": now_iso(),
            "status": "running",
            "active_plan": active_plan["id"] if active_plan else None,
            "active_plan_title": active_plan.get("title") if active_plan else None,
            "total_plans": len(plans),
            "agents_available": len(capabilities.get("agents", {})),
            "max_parallel": MAX_PARALLEL,
            "peer_review_enabled": PEER_REVIEW_ENABLED,
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

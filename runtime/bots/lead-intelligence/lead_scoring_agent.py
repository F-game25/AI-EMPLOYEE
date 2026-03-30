"""Lead Scoring Agent — embedding-based lead qualification and reranking.

Scores and ranks leads using:
  - NVIDIA NV-Embed-v2 semantic embeddings (ICP profile matching)
  - NVIDIA NV-Rerank cross-encoder reranking (precision refinement)
  - Configurable ICP profile (Ideal Customer Profile)
  - Multi-factor scoring: industry fit, budget signals, engagement

Commands:
  score <lead_id>          — score a single lead
  rank <query>             — rank all CRM leads against a query/ICP
  top <n>                  — list top N scored leads
  icp <description>        — set / update the ICP profile
  status                   — show scoring stats

State files:
  ~/.ai-employee/state/lead-scoring-agent.state.json
  ~/.ai-employee/state/leads-crm.json  (shared)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "lead-scoring-agent.state.json"
CRM_FILE = AI_HOME / "state" / "leads-crm.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("LEAD_SCORING_POLL_INTERVAL", "5"))
DEFAULT_ICP = os.environ.get(
    "LEAD_SCORING_DEFAULT_ICP",
    "B2B SaaS company 10-200 employees seeking AI automation and workflow tools",
)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("lead-scoring-agent")

# ── Dependency imports (graceful fallback) ────────────────────────────────────

_nim_path = AI_HOME / "bots" / "nvidia-nim"
_memory_path = AI_HOME / "bots" / "memory"
_ai_router_path = AI_HOME / "bots" / "ai-router"

for _p in [_nim_path, _memory_path, _ai_router_path]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from nim_client import NIMClient  # type: ignore
    _nim = NIMClient()
    _NIM_AVAILABLE = _nim.is_available()
except ImportError:
    _nim = None
    _NIM_AVAILABLE = False

try:
    from vector_memory import VectorMemory  # type: ignore
    _vmem = VectorMemory()
    _VMEM_AVAILABLE = True
except ImportError:
    _vmem = None
    _VMEM_AVAILABLE = False

try:
    from ai_router import query_ai_for_agent  # type: ignore
    _ROUTER_AVAILABLE = True
except ImportError:
    _ROUTER_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"scored": 0, "icp": DEFAULT_ICP, "last_run": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


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


def _lead_text(lead: dict) -> str:
    """Build a rich text representation of a lead for embedding."""
    parts = [
        lead.get("name", ""),
        lead.get("description", ""),
        lead.get("industry", ""),
        lead.get("location", ""),
        lead.get("website", ""),
        " ".join(str(v) for v in lead.get("metadata", {}).values()),
    ]
    return " | ".join(p for p in parts if p)


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_lead_embedding(lead: dict, icp_profile: str) -> float:
    """Compute a 0–1 ICP fit score using embedding cosine similarity.

    Falls back to 0.5 when NIM is unavailable.
    """
    if not _NIM_AVAILABLE:
        return 0.5

    lead_text = _lead_text(lead)
    if not lead_text.strip():
        return 0.0

    lead_vec = _nim.embed_one(lead_text, input_type="passage")
    icp_vec = _nim.embed_one(icp_profile, input_type="query")

    if not lead_vec or not icp_vec:
        return 0.5

    from vector_memory import cosine_similarity  # type: ignore
    return round(cosine_similarity(lead_vec, icp_vec), 4)


def score_lead_full(lead: dict, icp_profile: str) -> dict:
    """Compute a multi-factor score for a lead and return enriched lead dict.

    Factors:
      - Embedding similarity to ICP (weight 0.5)
      - ICP keyword match (weight 0.3)
      - Data completeness (website, email, description) (weight 0.2)

    Returns:
        Lead dict with added keys: nim_score, keyword_score, completeness_score,
        composite_score.
    """
    lead = dict(lead)

    # 1. Embedding similarity
    nim_score = score_lead_embedding(lead, icp_profile)

    # 2. Keyword score
    icp_words = set(icp_profile.lower().split())
    lead_words = set(_lead_text(lead).lower().split())
    overlap = len(icp_words & lead_words)
    keyword_score = round(min(overlap / max(len(icp_words), 1), 1.0), 4)

    # 3. Data completeness
    present = sum([
        bool(lead.get("name")),
        bool(lead.get("website")),
        bool(lead.get("description")),
        bool(lead.get("email")),
        bool(lead.get("industry")),
    ])
    completeness_score = round(present / 5.0, 2)

    # 4. Composite
    composite = round(
        0.5 * nim_score + 0.3 * keyword_score + 0.2 * completeness_score, 4
    )

    lead.update({
        "nim_score": nim_score,
        "keyword_score": keyword_score,
        "completeness_score": completeness_score,
        "composite_score": composite,
        "scored_at": _now_iso(),
    })
    return lead


def rank_leads(leads: list[dict], icp_profile: str, top_n: int = 20) -> list[dict]:
    """Score and rank all leads against the ICP profile.

    Uses two-stage ranking:
      1. Embedding similarity (fast, approximate)
      2. NV-Rerank cross-encoder (slow, precise) — applied to top candidates

    Args:
        leads:       List of lead dicts.
        icp_profile: ICP description string.
        top_n:       Number of top leads to return after reranking.

    Returns:
        Sorted list of scored lead dicts (highest composite_score first).
    """
    if not leads:
        return []

    # Stage 1: Score all leads
    scored = [score_lead_full(lead, icp_profile) for lead in leads]
    scored.sort(key=lambda l: l.get("composite_score", 0), reverse=True)

    # Stage 2: Rerank top candidates with NV-Rerank
    top_candidates = scored[:min(top_n * 2, len(scored))]
    if _NIM_AVAILABLE and len(top_candidates) > 1:
        passages = [_lead_text(l) for l in top_candidates]
        reranked = _nim.rerank(icp_profile, passages, top_n=top_n)
        if reranked:
            reranked_leads = []
            for r in reranked:
                idx = r["index"]
                if idx < len(top_candidates):
                    lead = dict(top_candidates[idx])
                    lead["rerank_score"] = r["score"]
                    reranked_leads.append(lead)
            return reranked_leads

    return scored[:top_n]


# ── Commands ──────────────────────────────────────────────────────────────────

def handle_command(cmd: str) -> str:
    cmd = cmd.strip()
    lower = cmd.lower()
    state = _load_state()
    icp = state.get("icp", DEFAULT_ICP)

    if lower.startswith("score "):
        lead_id = cmd[6:].strip()
        crm = _load_crm()
        target = next((l for l in crm if l.get("id") == lead_id), None)
        if not target:
            return f"❌ Lead not found: {lead_id}"
        scored = score_lead_full(target, icp)
        # Update CRM
        for i, l in enumerate(crm):
            if l.get("id") == lead_id:
                crm[i] = scored
                break
        _save_crm(crm)
        return (
            f"🎯 Lead Score for {scored.get('name', lead_id)}\n"
            f"  NIM similarity: {scored.get('nim_score', 0):.2%}\n"
            f"  Keyword match:  {scored.get('keyword_score', 0):.2%}\n"
            f"  Completeness:   {scored.get('completeness_score', 0):.2%}\n"
            f"  ─────────────────────\n"
            f"  Composite:      {scored.get('composite_score', 0):.2%}"
        )

    if lower.startswith("rank "):
        query_icp = cmd[5:].strip() or icp
        crm = _load_crm()
        ranked = rank_leads(crm, query_icp, top_n=10)
        if not ranked:
            return "📭 No leads to rank."
        lines = [f"🏆 Top {len(ranked)} leads ranked by ICP fit:"]
        for i, l in enumerate(ranked, 1):
            score_val = l.get("rerank_score") or l.get("composite_score", 0)
            lines.append(f"  {i}. {l.get('name', l.get('id', '?'))} — score: {score_val:.4f}")
        return "\n".join(lines)

    if lower.startswith("top "):
        try:
            n = int(cmd[4:].strip())
        except ValueError:
            n = 10
        crm = _load_crm()
        sorted_crm = sorted(crm, key=lambda l: l.get("composite_score", 0), reverse=True)
        top = sorted_crm[:n]
        if not top:
            return "📭 No scored leads yet. Run 'rank <icp>' first."
        lines = [f"🏆 Top {len(top)} leads:"]
        for l in top:
            lines.append(
                f"  • {l.get('name', l.get('id', '?'))} "
                f"({l.get('industry', '?')}) — {l.get('composite_score', 0):.2%}"
            )
        return "\n".join(lines)

    if lower.startswith("icp "):
        new_icp = cmd[4:].strip()
        state["icp"] = new_icp
        _save_state(state)
        return f"✅ ICP profile updated:\n{new_icp}"

    if lower == "status":
        crm = _load_crm()
        scored_count = sum(1 for l in crm if "composite_score" in l)
        return (
            f"📊 Lead Scoring Status\n"
            f"CRM size: {len(crm)}\n"
            f"Scored leads: {scored_count}\n"
            f"Current ICP: {icp[:100]}{'…' if len(icp) > 100 else ''}\n"
            f"Last run: {state.get('last_run', 'never')}"
        )

    return (
        f"❓ Unknown command: {cmd}\n"
        "Usage: score <lead_id> | rank [icp_query] | top <n> | icp <description> | status"
    )


# ── Main polling loop ─────────────────────────────────────────────────────────

def main() -> None:
    import time

    logger.info("lead-scoring-agent: starting")
    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        for task_file in sorted(AGENT_TASKS_DIR.glob("lead-scoring-agent_*.json")):
            try:
                task = json.loads(task_file.read_text())
                result = handle_command(task.get("command", ""))
                result_file = RESULTS_DIR / f"{task_file.stem}.result.json"
                result_file.write_text(json.dumps({"result": result, "ts": _now_iso()}))
                task_file.unlink()
            except Exception as exc:
                logger.warning("lead-scoring-agent: task error — %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

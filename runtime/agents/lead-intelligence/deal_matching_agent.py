"""Deal Matching Agent — business pairing and partnership opportunity detection.

Identifies high-value business pairing opportunities by:
  - Embedding-based similarity clustering (companies with complementary profiles)
  - NVIDIA Nemotron reasoning for strategic fit analysis
  - Deal scoring based on industry overlap, geography, size compatibility
  - Partnership recommendation generation

Commands:
  match <company_a> <company_b>   — score compatibility between two companies
  find <lead_id>                  — find best partner matches for a lead
  cluster <niche>                 — cluster leads by similarity within a niche
  recommend <lead_id>             — generate a partnership pitch for a lead
  status                          — show deal matching stats

State files:
  ~/.ai-employee/state/deal-matching-agent.state.json
  ~/.ai-employee/state/leads-crm.json  (shared)
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "deal-matching-agent.state.json"
CRM_FILE = AI_HOME / "state" / "leads-crm.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("DEAL_MATCHING_POLL_INTERVAL", "5"))
DEAL_MIN_SCORE = float(os.environ.get("DEAL_MIN_SCORE", "0.6"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("deal-matching-agent")

# ── Dependency imports ────────────────────────────────────────────────────────

_nim_path = AI_HOME / "agents" / "nvidia-nim"
_memory_path = AI_HOME / "agents" / "memory"
_ai_router_path = AI_HOME / "agents" / "ai-router"

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
    from vector_memory import VectorMemory, cosine_similarity  # type: ignore
    _vmem = VectorMemory()
    _VMEM_AVAILABLE = True
except ImportError:
    _vmem = None
    _VMEM_AVAILABLE = False
    def cosine_similarity(a, b):  # type: ignore  # noqa: E301
        logger.warning("deal-matching-agent: vector_memory unavailable — cosine_similarity returns 0.0")
        return 0.0

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
    return {"matches_run": 0, "deals_found": 0, "last_run": None}


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


def _lead_text(lead: dict) -> str:
    parts = [
        lead.get("name", ""),
        lead.get("description", ""),
        lead.get("industry", ""),
        lead.get("location", ""),
    ]
    return " | ".join(p for p in parts if p)


def _query_ai_reasoning(prompt: str, system: str = "") -> str:
    """Use NVIDIA Nemotron for strategic analysis; fall back to ai_router."""
    if _NIM_AVAILABLE:
        result = _nim.chat(prompt, system_prompt=system, temperature=0.3)
        if result.get("answer"):
            return result["answer"]
    if _ROUTER_AVAILABLE:
        result = query_ai_for_agent("deal-matching-agent", prompt, system_prompt=system)
        return result.get("answer", "")
    return ""


# ── Compatibility Scoring ─────────────────────────────────────────────────────

def score_compatibility(lead_a: dict, lead_b: dict) -> dict:
    """Compute a multi-factor compatibility score between two companies.

    Factors:
      1. Embedding similarity (complementary profiles, not identical)
      2. Industry relationship (same niche → referral, different → partnership)
      3. Geographic proximity (same location → local deal, different → remote)
      4. Data completeness (penalise sparse profiles)

    Returns:
        dict with keys: score (0–1), factors, recommendation
    """
    text_a = _lead_text(lead_a)
    text_b = _lead_text(lead_b)

    # 1. Embedding-based similarity
    embed_sim = 0.5
    if _NIM_AVAILABLE and text_a and text_b:
        vec_a = _nim.embed_one(text_a, input_type="passage")
        vec_b = _nim.embed_one(text_b, input_type="passage")
        if vec_a and vec_b:
            embed_sim = cosine_similarity(vec_a, vec_b)
            # For partnerships, we want complementary (moderate similarity 0.4–0.7)
            # rather than identical (>0.9) or completely unrelated (<0.2)
            if embed_sim > 0.7:
                embed_sim = 0.7 - (embed_sim - 0.7)  # penalty for too-similar
            embed_sim = max(0.0, embed_sim)

    # 2. Industry relationship
    ind_a = lead_a.get("industry", "").lower()
    ind_b = lead_b.get("industry", "").lower()
    if ind_a and ind_b:
        if ind_a == ind_b:
            industry_score = 0.7  # same niche → referral potential
        elif any(kw in ind_b for kw in ind_a.split()) or any(kw in ind_a for kw in ind_b.split()):
            industry_score = 0.8  # adjacent niche → strong partnership
        else:
            industry_score = 0.5  # different industries → moderate
    else:
        industry_score = 0.4

    # 3. Geographic factor (same location = bonus for referral, different = ok for remote)
    loc_a = lead_a.get("location", "").lower().strip()
    loc_b = lead_b.get("location", "").lower().strip()
    if loc_a and loc_b and loc_a == loc_b:
        geo_score = 0.9
    elif loc_a and loc_b:
        geo_score = 0.6
    else:
        geo_score = 0.5  # unknown location

    # 4. Completeness
    def _completeness(lead):
        return sum([
            bool(lead.get("name")), bool(lead.get("description")),
            bool(lead.get("website")), bool(lead.get("industry")),
        ]) / 4.0

    completeness = (_completeness(lead_a) + _completeness(lead_b)) / 2.0

    # Composite
    composite = round(
        0.35 * embed_sim + 0.30 * industry_score + 0.20 * geo_score + 0.15 * completeness, 4
    )

    return {
        "score": composite,
        "factors": {
            "embedding_similarity": round(embed_sim, 4),
            "industry_match": round(industry_score, 4),
            "geographic": round(geo_score, 4),
            "completeness": round(completeness, 4),
        },
        "recommendation": _score_label(composite),
    }


def _score_label(score: float) -> str:
    if score >= 0.75:
        return "🔥 Excellent match — pursue deal"
    if score >= 0.60:
        return "✅ Good fit — worth exploring"
    if score >= 0.45:
        return "⚠️  Moderate fit — optional outreach"
    return "❌ Poor fit — skip"


def find_best_matches(lead: dict, candidates: list[dict], top_n: int = 5) -> list[dict]:
    """Find the best partnership matches for a given lead from a candidate pool.

    Args:
        lead:       Reference lead.
        candidates: Pool of leads to match against.
        top_n:      Number of top matches to return.

    Returns:
        List of {lead_id, name, score, factors, recommendation} dicts.
    """
    results = []
    for candidate in candidates:
        if candidate.get("id") == lead.get("id"):
            continue
        compat = score_compatibility(lead, candidate)
        results.append({
            "lead_id": candidate.get("id", ""),
            "name": candidate.get("name", ""),
            "industry": candidate.get("industry", ""),
            "location": candidate.get("location", ""),
            **compat,
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


def cluster_leads(leads: list[dict], niche: str = "") -> list[list[dict]]:
    """Group leads into similarity clusters using embedding vectors.

    Uses simple greedy clustering: a lead joins an existing cluster if its
    embedding cosine similarity to the cluster centroid exceeds 0.7.

    Args:
        leads:  List of lead dicts.
        niche:  Optional niche filter applied before clustering.

    Returns:
        List of clusters (each cluster is a list of leads).
    """
    if niche:
        leads = [l for l in leads if niche.lower() in l.get("industry", "").lower()]
    if not leads:
        return []

    if not _NIM_AVAILABLE:
        # Fallback: group by industry
        by_industry: dict[str, list] = {}
        for lead in leads:
            ind = lead.get("industry", "unknown")
            by_industry.setdefault(ind, []).append(lead)
        return list(by_industry.values())

    # Embed all leads
    texts = [_lead_text(l) for l in leads]
    vectors = _nim.embed(texts, input_type="passage")
    if not vectors or len(vectors) != len(leads):
        return [leads]

    # Greedy clustering
    clusters: list[list] = []
    cluster_vecs: list[list[float]] = []
    used = [False] * len(leads)

    for i, (lead, vec) in enumerate(zip(leads, vectors)):
        if used[i]:
            continue
        # Find best existing cluster
        best_cluster = -1
        best_sim = 0.0
        for ci, cvec in enumerate(cluster_vecs):
            sim = cosine_similarity(vec, cvec)
            if sim > 0.70 and sim > best_sim:
                best_sim = sim
                best_cluster = ci
        if best_cluster >= 0:
            clusters[best_cluster].append(lead)
            # Update centroid (running average)
            n = len(clusters[best_cluster])
            old_cvec = cluster_vecs[best_cluster]
            cluster_vecs[best_cluster] = [
                (old * (n - 1) + new) / n for old, new in zip(old_cvec, vec)
            ]
        else:
            clusters.append([lead])
            cluster_vecs.append(vec)
        used[i] = True

    return clusters


def generate_partnership_pitch(lead_a: dict, lead_b: dict) -> str:
    """Generate a partnership recommendation pitch using NVIDIA Nemotron.

    Args:
        lead_a: The source company (our client or lead).
        lead_b: The potential partner company.

    Returns:
        Partnership pitch text.
    """
    compat = score_compatibility(lead_a, lead_b)
    prompt = (
        f"Write a brief, compelling business partnership pitch explaining why "
        f"'{lead_a.get('name', 'Company A')}' ({lead_a.get('industry', '')}) and "
        f"'{lead_b.get('name', 'Company B')}' ({lead_b.get('industry', '')}) "
        f"would be a strong strategic partnership.\n\n"
        f"Compatibility score: {compat['score']:.0%}\n"
        f"Industry: {lead_a.get('industry', 'N/A')} ↔ {lead_b.get('industry', 'N/A')}\n"
        f"Location: {lead_a.get('location', 'N/A')} | {lead_b.get('location', 'N/A')}\n\n"
        "Write 2-3 specific reasons why this deal makes business sense. "
        "Include potential revenue/value unlock. Be direct and actionable. "
        "Max 150 words."
    )
    return _query_ai_reasoning(
        prompt,
        system=(
            "You are a strategic business development expert. Write concise, "
            "data-driven partnership pitches that highlight mutual value."
        ),
    )


# ── Commands ──────────────────────────────────────────────────────────────────

def handle_command(cmd: str) -> str:
    cmd = cmd.strip()
    lower = cmd.lower()
    state = _load_state()

    if lower.startswith("match "):
        parts = cmd[6:].split(maxsplit=1)
        if len(parts) < 2:
            return "❌ Usage: match <company_a_id_or_name> <company_b_id_or_name>"
        crm = _load_crm()
        lead_a = _find_lead(parts[0], crm)
        lead_b = _find_lead(parts[1], crm)
        if not lead_a:
            return f"❌ Not found: {parts[0]}"
        if not lead_b:
            return f"❌ Not found: {parts[1]}"
        compat = score_compatibility(lead_a, lead_b)
        state["matches_run"] = state.get("matches_run", 0) + 1
        _save_state(state)
        return (
            f"🤝 Compatibility: {lead_a.get('name', '?')} × {lead_b.get('name', '?')}\n"
            f"  Score:  {compat['score']:.2%}\n"
            f"  Embed:  {compat['factors']['embedding_similarity']:.2%}\n"
            f"  Industry: {compat['factors']['industry_match']:.2%}\n"
            f"  Geo:    {compat['factors']['geographic']:.2%}\n"
            f"  Result: {compat['recommendation']}"
        )

    if lower.startswith("find "):
        lead_id = cmd[5:].strip()
        crm = _load_crm()
        lead = _find_lead(lead_id, crm)
        if not lead:
            return f"❌ Lead not found: {lead_id}"
        matches = find_best_matches(lead, crm, top_n=5)
        good = [m for m in matches if m["score"] >= DEAL_MIN_SCORE]
        state["deals_found"] = state.get("deals_found", 0) + len(good)
        state["last_run"] = _now_iso()
        _save_state(state)
        if not good:
            return f"📭 No strong matches found for {lead.get('name', lead_id)}."
        lines = [f"🤝 Top matches for {lead.get('name', lead_id)}:"]
        for m in good:
            lines.append(
                f"  • {m['name']} ({m['industry']}) — {m['score']:.2%} — {m['recommendation']}"
            )
        return "\n".join(lines)

    if lower.startswith("cluster "):
        niche = cmd[8:].strip()
        crm = _load_crm()
        clusters = cluster_leads(crm, niche)
        if not clusters:
            return f"📭 No leads found for niche: {niche}"
        lines = [f"🔵 {len(clusters)} clusters for niche '{niche}':"]
        for i, cluster in enumerate(clusters, 1):
            names = [l.get("name", l.get("id", "?")) for l in cluster[:4]]
            lines.append(f"  Cluster {i} ({len(cluster)} leads): {', '.join(names)}")
        return "\n".join(lines)

    if lower.startswith("recommend "):
        lead_id = cmd[10:].strip()
        crm = _load_crm()
        lead = _find_lead(lead_id, crm)
        if not lead:
            return f"❌ Lead not found: {lead_id}"
        matches = find_best_matches(lead, crm, top_n=1)
        if not matches:
            return f"📭 No matches found for {lead.get('name', lead_id)}."
        best = matches[0]
        partner = _find_lead(best["lead_id"], crm)
        if not partner:
            return f"📭 Partner lead not found."
        pitch = generate_partnership_pitch(lead, partner)
        return (
            f"💼 Partnership Pitch: {lead.get('name', '?')} × {partner.get('name', '?')}\n"
            f"Score: {best['score']:.2%}\n\n{pitch}"
        )

    if lower == "status":
        return (
            f"📊 Deal Matching Status\n"
            f"Matches run: {state.get('matches_run', 0)}\n"
            f"Deals found: {state.get('deals_found', 0)}\n"
            f"Min score threshold: {DEAL_MIN_SCORE:.0%}\n"
            f"Last run: {state.get('last_run', 'never')}"
        )

    return (
        f"❓ Unknown command: {cmd}\n"
        "Usage: match <a> <b> | find <lead_id> | cluster <niche> | "
        "recommend <lead_id> | status"
    )


def _find_lead(query: str, crm: list) -> dict | None:
    """Find a lead by ID or name (case-insensitive prefix)."""
    for l in crm:
        if l.get("id") == query:
            return l
    q = query.lower()
    for l in crm:
        if l.get("name", "").lower().startswith(q):
            return l
    return None


# ── Main polling loop ─────────────────────────────────────────────────────────

def main() -> None:
    import time

    logger.info("deal-matching-agent: starting")
    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        for task_file in sorted(AGENT_TASKS_DIR.glob("deal-matching-agent_*.json")):
            try:
                task = json.loads(task_file.read_text())
                result = handle_command(task.get("command", ""))
                result_file = RESULTS_DIR / f"{task_file.stem}.result.json"
                result_file.write_text(json.dumps({"result": result, "ts": _now_iso()}))
                task_file.unlink()
            except Exception as exc:
                logger.warning("deal-matching-agent: task error — %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

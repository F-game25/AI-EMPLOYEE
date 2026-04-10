"""Skill Registry — unified manifest, Decision Engine, ROI Tracker, Change Log.

At startup (or on demand) this module:
  1. Introspects every agent directory under ``runtime/agents/``
  2. Cross-references the 147-skill library (``skills_library.json``)
  3. Merges agent capabilities from ``agent_capabilities.json``
  4. Emits a single ``skill_registry_manifest.json`` consumed by any part of
     the system that needs to know "what can this system do?"

It also exposes three thin sub-systems that fill the gaps identified in the
architecture audit:

Decision Engine
    Score any (agent, action) pair by *profit potential*, *execution speed*,
    and *task complexity* and return a ranked recommendation.

ROI Tracker
    Append per-action revenue / cost events and query cumulative ROI per agent
    or per skill — giving a unified money trail across all 74 agents.

Change Log
    Append structured "why did we change X?" events so every automated
    decision has an auditable, cross-session history.

Usage
-----
    from core.skill_registry import get_registry

    reg = get_registry()               # singleton; builds manifest once
    reg.save_manifest()                # write JSON to disk

    # Decision Engine
    scores = reg.decision_engine.score("lead-generator", "cold_outreach")

    # ROI Tracker
    reg.roi_tracker.record(agent="lead-generator", action="cold_outreach",
                           revenue=120.0, cost=5.0)
    summary = reg.roi_tracker.summary()

    # Change Log
    reg.change_log.append(agent="ascend-forge", action="patch_applied",
                          reason="coverage gap identified by /scan",
                          diff_summary="Added null-check in brain.py")
    history = reg.change_log.recent(n=20)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent.parent  # AI-EMPLOYEE/
_AGENTS_DIR = _REPO_ROOT / "runtime" / "agents"
_CONFIG_DIR = _REPO_ROOT / "runtime" / "config"
_SKILLS_LIBRARY_FILE = _CONFIG_DIR / "skills_library.json"
_AGENT_CAPS_FILE = _CONFIG_DIR / "agent_capabilities.json"

# Default output path (can be overridden via AI_HOME env var)
_AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_MANIFEST_FILE = _AI_HOME / "config" / "skill_registry_manifest.json"
_ROI_LOG_FILE = _AI_HOME / "state" / "roi_tracker.jsonl"
_CHANGE_LOG_FILE = _AI_HOME / "state" / "change_log.jsonl"

# Agents whose directories are infrastructure, not capability agents
_INFRA_AGENTS = {
    "problem-solver-ui",
    "problem-solver",
    "scheduler-runner",
    "status-reporter",
    "auto-updater",
    "discovery",
    "tools",
}

# Maximum lines kept on disk for append-only logs
_MAX_LOG_LINES = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _append_jsonl(path: Path, entry: dict, max_lines: int = _MAX_LOG_LINES) -> None:
    """Append *entry* to a .jsonl file, trimming to *max_lines* if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        lines.append(line)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        path.write_text(line + "\n", encoding="utf-8")


def _read_jsonl(path: Path, n: int = 0) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entries.append(json.loads(raw))
        except Exception:
            pass
    return entries[-n:] if n > 0 else entries


# ── Decision Engine ────────────────────────────────────────────────────────────

# Static scoring weights (overridable via env vars for experimentation)
_W_PROFIT = float(os.environ.get("DE_WEIGHT_PROFIT", "0.5"))
_W_SPEED = float(os.environ.get("DE_WEIGHT_SPEED", "0.3"))
_W_COMPLEXITY = float(os.environ.get("DE_WEIGHT_COMPLEXITY", "0.2"))

# Category → baseline profit potential (1–10)
_CATEGORY_PROFIT: dict[str, float] = {
    "sales": 9.0,
    "finance": 8.5,
    "trading": 8.0,
    "ecommerce": 8.0,
    "growth": 7.5,
    "analytics": 7.0,
    "marketing": 7.0,
    "content": 6.5,
    "social": 6.0,
    "coordination": 6.0,
    "research": 5.5,
    "development": 5.5,
    "creative": 5.0,
    "hr": 4.5,
    "support": 4.5,
    "crypto": 7.5,
    "strategy": 7.0,
    "management": 6.0,
    "automation": 6.5,
    "other": 5.0,
}

# Category → baseline execution speed (1–10, higher = faster)
_CATEGORY_SPEED: dict[str, float] = {
    "automation": 9.0,
    "coordination": 8.5,
    "content": 8.0,
    "social": 8.0,
    "analytics": 7.5,
    "research": 6.5,
    "sales": 6.0,
    "marketing": 6.0,
    "development": 5.5,
    "growth": 6.0,
    "finance": 5.5,
    "trading": 7.0,
    "ecommerce": 6.5,
    "hr": 5.0,
    "support": 7.0,
    "creative": 6.0,
    "management": 5.5,
    "strategy": 5.0,
    "crypto": 7.0,
    "other": 5.0,
}

# Category → baseline complexity penalty (1–10; higher = MORE complex = lower score)
_CATEGORY_COMPLEXITY: dict[str, float] = {
    "coordination": 9.0,
    "development": 8.5,
    "strategy": 8.0,
    "finance": 7.5,
    "trading": 7.5,
    "analytics": 7.0,
    "research": 6.5,
    "growth": 6.0,
    "hr": 6.0,
    "management": 6.0,
    "crypto": 7.0,
    "ecommerce": 5.5,
    "sales": 5.0,
    "marketing": 5.0,
    "social": 4.5,
    "content": 4.5,
    "creative": 4.0,
    "support": 4.0,
    "automation": 3.5,
    "other": 5.0,
}


class DecisionEngine:
    """Score (agent, action) pairs and rank recommendations.

    Scores are in the range [0, 10] and composed of three weighted dimensions:

    * **profit**     — revenue potential of the agent's category
    * **speed**      — typical execution speed for the agent's category
    * **complexity** — task complexity (penalises high-complexity actions)

    The composite score is::

        score = W_PROFIT * profit
              + W_SPEED  * speed
              + W_COMPLEXITY * (10 - complexity)  # invert: lower complexity = better
    """

    def __init__(self, registry: "SkillRegistry") -> None:
        self._registry = registry

    def _agent_category(self, agent_id: str) -> str:
        agents = self._registry.manifest.get("agents", {})
        return agents.get(agent_id, {}).get("category", "other")

    def score(self, agent_id: str, action: str = "") -> dict:
        """Return a score dict for an (agent, optional action).

        Parameters
        ----------
        agent_id:
            Canonical agent identifier, e.g. ``"lead-generator"``.
        action:
            Optional action or skill name to narrow the score.

        Returns
        -------
        dict with keys: agent_id, action, profit, speed, complexity,
                        composite, recommendation
        """
        cat = self._agent_category(agent_id)
        profit = _CATEGORY_PROFIT.get(cat, 5.0)
        speed = _CATEGORY_SPEED.get(cat, 5.0)
        complexity = _CATEGORY_COMPLEXITY.get(cat, 5.0)

        composite = (
            _W_PROFIT * profit
            + _W_SPEED * speed
            + _W_COMPLEXITY * (10.0 - complexity)
        )
        composite = round(min(10.0, max(0.0, composite)), 2)

        if composite >= 7.5:
            recommendation = "high priority — deploy first"
        elif composite >= 5.0:
            recommendation = "medium priority — schedule soon"
        else:
            recommendation = "low priority — defer or review"

        return {
            "agent_id": agent_id,
            "action": action,
            "category": cat,
            "profit": profit,
            "speed": speed,
            "complexity": complexity,
            "composite": composite,
            "recommendation": recommendation,
        }

    def rank(self, agent_ids: list[str]) -> list[dict]:
        """Return agents sorted by composite score, highest first."""
        scores = [self.score(a) for a in agent_ids]
        return sorted(scores, key=lambda s: s["composite"], reverse=True)

    def top(self, n: int = 10) -> list[dict]:
        """Return the top-n agents from the full registry, ranked by score."""
        all_agents = list(self._registry.manifest.get("agents", {}).keys())
        return self.rank(all_agents)[:n]


# ── ROI Tracker ────────────────────────────────────────────────────────────────


class RoiTracker:
    """Per-action revenue tracker giving a unified money trail across agents.

    All events are appended to ``~/.ai-employee/state/roi_tracker.jsonl``
    so they survive restarts and accumulate across sessions.

    Each event record::

        {
          "ts":      "2026-04-10T08:00:00Z",
          "agent":   "lead-generator",
          "action":  "cold_outreach",
          "skill":   "email_copywriting",    # optional
          "revenue": 120.0,                  # dollars / units, positive
          "cost":    5.0,                    # dollars / units, positive
          "roi":     23.0,                   # (revenue - cost) / cost * 100  %
          "note":    "3 replies converted"   # optional free-text
        }
    """

    def __init__(self, log_file: Path | None = None) -> None:
        self._log_file = log_file or _ROI_LOG_FILE
        self._lock = threading.Lock()

    def record(
        self,
        agent: str,
        action: str,
        revenue: float,
        cost: float = 0.0,
        skill: str = "",
        note: str = "",
    ) -> dict:
        """Append one ROI event and return the recorded entry."""
        if cost < 0 or revenue < 0:
            raise ValueError("revenue and cost must be non-negative")
        # When cost is 0 and revenue > 0 this represents pure profit (infinite ROI).
        # We store None to distinguish it from a genuinely zero ROI (revenue == cost).
        if cost == 0:
            roi_pct: float | None = None if revenue > 0 else 0.0
        else:
            roi_pct = (revenue - cost) / cost * 100.0
        entry = {
            "ts": _now_iso(),
            "agent": agent,
            "action": action,
            "skill": skill,
            "revenue": round(revenue, 4),
            "cost": round(cost, 4),
            "roi": round(roi_pct, 2) if roi_pct is not None else None,
            "note": note,
        }
        with self._lock:
            _append_jsonl(self._log_file, entry)
        return entry

    def summary(
        self,
        agent: str | None = None,
        skill: str | None = None,
        n: int = 0,
    ) -> dict:
        """Aggregate ROI events.

        Parameters
        ----------
        agent:
            Filter to a specific agent; ``None`` aggregates all.
        skill:
            Filter to a specific skill; ``None`` aggregates all.
        n:
            If > 0, only consider the most recent *n* events.

        Returns
        -------
        dict with keys: events, total_revenue, total_cost, net_profit, roi_pct,
                        by_agent (dict), by_skill (dict)
        """
        with self._lock:
            events = _read_jsonl(self._log_file, n=n)

        if agent:
            events = [e for e in events if e.get("agent") == agent]
        if skill:
            events = [e for e in events if e.get("skill") == skill]

        total_revenue = sum(e.get("revenue", 0.0) for e in events)
        total_cost = sum(e.get("cost", 0.0) for e in events)
        net_profit = total_revenue - total_cost
        roi_pct = (net_profit / total_cost * 100.0) if total_cost > 0 else 0.0

        by_agent: dict[str, dict] = {}
        by_skill: dict[str, dict] = {}
        for e in events:
            for key, bucket in (("agent", by_agent), ("skill", by_skill)):
                name = e.get(key, "") or "unknown"
                if name not in bucket:
                    bucket[name] = {"revenue": 0.0, "cost": 0.0, "events": 0}
                bucket[name]["revenue"] += e.get("revenue", 0.0)
                bucket[name]["cost"] += e.get("cost", 0.0)
                bucket[name]["events"] += 1
            # compute net / roi per bucket entry after accumulation
        for bucket in (by_agent, by_skill):
            for v in bucket.values():
                v["net_profit"] = round(v["revenue"] - v["cost"], 4)
                v["roi_pct"] = (
                    round(v["net_profit"] / v["cost"] * 100.0, 2)
                    if v["cost"] > 0
                    else 0.0
                )

        return {
            "events": len(events),
            "total_revenue": round(total_revenue, 4),
            "total_cost": round(total_cost, 4),
            "net_profit": round(net_profit, 4),
            "roi_pct": round(roi_pct, 2),
            "by_agent": by_agent,
            "by_skill": by_skill,
        }

    def recent(self, n: int = 20) -> list[dict]:
        """Return the *n* most recent ROI events."""
        with self._lock:
            return _read_jsonl(self._log_file, n=n)


# ── Change Log ─────────────────────────────────────────────────────────────────


class ChangeLog:
    """Cross-session audit trail of autonomous decisions.

    Each entry captures *what* changed, *who* changed it, and — crucially —
    *why*, so the system remains interpretable after many self-improvement
    cycles.

    Each event record::

        {
          "ts":           "2026-04-10T08:00:00Z",
          "agent":        "ascend-forge",
          "action":       "patch_applied",
          "target":       "runtime/brain/brain.py",   # optional file / module
          "reason":       "Coverage gap found by /scan",
          "diff_summary": "Added null-check for reward=NaN",
          "session_id":   "abc123",                   # optional
          "approved_by":  "human"                     # optional
        }
    """

    def __init__(self, log_file: Path | None = None) -> None:
        self._log_file = log_file or _CHANGE_LOG_FILE
        self._lock = threading.Lock()

    def append(
        self,
        agent: str,
        action: str,
        reason: str,
        target: str = "",
        diff_summary: str = "",
        session_id: str = "",
        approved_by: str = "",
    ) -> dict:
        """Append one change event and return the recorded entry."""
        entry = {
            "ts": _now_iso(),
            "agent": agent,
            "action": action,
            "target": target,
            "reason": reason,
            "diff_summary": diff_summary,
            "session_id": session_id,
            "approved_by": approved_by,
        }
        with self._lock:
            _append_jsonl(self._log_file, entry)
        return entry

    def recent(self, n: int = 20, agent: str | None = None) -> list[dict]:
        """Return the *n* most recent change events, optionally filtered."""
        with self._lock:
            events = _read_jsonl(self._log_file, n=0)
        if agent:
            events = [e for e in events if e.get("agent") == agent]
        return events[-n:] if n > 0 else events

    def for_target(self, target: str) -> list[dict]:
        """Return all change events that touched *target* (file or module)."""
        with self._lock:
            events = _read_jsonl(self._log_file)
        return [e for e in events if e.get("target") == target]


# ── Agent introspection ────────────────────────────────────────────────────────


def _discover_agents(agents_dir: Path) -> dict[str, dict]:
    """Walk *agents_dir* and build a minimal metadata dict per agent.

    We look for:
    * A ``run.sh``   → agent is runnable
    * Any ``.py``    → collect module names
    * ``requirements.txt`` → note external dependencies exist
    """
    discovered: dict[str, dict] = {}
    if not agents_dir.is_dir():
        return discovered

    for item in sorted(agents_dir.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        if item.name in _INFRA_AGENTS:
            continue

        py_files = [f.name for f in item.glob("*.py")]
        has_run_sh = (item / "run.sh").exists()
        has_requirements_file = (item / "requirements.txt").exists()

        discovered[item.name] = {
            "path": str(item.relative_to(agents_dir.parent.parent)),
            "runnable": has_run_sh,
            "python_modules": py_files,
            "has_requirements_file": has_requirements_file,
        }
    return discovered


def _build_manifest(
    agents_dir: Path,
    skills_file: Path,
    caps_file: Path,
) -> dict:
    """Build the unified manifest dict."""
    # 1. Skills library
    skills_lib = _load_json(skills_file, {"skills": [], "categories": []})
    skills_by_id: dict[str, dict] = {
        s["id"]: s for s in skills_lib.get("skills", [])
    }

    # 2. Agent capabilities
    caps_data = _load_json(caps_file, {"agents": {}})
    caps_agents: dict[str, dict] = caps_data.get("agents", {})

    # 3. Filesystem introspection
    discovered = _discover_agents(agents_dir)

    # 4. Merge: filesystem ← capabilities ← discovery
    merged_agents: dict[str, dict] = {}
    # Start with all entries from capabilities file
    for agent_id, cap in caps_agents.items():
        merged_agents[agent_id] = {
            "id": agent_id,
            "description": cap.get("description", ""),
            "category": cap.get("category", "other"),
            "skills": cap.get("skills", []),
            "commands": cap.get("commands", []),
            "specialties": cap.get("specialties", []),
            "model_provider": cap.get("model_provider", ""),
            "model": cap.get("model", ""),
            "runnable": False,
            "python_modules": [],
            "has_requirements_file": False,
            "source": "capabilities",
        }
    # Overlay filesystem discovery (agents_dir uses dash-names; caps may use
    # either dash or underscore — normalise to dash)
    for fs_name, fs_meta in discovered.items():
        agent_id = fs_name  # agents_dir uses canonical dash-names
        if agent_id in merged_agents:
            merged_agents[agent_id].update({
                "runnable": fs_meta["runnable"],
                "python_modules": fs_meta["python_modules"],
                "has_requirements_file": fs_meta["has_requirements_file"],
                "path": fs_meta["path"],
                "source": "capabilities+filesystem",
            })
        else:
            merged_agents[agent_id] = {
                "id": agent_id,
                "description": "",
                "category": "other",
                "skills": [],
                "commands": [],
                "specialties": [],
                "model_provider": "",
                "model": "",
                "source": "filesystem",
                **fs_meta,
            }

    # 5. Identify missing gap areas from the audit
    all_skill_ids: set[str] = set()
    for agent in merged_agents.values():
        all_skill_ids.update(agent.get("skills", []))

    library_skill_ids = set(skills_by_id.keys())
    covered_skills = all_skill_ids & library_skill_ids
    gap_skills = library_skill_ids - all_skill_ids

    return {
        "_meta": {
            "version": "1.0",
            "generated_at": _now_iso(),
            "description": (
                "Unified skill registry manifest — agents × skills × capabilities. "
                "Auto-generated by runtime/core/skill_registry.py"
            ),
            "total_agents": len(merged_agents),
            "total_skills_library": len(library_skill_ids),
            "total_skills_covered": len(covered_skills),
            "total_skills_gap": len(gap_skills),
            "coverage_pct": (
                round(len(covered_skills) / len(library_skill_ids) * 100, 1)
                if library_skill_ids
                else 0.0
            ),
        },
        "agents": merged_agents,
        "skills": skills_by_id,
        "skill_categories": skills_lib.get("categories", []),
        "gap_skills": sorted(gap_skills),
    }


# ── SkillRegistry singleton ────────────────────────────────────────────────────


class SkillRegistry:
    """Central registry: manifest + Decision Engine + ROI Tracker + Change Log.

    Instantiate once via ``get_registry()``.  The manifest is built lazily on
    first access and cached in memory; call ``rebuild()`` to refresh.
    """

    def __init__(
        self,
        agents_dir: Path | None = None,
        skills_file: Path | None = None,
        caps_file: Path | None = None,
        manifest_file: Path | None = None,
        roi_log_file: Path | None = None,
        change_log_file: Path | None = None,
    ) -> None:
        self._agents_dir = agents_dir or _AGENTS_DIR
        self._skills_file = skills_file or _SKILLS_LIBRARY_FILE
        self._caps_file = caps_file or _AGENT_CAPS_FILE
        self._manifest_file = manifest_file or _MANIFEST_FILE
        self._manifest: dict | None = None
        self._lock = threading.Lock()

        self.decision_engine = DecisionEngine(self)
        self.roi_tracker = RoiTracker(roi_log_file)
        self.change_log = ChangeLog(change_log_file)

    # ── Manifest ──────────────────────────────────────────────────────────────

    @property
    def manifest(self) -> dict:
        with self._lock:
            if self._manifest is None:
                self._manifest = _build_manifest(
                    self._agents_dir, self._skills_file, self._caps_file
                )
        return self._manifest

    def rebuild(self) -> dict:
        """Force a full rebuild of the manifest from disk."""
        with self._lock:
            self._manifest = _build_manifest(
                self._agents_dir, self._skills_file, self._caps_file
            )
        return self._manifest

    def save_manifest(self, path: Path | None = None) -> Path:
        """Write the manifest JSON to *path* (default: manifest_file).

        Creates parent directories as needed.  Returns the path written.
        """
        out = path or self._manifest_file
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False))
        logger.info("skill_registry: manifest written → %s", out)
        return out

    # ── Convenience accessors ─────────────────────────────────────────────────

    def agents(self) -> dict[str, dict]:
        """Return all merged agents."""
        return self.manifest.get("agents", {})

    def skills(self) -> dict[str, dict]:
        """Return all skills, keyed by skill ID."""
        return self.manifest.get("skills", {})

    def gap_skills(self) -> list[str]:
        """Return skill IDs present in the library but not covered by any agent."""
        return self.manifest.get("gap_skills", [])

    def agent(self, agent_id: str) -> dict | None:
        """Return a single agent's merged metadata, or *None* if not found."""
        return self.manifest.get("agents", {}).get(agent_id)

    def skill(self, skill_id: str) -> dict | None:
        """Return a single skill's metadata, or *None* if not found."""
        return self.manifest.get("skills", {}).get(skill_id)

    def agents_for_skill(self, skill_id: str) -> list[str]:
        """Return agent IDs that list *skill_id* in their skills."""
        return [
            aid
            for aid, ameta in self.manifest.get("agents", {}).items()
            if skill_id in ameta.get("skills", [])
        ]

    def skills_for_agent(self, agent_id: str) -> list[str]:
        """Return skill IDs listed by *agent_id*."""
        return self.manifest.get("agents", {}).get(agent_id, {}).get("skills", [])

    def meta(self) -> dict:
        """Return the ``_meta`` section of the manifest."""
        return self.manifest.get("_meta", {})


# ── Module-level singleton ─────────────────────────────────────────────────────

_REGISTRY: SkillRegistry | None = None
_REGISTRY_LOCK = threading.Lock()


def get_registry(
    *,
    agents_dir: Path | None = None,
    skills_file: Path | None = None,
    caps_file: Path | None = None,
    manifest_file: Path | None = None,
    roi_log_file: Path | None = None,
    change_log_file: Path | None = None,
) -> SkillRegistry:
    """Return the module-level ``SkillRegistry`` singleton.

    On first call the registry is instantiated with the provided (or default)
    paths.  Subsequent calls return the cached singleton regardless of
    arguments.  Use ``SkillRegistry(...)`` directly if you need a fresh
    instance with custom paths (e.g. in tests).
    """
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = SkillRegistry(
                agents_dir=agents_dir,
                skills_file=skills_file,
                caps_file=caps_file,
                manifest_file=manifest_file,
                roi_log_file=roi_log_file,
                change_log_file=change_log_file,
            )
    return _REGISTRY


# ── CLI entry-point ────────────────────────────────────────────────────────────

def _cli_main() -> None:
    """Print a summary and write the manifest when run as a script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build and print the unified skill registry manifest."
    )
    parser.add_argument(
        "--save",
        metavar="PATH",
        help="Write manifest JSON to PATH (default: print to stdout only).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Print top-N agents ranked by Decision Engine score.",
    )
    args = parser.parse_args()

    reg = SkillRegistry()
    m = reg.manifest
    meta = m.get("_meta", {})
    print(
        f"Skill Registry  v{meta.get('version', '?')}  "
        f"generated {meta.get('generated_at', '?')}\n"
        f"  Agents   : {meta.get('total_agents', 0)}\n"
        f"  Skills   : {meta.get('total_skills_library', 0)} in library "
        f"({meta.get('total_skills_covered', 0)} covered, "
        f"{meta.get('total_skills_gap', 0)} gap)\n"
        f"  Coverage : {meta.get('coverage_pct', 0)}%"
    )

    print(f"\nTop-{args.top} agents by Decision Engine score:")
    for rank, entry in enumerate(reg.decision_engine.top(args.top), 1):
        print(
            f"  {rank:2}. {entry['agent_id']:<35} "
            f"composite={entry['composite']:.2f}  "
            f"({entry['recommendation']})"
        )

    if args.save:
        out = reg.save_manifest(Path(args.save))
        print(f"\nManifest written → {out}")
    else:
        print("\nUse --save <path> to write the full manifest JSON.")


if __name__ == "__main__":
    _cli_main()

"""Agent Learning Profile — coupling agents to learning ladders with grading.

Implements the AGENT_LEARNING_PROFILE system:

- Assigns a specific learning ladder (topic) to any agent
- Tracks each agent's grade (Ungraded → Beginner → Basic → Mature → Advanced → Pro)
  based on the number of ladder levels successfully completed
- On each level completion:
    1. Calls LearningLadderBuilder to record the milestone
    2. Saves every learned skill to MemoryIndex (brain/neural network)
    3. Records the task in LearningEngine for strategy reinforcement
    4. Boosts the agent's brain_model weights (reinforcement)
- Persists all profiles to state/agent_learning_profiles.json

Grade mapping (5 levels → 5 grades):

    Level completed  →  Grade
    ───────────────────────────
    0 (none)         →  Ungraded
    1                →  Beginner
    2                →  Basic
    3                →  Mature
    4                →  Advanced
    5 (all)          →  Pro

Usage::

    from core.agent_learning_profile import get_agent_learning_profile

    alp = get_agent_learning_profile()
    alp.assign_ladder("lead-hunter", "B2B Lead Generation")
    result = alp.advance(
        agent_id="lead-hunter",
        level=1,
        success=True,
        score=0.85,
        milestone_output="Built a cold outreach sequence",
    )
    grade = alp.get_agent_grade("lead-hunter")   # {"grade": "Beginner", ...}
    all_profiles = alp.get_all_profiles()
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_MAX_AGENTS = 500

# ── Grade system ───────────────────────────────────────────────────────────────

#: Maps highest completed level → grade label
GRADE_MAP: dict[int, str] = {
    0: "Ungraded",
    1: "Beginner",
    2: "Basic",
    3: "Mature",
    4: "Advanced",
    5: "Pro",
}

#: Maps grade label → numeric rank (for comparison)
GRADE_RANK: dict[str, int] = {v: k for k, v in GRADE_MAP.items()}

# Memory importance increases with level (higher = more important)
_MEMORY_IMPORTANCE_BASE = 0.60
_MEMORY_IMPORTANCE_PER_LEVEL = 0.06  # 0.06 per level → max 0.90 at level 5


# ── Utilities ──────────────────────────────────────────────────────────────────


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _agent_key(agent_id: str) -> str:
    return (agent_id or "").strip().lower()


def _state_path() -> Path:
    home = os.getenv("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[2]
    p = base / "state" / "agent_learning_profiles.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _compute_grade(levels_completed: int) -> str:
    return GRADE_MAP.get(min(max(int(levels_completed), 0), 5), "Ungraded")


# ── Default state ──────────────────────────────────────────────────────────────

def _default_state() -> dict[str, Any]:
    return {
        "assignments": {},   # agent_key → {topic, assigned_at, ladder_id}
        "grades": {},        # agent_key → {grade, grade_level, topic, levels_completed, last_updated}
        "metrics": {
            "total_agents_assigned": 0,
            "total_levels_completed": 0,
            "total_levels_failed": 0,
        },
        "updated_at": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AgentLearningProfile
# ══════════════════════════════════════════════════════════════════════════════


class AgentLearningProfile:
    """Couples agents to learning ladders and manages grade progression.

    On each successful level completion the module:
    - Updates the agent's grade in persistent state
    - Commits learned skills to MemoryIndex
    - Records the task in LearningEngine
    - Reinforces the agent's brain_model weights
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _state_path()
        self._state = self._load()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                base = _default_state()
                base.update(payload)
                return base
        except Exception:
            pass
        state = _default_state()
        self._save(state)
        return state

    def _save(self, state: dict[str, Any] | None = None) -> None:
        data = state if state is not None else self._state
        data["updated_at"] = _ts()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Public API ─────────────────────────────────────────────────────────────

    def assign_ladder(self, agent_id: str, topic: str) -> dict[str, Any]:
        """Assign a learning ladder topic to an agent and build the ladder.

        If the agent already has an assignment for a different topic, the old
        assignment is replaced (grade progress is preserved in the ladder module).

        Args:
            agent_id: Agent identifier (e.g., "lead-hunter").
            topic:    Learning ladder topic (e.g., "B2B Lead Generation").

        Returns:
            Dict with agent_id, topic, ladder_id, grade, assigned_at.
        """
        agent_id = (agent_id or "").strip()
        topic = (topic or "").strip()
        if not agent_id:
            raise ValueError("agent_id must be a non-empty string")
        if not topic:
            raise ValueError("topic must be a non-empty string")

        key = _agent_key(agent_id)

        # Build the ladder (cached if already built)
        from core.learning_ladder_builder import get_learning_ladder_builder
        builder = get_learning_ladder_builder()
        ladder = builder.build_ladder(topic)

        with _LOCK:
            assignments = self._state["assignments"]
            if len(assignments) >= _MAX_AGENTS and key not in assignments:
                # Evict the oldest assignment
                oldest = next(iter(assignments))
                del assignments[oldest]

            assignments[key] = {
                "agent_id": agent_id,
                "topic": topic,
                "ladder_id": ladder["id"],
                "assigned_at": _ts(),
            }

            # Initialise grade record if absent
            grades = self._state["grades"]
            if key not in grades:
                grades[key] = {
                    "agent_id": agent_id,
                    "topic": topic,
                    "grade": "Ungraded",
                    "grade_level": 0,
                    "levels_completed": 0,
                    "last_updated": _ts(),
                }
            else:
                # Keep grade but update topic pointer if reassigned
                grades[key]["topic"] = topic

            self._state["metrics"]["total_agents_assigned"] = (
                int(self._state["metrics"].get("total_agents_assigned", 0)) + 1
            )
            self._save()

            return {
                "agent_id": agent_id,
                "topic": topic,
                "ladder_id": ladder["id"],
                "grade": grades[key]["grade"],
                "assigned_at": assignments[key]["assigned_at"],
            }

    def advance(
        self,
        *,
        agent_id: str,
        level: int,
        success: bool,
        score: float = 0.0,
        milestone_output: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Record a level completion attempt for an agent.

        Enforces the anti-illusion protocol from LearningLadderBuilder
        (success=True + score≥0.5 required to be marked LEARNED).

        On success also:
        - Stores learned skills in MemoryIndex (brain)
        - Reinforces agent in LearningEngine
        - Boosts brain_model weights

        Args:
            agent_id:         Agent identifier.
            level:            Level number 1–5.
            success:          Whether the milestone was completed.
            score:            Quality score [0, 1].
            milestone_output: Text describing what was produced.
            notes:            Skill gaps or additional notes.

        Returns:
            Dict with result, grade, adaptation, brain_stored.
        """
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise ValueError("agent_id must be a non-empty string")
        if level not in range(1, 6):
            raise ValueError(f"level must be 1–5, got {level}")

        key = _agent_key(agent_id)

        with _LOCK:
            assignment = self._state["assignments"].get(key)
            if not assignment:
                raise KeyError(
                    f"Agent '{agent_id}' has no learning ladder assigned. "
                    "Call assign_ladder() first."
                )
            topic = assignment["topic"]

        # Delegate completion recording to LearningLadderBuilder
        from core.learning_ladder_builder import get_learning_ladder_builder
        builder = get_learning_ladder_builder()
        result = builder.record_level_completion(
            topic=topic,
            level=level,
            success=success,
            milestone_output=milestone_output,
            score=score,
            notes=notes,
        )

        learned = result["learned"]
        brain_stored = False

        if learned:
            # ── Brain integration ─────────────────────────────────────────────
            brain_stored = self._integrate_brain(
                agent_id=agent_id,
                topic=topic,
                level=level,
                score=score,
                milestone_output=milestone_output,
            )

            # ── Update grade ──────────────────────────────────────────────────
            with _LOCK:
                grade_rec = self._state["grades"].setdefault(
                    key,
                    {
                        "agent_id": agent_id,
                        "topic": topic,
                        "grade": "Ungraded",
                        "grade_level": 0,
                        "levels_completed": 0,
                        "last_updated": _ts(),
                    },
                )
                # Grade = highest completed level
                current_level = int(grade_rec.get("grade_level", 0))
                if level > current_level:
                    grade_rec["grade_level"] = level
                    grade_rec["grade"] = _compute_grade(level)
                grade_rec["levels_completed"] = max(
                    int(grade_rec.get("levels_completed", 0)), level
                )
                grade_rec["last_updated"] = _ts()

                self._state["metrics"]["total_levels_completed"] = (
                    int(self._state["metrics"].get("total_levels_completed", 0)) + 1
                )
                self._save()
        else:
            with _LOCK:
                self._state["metrics"]["total_levels_failed"] = (
                    int(self._state["metrics"].get("total_levels_failed", 0)) + 1
                )
                self._save()

        grade_info = self.get_agent_grade(agent_id)

        return {
            "agent_id": agent_id,
            "topic": topic,
            "level": level,
            "learned": learned,
            "status": result["status"],
            "grade": grade_info["grade"],
            "grade_level": grade_info["grade_level"],
            "next_level": result.get("next_level"),
            "adaptation": result.get("adaptation"),
            "brain_stored": brain_stored,
        }

    def get_agent_grade(self, agent_id: str) -> dict[str, Any]:
        """Return the current grade record for an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Dict with agent_id, topic, grade, grade_level, levels_completed.
            Returns Ungraded if no assignment exists.
        """
        key = _agent_key(agent_id)
        with _LOCK:
            grades = self._state["grades"]
            if key not in grades:
                return {
                    "agent_id": (agent_id or "").strip(),
                    "topic": None,
                    "grade": "Ungraded",
                    "grade_level": 0,
                    "levels_completed": 0,
                    "last_updated": None,
                }
            return dict(grades[key])

    def get_agent_profile(self, agent_id: str) -> dict[str, Any]:
        """Return the full learning profile for an agent.

        Includes the assignment, grade, ladder, and progress.

        Args:
            agent_id: Agent identifier.

        Returns:
            Dict with agent_id, assignment, grade, ladder_progress, next_level.
        """
        key = _agent_key(agent_id)
        with _LOCK:
            assignment = dict(self._state["assignments"].get(key) or {})
            grade = dict(self._state["grades"].get(key) or {})

        if not assignment:
            return {
                "agent_id": (agent_id or "").strip(),
                "assignment": None,
                "grade": "Ungraded",
                "grade_level": 0,
                "ladder_progress": None,
                "next_level": None,
            }

        from core.learning_ladder_builder import get_learning_ladder_builder
        builder = get_learning_ladder_builder()
        ladder_progress = builder.get_progress(assignment.get("topic", ""))

        return {
            "agent_id": (agent_id or "").strip(),
            "assignment": assignment,
            "grade": grade.get("grade", "Ungraded"),
            "grade_level": grade.get("grade_level", 0),
            "ladder_progress": ladder_progress,
            "next_level": ladder_progress.get("next_level"),
        }

    def get_all_profiles(self) -> list[dict[str, Any]]:
        """Return grade summaries for all agents with a ladder assignment."""
        with _LOCK:
            result = []
            for key, assignment in self._state["assignments"].items():
                grade_rec = self._state["grades"].get(key, {})
                result.append({
                    "agent_id": assignment.get("agent_id", key),
                    "topic": assignment.get("topic", ""),
                    "ladder_id": assignment.get("ladder_id", ""),
                    "grade": grade_rec.get("grade", "Ungraded"),
                    "grade_level": grade_rec.get("grade_level", 0),
                    "levels_completed": grade_rec.get("levels_completed", 0),
                    "levels_total": 5,
                    "last_updated": grade_rec.get("last_updated"),
                })
            return sorted(
                result,
                key=lambda x: (x["grade_level"], x.get("last_updated") or ""),
                reverse=True,
            )

    def metrics(self) -> dict[str, Any]:
        """Return global agent learning metrics."""
        with _LOCK:
            m = dict(self._state["metrics"])
            m["total_agents_assigned"] = len(self._state["assignments"])
            m["grade_distribution"] = self._grade_distribution()
            m["ts"] = _ts()
            return m

    # ── Brain integration ──────────────────────────────────────────────────────

    def _integrate_brain(
        self,
        *,
        agent_id: str,
        topic: str,
        level: int,
        score: float,
        milestone_output: str,
    ) -> bool:
        """Persist learned knowledge to MemoryIndex and reinforce brain_model.

        Returns True if any brain store was updated.
        """
        stored = False
        importance = min(
            _MEMORY_IMPORTANCE_BASE + (_MEMORY_IMPORTANCE_PER_LEVEL * level), 0.95
        )
        grade = _compute_grade(level)

        # Pull level skills from the ladder
        skills: list[str] = []
        try:
            from core.learning_ladder_builder import get_learning_ladder_builder
            builder = get_learning_ladder_builder()
            ladder = builder.get_ladder(topic)
            if ladder:
                level_data = next(
                    (lv for lv in ladder.get("levels", []) if lv["level"] == level), None
                )
                if level_data:
                    skills = level_data.get("skills", [])
        except Exception:
            pass

        # 1. Add each learned skill to MemoryIndex
        try:
            from core.memory_index import get_memory_index
            memory = get_memory_index()
            # Store a summary memory for the level completion
            summary = (
                f"[Agent:{agent_id}] Achieved grade '{grade}' on topic '{topic}' "
                f"(Level {level}, score={score:.2f}). "
                f"Milestone: {(milestone_output or '').strip()[:200]}"
            )
            memory.add_memory(summary, importance=importance)
            # Store each skill individually for fine-grained retrieval
            for skill in skills:
                skill_mem = f"[Agent:{agent_id}] Skill learned: {skill} ({topic} Level {level})"
                memory.add_memory(skill_mem, importance=importance * 0.9)
            stored = True
        except Exception:
            pass  # non-fatal — brain integration is best-effort

        # 2. Record in LearningEngine
        try:
            from core.learning_engine import get_learning_engine
            engine = get_learning_engine()
            engine.record_task(
                task_input=f"learn {topic} level {level}",
                chosen_agent=agent_id,
                strategy_used=f"learning_ladder:{topic}:level{level}",
                result={"milestone_output": milestone_output, "score": score},
                success_score=score,
                decision_reason=f"Learning ladder progression: {grade} on {topic}",
                memories_used=[],
            )
            stored = True
        except Exception:
            pass  # non-fatal

        # 3. Reinforce brain_model weights for the agent
        try:
            from core.brain_model import update_agent_model
            reward = round(0.1 * level * score, 4)
            update_agent_model(agent_id, reward)
            stored = True
        except Exception:
            pass  # brain_model only knows 6 agents; others are silently skipped

        return stored

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _grade_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {g: 0 for g in GRADE_MAP.values()}
        for rec in self._state["grades"].values():
            grade = rec.get("grade", "Ungraded")
            dist[grade] = dist.get(grade, 0) + 1
        return dist


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: AgentLearningProfile | None = None
_instance_lock = threading.Lock()


def get_agent_learning_profile(path: Path | None = None) -> AgentLearningProfile:
    """Return the process-wide AgentLearningProfile singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AgentLearningProfile(path)
        elif path is not None and _instance._path != path:
            _instance = AgentLearningProfile(path)
    return _instance

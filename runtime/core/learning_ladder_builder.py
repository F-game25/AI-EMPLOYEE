"""Learning Ladder Builder — structured 5-level progression module.

SYSTEM MODULE: LEARNING_LADDER_BUILDER

Decomposes any topic into a structured 5-level learning ladder and enforces
progression-based learning with memory integration and adaptive intelligence.

Anti-Illusion Protocol:
- If the system "explains" but cannot "do", mark as NOT LEARNED
- If milestone cannot be completed autonomously, downgrade level
- Prioritize execution over theory at all times

Usage::

    from core.learning_ladder_builder import get_learning_ladder_builder

    builder = get_learning_ladder_builder()
    ladder = builder.build_ladder("Python programming")
    builder.record_level_completion(
        topic="Python programming",
        level=1,
        success=True,
        milestone_output="Completed hello-world script",
        score=0.9,
    )
    progress = builder.get_progress("Python programming")
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()

_MAX_HISTORY_PER_TOPIC = 50
_MAX_TOPICS = 200

# ── Level templates ────────────────────────────────────────────────────────────

_LEVEL_TEMPLATES: dict[int, dict[str, Any]] = {
    1: {
        "name": "Beginner",
        "description": (
            "Understands the fundamental concepts of {topic}. "
            "Can identify basic terminology and follow simple examples with guidance."
        ),
        "skills": [
            "Define core terms and concepts of {topic}",
            "Identify the primary components and elements in {topic}",
            "Follow a step-by-step tutorial to produce a basic {topic} output",
        ],
        "milestone": (
            "Complete a beginner-level guided exercise: build or produce a minimal "
            "working example of {topic} from a tutorial, then explain what each step does."
        ),
    },
    2: {
        "name": "Basic",
        "description": (
            "Can independently perform basic {topic} tasks without constant guidance. "
            "Understands the 'why' behind foundational concepts."
        ),
        "skills": [
            "Independently set up and configure a {topic} environment or workflow",
            "Apply core {topic} techniques to simple, well-defined problems",
            "Debug common beginner-level {topic} errors",
            "Read and understand basic {topic} documentation",
        ],
        "milestone": (
            "Build a simple standalone {topic} project from scratch (no tutorial) that "
            "solves a basic real-world problem. Include error handling and basic documentation."
        ),
    },
    3: {
        "name": "Mature",
        "description": (
            "Solves moderately complex {topic} problems independently. "
            "Understands trade-offs and begins to apply best practices."
        ),
        "skills": [
            "Design and implement a multi-component {topic} system",
            "Apply best practices and design patterns relevant to {topic}",
            "Optimise {topic} solutions for performance or maintainability",
            "Integrate {topic} with other tools, systems, or frameworks",
            "Test and validate {topic} implementations",
        ],
        "milestone": (
            "Design, implement, and test a complete mature-level {topic} application "
            "that integrates with at least one external tool or data source. "
            "Document the architecture and key decisions."
        ),
    },
    4: {
        "name": "Advanced",
        "description": (
            "Handles complex, production-grade {topic} challenges. "
            "Can architect systems, mentor others, and make informed technical decisions."
        ),
        "skills": [
            "Architect scalable and maintainable {topic} systems",
            "Identify and resolve advanced performance or security issues in {topic}",
            "Evaluate and select appropriate {topic} tools/frameworks for specific contexts",
            "Contribute to or extend {topic} ecosystems (libraries, plugins, or tools)",
        ],
        "milestone": (
            "Architect and deploy a production-ready {topic} solution that handles "
            "real-world constraints (scale, security, reliability). Write a technical design "
            "document explaining key decisions and trade-offs."
        ),
    },
    5: {
        "name": "Pro",
        "description": (
            "Expert-level mastery of {topic}. Can innovate, define standards, lead teams, "
            "and solve novel problems autonomously in {topic}."
        ),
        "skills": [
            "Define and enforce {topic} standards and best practices across a team or organisation",
            "Innovate and solve novel, unseen problems in {topic} without reference material",
            "Mentor and grow others' {topic} capabilities",
            "Contribute original knowledge to the {topic} community (publications, open-source, talks)",
            "Evaluate and drive adoption of emerging {topic} technologies or methodologies",
        ],
        "milestone": (
            "Lead a complex {topic} initiative end-to-end: define the problem, architect the "
            "solution, execute with a team, deliver measurable outcomes, and document learnings "
            "for future reference. Present results to stakeholders."
        ),
    },
}

_LEVEL_NAMES = {
    1: "Beginner",
    2: "Basic",
    3: "Mature",
    4: "Advanced",
    5: "Pro",
}

# ── Utilities ──────────────────────────────────────────────────────────────────


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _topic_key(topic: str) -> str:
    """Normalised key for a topic (lower-case, stripped)."""
    return topic.strip().lower()


def _state_path() -> Path:
    home = os.getenv("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[2]
    p = base / "state" / "learning_ladder.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _render_template(template: str, topic: str) -> str:
    return template.replace("{topic}", topic)


def _build_level(topic: str, level_num: int) -> dict[str, Any]:
    tmpl = _LEVEL_TEMPLATES[level_num]
    return {
        "level": level_num,
        "name": tmpl["name"],
        "description": _render_template(tmpl["description"], topic),
        "skills": [_render_template(s, topic) for s in tmpl["skills"]],
        "milestone": _render_template(tmpl["milestone"], topic),
    }


def _ladder_id(topic: str) -> str:
    return hashlib.sha1(topic.strip().encode()).hexdigest()[:12]


# ── Default state ──────────────────────────────────────────────────────────────

_DEFAULT_STATE: dict[str, Any] = {
    "ladders": {},    # topic_key → built ladder JSON
    "progress": {},   # topic_key → per-level completion records
    "metrics": {
        "total_ladders_built": 0,
        "total_levels_completed": 0,
        "total_levels_failed": 0,
        "total_levels_attempted": 0,
    },
    "updated_at": None,
}


# ══════════════════════════════════════════════════════════════════════════════
# LearningLadderBuilder
# ══════════════════════════════════════════════════════════════════════════════


class LearningLadderBuilder:
    """Structured 5-level learning progression engine.

    Responsibilities
    ----------------
    - Build topic-specific 5-level learning ladders
    - Enforce prerequisite gating (cannot advance without prior milestone)
    - Record completions, failures, and skill gaps
    - Adapt ladders via sub-levels on repeated failure or skip on rapid success
    - Persist all state for future sessions
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _state_path()
        self._state = self._load()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                merged: dict[str, Any] = {
                    "ladders": {},
                    "progress": {},
                    "metrics": dict(_DEFAULT_STATE["metrics"]),
                    "updated_at": None,
                }
                merged.update(payload)
                return merged
        except Exception:
            pass
        self._save(dict(_DEFAULT_STATE))
        return {
            "ladders": {},
            "progress": {},
            "metrics": dict(_DEFAULT_STATE["metrics"]),
            "updated_at": None,
        }

    def _save(self, state: dict[str, Any] | None = None) -> None:
        data = state if state is not None else self._state
        data["updated_at"] = _ts()
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Public API ─────────────────────────────────────────────────────────────

    def build_ladder(self, topic: str) -> dict[str, Any]:
        """Build and return a 5-level learning ladder for *topic*.

        Returns the JSON structure specified by the module contract.
        Stores the ladder in persistent state so future queries can retrieve it.

        Args:
            topic: The topic, skill, or domain to decompose.

        Returns:
            A dict with keys ``topic`` and ``levels`` (list of 5 level dicts).
        """
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("topic must be a non-empty string")

        key = _topic_key(topic)

        with _LOCK:
            # Return cached ladder if the topic has been built before
            if key in self._state["ladders"]:
                return dict(self._state["ladders"][key])

            levels = [_build_level(topic, n) for n in range(1, 6)]
            ladder: dict[str, Any] = {
                "id": _ladder_id(topic),
                "topic": topic,
                "levels": levels,
                "built_at": _ts(),
            }

            # Enforce max stored topics (evict oldest if needed)
            ladders = self._state["ladders"]
            if len(ladders) >= _MAX_TOPICS:
                oldest_key = next(iter(ladders))
                del ladders[oldest_key]

            ladders[key] = ladder
            self._state["metrics"]["total_ladders_built"] = (
                int(self._state["metrics"].get("total_ladders_built", 0)) + 1
            )
            self._save()
            return dict(ladder)

    def get_ladder(self, topic: str) -> dict[str, Any] | None:
        """Return a previously built ladder, or *None* if not found."""
        key = _topic_key(topic)
        with _LOCK:
            return dict(self._state["ladders"][key]) if key in self._state["ladders"] else None

    def record_level_completion(
        self,
        *,
        topic: str,
        level: int,
        success: bool,
        milestone_output: str = "",
        score: float = 0.0,
        notes: str = "",
    ) -> dict[str, Any]:
        """Record an attempt at completing a level milestone.

        Anti-illusion protocol is enforced here:
        - If ``success=False``, the level is NOT marked learned.
        - Score below 0.5 is treated as partial failure.

        Args:
            topic:            Topic name.
            level:            Level number (1–5).
            success:          Whether the milestone was completed autonomously.
            milestone_output: Text description of what was produced.
            score:            Quality score in [0, 1].
            notes:            Additional notes or skill gaps observed.

        Returns:
            A dict with completion record and updated progression state.
        """
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("topic must be a non-empty string")
        if level not in range(1, 6):
            raise ValueError(f"level must be 1–5, got {level}")

        key = _topic_key(topic)
        score = max(0.0, min(1.0, float(score)))
        learned = success and score >= 0.5  # anti-illusion gate

        with _LOCK:
            progress = self._state["progress"].setdefault(key, {})
            level_str = str(level)
            level_progress = progress.setdefault(
                level_str,
                {
                    "level": level,
                    "name": _LEVEL_NAMES[level],
                    "status": "not_started",
                    "attempts": [],
                    "completed_at": None,
                    "learned": False,
                    "best_score": 0.0,
                    "skill_gaps": [],
                },
            )

            attempt = {
                "ts": _ts(),
                "success": success,
                "learned": learned,
                "score": round(score, 4),
                "milestone_output": (milestone_output or "")[:500],
                "notes": (notes or "")[:300],
            }

            attempts = list(level_progress.get("attempts", []))
            attempts.append(attempt)
            # Keep last N attempts per level
            level_progress["attempts"] = attempts[-_MAX_HISTORY_PER_TOPIC:]

            if learned:
                level_progress["status"] = "completed"
                level_progress["learned"] = True
                level_progress["completed_at"] = _ts()
                level_progress["best_score"] = max(
                    float(level_progress.get("best_score", 0.0)), score
                )
                self._state["metrics"]["total_levels_completed"] = (
                    int(self._state["metrics"].get("total_levels_completed", 0)) + 1
                )
            else:
                # Downgrade: mark level as failed if not previously completed
                if level_progress.get("status") != "completed":
                    level_progress["status"] = "failed"
                    level_progress["learned"] = False
                # Record skill gap from notes
                if notes and notes not in level_progress.get("skill_gaps", []):
                    gaps = list(level_progress.get("skill_gaps", []))
                    gaps.append(notes[:200])
                    level_progress["skill_gaps"] = gaps[-10:]
                self._state["metrics"]["total_levels_failed"] = (
                    int(self._state["metrics"].get("total_levels_failed", 0)) + 1
                )

            self._state["metrics"]["total_levels_attempted"] = (
                int(self._state["metrics"].get("total_levels_attempted", 0)) + 1
            )

            self._save()

            return {
                "topic": topic,
                "level": level,
                "learned": learned,
                "status": level_progress["status"],
                "attempts_count": len(level_progress["attempts"]),
                "best_score": level_progress["best_score"],
                "next_level": self._next_executable_level(key),
                "adaptation": self._check_adaptation(key, level, attempts),
            }

    def get_progress(self, topic: str) -> dict[str, Any]:
        """Return full progress record for *topic*.

        Returns:
            A dict with:
            - ``topic``        — original topic string
            - ``ladder``       — the built ladder (if any)
            - ``progress``     — per-level status records
            - ``next_level``   — the next level ready for execution (1–5 or None)
            - ``completed``    — True if all 5 levels learned
        """
        key = _topic_key(topic)
        with _LOCK:
            ladder = self._state["ladders"].get(key)
            progress = self._state["progress"].get(key, {})
            next_lvl = self._next_executable_level(key)
            all_done = all(
                progress.get(str(n), {}).get("learned", False) for n in range(1, 6)
            )
            return {
                "topic": topic,
                "ladder": dict(ladder) if ladder else None,
                "progress": dict(progress),
                "next_level": next_lvl,
                "completed": all_done,
            }

    def get_all_topics(self) -> list[dict[str, Any]]:
        """Return a summary of all topics tracked by this builder."""
        with _LOCK:
            result = []
            for key, ladder in self._state["ladders"].items():
                progress = self._state["progress"].get(key, {})
                completed_levels = sum(
                    1 for n in range(1, 6) if progress.get(str(n), {}).get("learned", False)
                )
                result.append({
                    "topic": ladder.get("topic", key),
                    "id": ladder.get("id", key),
                    "built_at": ladder.get("built_at"),
                    "levels_completed": completed_levels,
                    "levels_total": 5,
                    "completed": completed_levels == 5,
                })
            return sorted(result, key=lambda x: x.get("built_at") or "", reverse=True)

    def metrics(self) -> dict[str, Any]:
        """Return global learning ladder metrics."""
        with _LOCK:
            m = dict(self._state["metrics"])
            m["total_topics"] = len(self._state["ladders"])
            m["ts"] = _ts()
            return m

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _next_executable_level(self, topic_key: str) -> int | None:
        """Return the next level (1–5) that can be attempted, or None if all done."""
        progress = self._state["progress"].get(topic_key, {})
        for n in range(1, 6):
            level_rec = progress.get(str(n), {})
            if not level_rec.get("learned", False):
                # Cannot execute level N unless level N-1 is learned
                if n == 1 or progress.get(str(n - 1), {}).get("learned", False):
                    return n
                return None  # Blocked by prior level not completed
        return None  # All levels complete

    def _check_adaptation(
        self, topic_key: str, level: int, attempts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Determine adaptive action based on attempt history.

        - Repeated failure (≥3 failures) → suggest sub-levels
        - Rapid success (1st attempt, high score) → suggest skipping next level review

        Returns:
            A dict with keys ``action`` and ``reason``.
        """
        failures = sum(1 for a in attempts if not a.get("learned", False))
        successes = [a for a in attempts if a.get("learned", False)]

        if failures >= 3:
            return {
                "action": "break_into_sub_levels",
                "reason": (
                    f"Level {level} failed {failures} times. "
                    "Breaking into sub-levels for simplified progression."
                ),
            }

        if len(successes) == 1 and len(attempts) == 1 and successes[0].get("score", 0) >= 0.9:
            return {
                "action": "accelerate_progression",
                "reason": (
                    f"Level {level} completed on first attempt with high score. "
                    "Accelerating to next level."
                ),
            }

        return {"action": "continue", "reason": "Normal progression."}


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: LearningLadderBuilder | None = None
_instance_lock = threading.Lock()


def get_learning_ladder_builder(path: Path | None = None) -> LearningLadderBuilder:
    """Return the process-wide LearningLadderBuilder singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = LearningLadderBuilder(path)
        elif path is not None and _instance._path != path:
            _instance = LearningLadderBuilder(path)
    return _instance

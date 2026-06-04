"""Swarm Engine — generieke multi-agent consensus voor het AI Employee systeem.

Architectuur: N parallelle "swarm agents" denken onafhankelijk over een probleem,
vormen vervolgens consensus via belief-propagation (gebaseerd op MiroFish), en
leveren één antwoord met confidence-score.

Gebruik:
    from core.swarm_engine import SwarmEngine, SwarmTask

    engine = SwarmEngine(n_agents=5, model="qwen2.5-coder:14b")
    result = await engine.run(SwarmTask(
        goal="Refactor deze functie naar async",
        context="...",
        task_type="code",
    ))
    # result.answer   — beste antwoord
    # result.confidence — 0-1
    # result.dissent  — afwijkende meningen van minority-agents

Toepassingen:
    - AscendForge: parallelle code-generatie → beste patch kiezen
    - Pitch-generator: meerdere pitch-varianten → sterkste kiezen
    - Bedrijf-research: meerdere zoekstrategieën → rijkste data
    - Beslissingen: risicobeoordeling via consensus
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_DEFAULT_MODEL = os.environ.get("SWARM_MODEL") or os.environ.get("OLLAMA_MODEL", "llama3:latest")
_CODE_MODEL   = os.environ.get("FORGE_OLLAMA_MODEL") or os.environ.get("OLLAMA_CODE_MODEL", "qwen2.5-coder:14b")
_MAX_WORKERS  = int(os.environ.get("SWARM_MAX_WORKERS", "8"))

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class SwarmTask:
    goal: str
    context: str = ""
    task_type: str = "general"   # "code" | "analysis" | "pitch" | "general"
    n_agents: int = 0            # 0 = auto (3 for general, 5 for code)
    timeout_s: float = 120.0
    require_json: bool = False
    diversity_prompt: bool = True  # give each agent a slightly different angle


@dataclass
class AgentVote:
    agent_id: int
    answer: str
    confidence: float    # self-reported 0-1
    reasoning: str = ""
    duration_ms: int = 0
    model: str = ""


@dataclass
class SwarmResult:
    answer: str                      # consensus best answer
    confidence: float                # 0-1, agreement-weighted
    votes: list[AgentVote] = field(default_factory=list)
    dissent: list[str] = field(default_factory=list)  # minority answers
    winner_agent: int = 0
    n_agents: int = 0
    duration_ms: int = 0
    provider: str = "ollama"


# ── Swarm belief propagation ──────────────────────────────────────────────────

class _BeliefAgent:
    """Lightweight belief agent — tracks confidence and shifts toward consensus."""
    __slots__ = ("agent_id", "confidence", "herd_tendency", "expertise")

    def __init__(self, agent_id: int, rng: random.Random) -> None:
        self.agent_id = agent_id
        self.confidence = rng.uniform(0.4, 0.9)
        self.herd_tendency = rng.uniform(0.15, 0.6)
        self.expertise = rng.uniform(0.5, 1.0)

    def update(self, own_signal: float, crowd_mean: float, rng: random.Random) -> None:
        noise = rng.gauss(0, (1 - self.expertise) * 0.05)
        blended = (1 - self.herd_tendency) * own_signal + self.herd_tendency * crowd_mean
        self.confidence = max(0.05, min(0.99, blended + noise))


def _propagate_beliefs(votes: list[AgentVote], rounds: int = 5) -> list[float]:
    """Run belief propagation over agent votes. Returns updated confidence per agent."""
    if not votes:
        return []
    rng = random.Random(sum(v.agent_id for v in votes))
    agents = [_BeliefAgent(v.agent_id, rng) for v in votes]
    signals = [v.confidence for v in votes]

    for _ in range(rounds):
        crowd = sum(a.confidence for a in agents) / len(agents)
        for i, a in enumerate(agents):
            a.update(signals[i], crowd, rng)

    return [a.confidence for a in agents]


# ── LLM call (synchronous, runs in thread pool) ───────────────────────────────

def _call_ollama_sync(prompt: str, model: str, timeout_s: float) -> tuple[str, str]:
    """Returns (response_text, model_used). Raises on failure."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.7},
    }).encode()
    req = urllib.request.Request(
        f"{_OLLAMA_HOST}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosec B310
        body = json.loads(resp.read())
    return body.get("response", "").strip(), model


def _try_claude_sync(prompt: str, model: str, timeout_s: float) -> tuple[str, str] | None:
    """Try Claude API as fallback. Returns None if not configured."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    try:
        from anthropic import Anthropic  # type: ignore
        client = Anthropic(api_key=key)
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout_s,
        )
        return resp.content[0].text, model
    except Exception as exc:
        logger.debug("swarm_engine: Claude fallback failed: %s", exc)
        return None


def _call_llm_sync(prompt: str, model: str, timeout_s: float) -> tuple[str, str]:
    """Try Ollama first, then Claude. Raises if both fail."""
    try:
        return _call_ollama_sync(prompt, model, timeout_s)
    except Exception as ollama_err:
        logger.debug("swarm_engine: Ollama failed (%s), trying Claude", ollama_err)
        claude = _try_claude_sync(prompt, os.environ.get("FORGE_CLAUDE_MODEL", "claude-sonnet-4-6"), timeout_s)
        if claude:
            return claude
        raise RuntimeError(f"All LLM providers failed. Last Ollama error: {ollama_err}") from ollama_err


# ── Prompt builders ───────────────────────────────────────────────────────────

_ANGLE_ADJECTIVES = [
    "conservative and safe",
    "creative and experimental",
    "performance-focused",
    "minimal and elegant",
    "defensive and security-conscious",
    "pragmatic and maintainable",
    "user-experience-focused",
    "test-driven",
]

_TASK_SYSTEM: dict[str, str] = {
    "code": (
        "You are a senior software engineer. Produce clean, working code. "
        "Wrap code in triple-backtick fences with the language tag. "
        "After the code, write one sentence explaining your approach."
    ),
    "analysis": (
        "You are a senior business analyst. Give structured, evidence-based analysis. "
        "Use bullet points for key findings. End with a clear recommendation."
    ),
    "pitch": (
        "You are a professional Dutch copywriter specializing in website sales. "
        "Write persuasive, personal, and concrete pitches. Never generic."
    ),
    "general": (
        "You are a highly capable AI assistant. Be concise, accurate, and helpful."
    ),
}


def _build_agent_prompt(task: SwarmTask, agent_id: int, n_agents: int) -> str:
    system = _TASK_SYSTEM.get(task.task_type, _TASK_SYSTEM["general"])
    angle = ""
    if task.diversity_prompt and n_agents > 1:
        adj = _ANGLE_ADJECTIVES[agent_id % len(_ANGLE_ADJECTIVES)]
        angle = f"\nApproach this from a {adj} perspective.\n"

    confidence_instruction = (
        "\n\nAfter your answer, on the last line write exactly:\n"
        "CONFIDENCE: 0.X\n"
        "(a number from 0.1 to 0.99 representing how confident you are)"
    )

    parts = [system, angle]
    if task.context:
        parts.append(f"\nContext:\n{task.context}")
    parts.append(f"\nTask:\n{task.goal}")
    parts.append(confidence_instruction)
    return "\n".join(p for p in parts if p)


def _parse_confidence(text: str) -> float:
    """Extract CONFIDENCE: X.XX from end of response."""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.upper().startswith("CONFIDENCE:"):
            try:
                return max(0.05, min(0.99, float(line.split(":", 1)[1].strip())))
            except ValueError:
                pass
    return 0.5  # default if not reported


def _strip_confidence_line(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[-1].strip().upper().startswith("CONFIDENCE:"):
        return "\n".join(lines[:-1]).strip()
    return text.strip()


# ── Core engine ───────────────────────────────────────────────────────────────

class SwarmEngine:
    """Run N agents in parallel, propagate beliefs, return consensus answer.

    Usage:
        engine = SwarmEngine()
        result = engine.run_sync(task)      # blocking
        result = await engine.run(task)     # async
    """

    def __init__(
        self,
        n_agents: int = 0,
        model: str = "",
        max_workers: int = _MAX_WORKERS,
    ) -> None:
        self.default_n_agents = n_agents or 3
        self.default_model = model or _DEFAULT_MODEL
        self.max_workers = max_workers

    def _resolve_config(self, task: SwarmTask) -> tuple[int, str]:
        n = task.n_agents or self.default_n_agents
        if task.task_type == "code":
            n = task.n_agents or 5
            model = _CODE_MODEL
        elif task.task_type in ("analysis", "pitch"):
            n = task.n_agents or 4
            model = self.default_model
        else:
            model = self.default_model
        return n, model

    def _run_single_agent(
        self, agent_id: int, task: SwarmTask, model: str, n_agents: int
    ) -> AgentVote:
        t0 = time.monotonic()
        prompt = _build_agent_prompt(task, agent_id, n_agents)
        try:
            text, used_model = _call_llm_sync(prompt, model, task.timeout_s * 0.8)
            confidence = _parse_confidence(text)
            answer = _strip_confidence_line(text)
            return AgentVote(
                agent_id=agent_id,
                answer=answer,
                confidence=confidence,
                model=used_model,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            logger.warning("swarm_engine: agent %d failed: %s", agent_id, exc)
            return AgentVote(
                agent_id=agent_id,
                answer="",
                confidence=0.0,
                model=model,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

    def _select_winner(self, votes: list[AgentVote], final_confs: list[float]) -> int:
        """Return index of winning vote (highest belief-propagated confidence)."""
        if not votes:
            return 0
        best_i, best_c = 0, -1.0
        for i, (v, c) in enumerate(zip(votes, final_confs)):
            if v.answer and c > best_c:
                best_c = c
                best_i = i
        return best_i

    def run_sync(self, task: SwarmTask) -> SwarmResult:
        t0 = time.monotonic()
        n_agents, model = self._resolve_config(task)

        logger.info(
            "swarm_engine: starting %d agents for task_type=%s model=%s",
            n_agents, task.task_type, model,
        )

        votes: list[AgentVote] = []
        with ThreadPoolExecutor(
            max_workers=min(n_agents, self.max_workers),
            thread_name_prefix="swarm",
        ) as pool:
            futures = {
                pool.submit(self._run_single_agent, i, task, model, n_agents): i
                for i in range(n_agents)
            }
            for fut in as_completed(futures, timeout=task.timeout_s):
                try:
                    votes.append(fut.result())
                except Exception as exc:
                    agent_id = futures[fut]
                    logger.warning("swarm_engine: future %d raised: %s", agent_id, exc)

        # Sort by agent_id for determinism
        votes.sort(key=lambda v: v.agent_id)
        valid_votes = [v for v in votes if v.answer]

        if not valid_votes:
            return SwarmResult(
                answer="Geen antwoord — alle agents faalden. Controleer of Ollama draait.",
                confidence=0.0,
                votes=votes,
                n_agents=n_agents,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # Belief propagation over valid votes
        final_confs = _propagate_beliefs(valid_votes)
        winner_i = self._select_winner(valid_votes, final_confs)
        winner = valid_votes[winner_i]

        # Update votes with propagated confidence
        for v, c in zip(valid_votes, final_confs):
            v.confidence = round(c, 3)

        # Overall confidence = mean of top 50% propagated beliefs
        sorted_confs = sorted(final_confs, reverse=True)
        top_half = sorted_confs[: max(1, len(sorted_confs) // 2)]
        overall_conf = sum(top_half) / len(top_half)

        # Dissenting answers (non-winner valid votes with different content)
        dissent = [
            v.answer for i, v in enumerate(valid_votes)
            if i != winner_i and v.answer != winner.answer
        ]

        total_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "swarm_engine: done — winner=agent%d confidence=%.2f n_valid=%d/%d time=%dms",
            winner.agent_id, overall_conf, len(valid_votes), n_agents, total_ms,
        )

        return SwarmResult(
            answer=winner.answer,
            confidence=round(overall_conf, 3),
            votes=votes,
            dissent=dissent[:2],  # max 2 dissenting views
            winner_agent=winner.agent_id,
            n_agents=n_agents,
            duration_ms=total_ms,
            provider=winner.model,
        )

    async def run(self, task: SwarmTask) -> SwarmResult:
        """Async wrapper — runs swarm in executor to avoid blocking event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run_sync, task)

    async def select_agents_qce(self, goal: str, n: int = 3,
                                available: list[str] | None = None) -> list[str]:
        """Use AmplitudeRouter.route_swarm() for diversity-constrained agent selection."""
        try:
            from core.quantum.engine import get_qce
            qce = get_qce()
            pack = await qce.process(goal=goal, task_type='execution')
            return qce._router.route_swarm(pack, n=n)
        except Exception:
            pass
        return (available or [])[:n]


# ── Convenience functions ─────────────────────────────────────────────────────

_default_engine: SwarmEngine | None = None


def get_engine() -> SwarmEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = SwarmEngine()
    return _default_engine


def swarm_code(goal: str, context: str = "", n_agents: int = 5) -> SwarmResult:
    """Shortcut: run swarm for code generation."""
    return get_engine().run_sync(SwarmTask(
        goal=goal, context=context, task_type="code", n_agents=n_agents,
    ))


def swarm_analyze(goal: str, context: str = "", n_agents: int = 4) -> SwarmResult:
    """Shortcut: run swarm for analysis/decisions."""
    return get_engine().run_sync(SwarmTask(
        goal=goal, context=context, task_type="analysis", n_agents=n_agents,
    ))


def swarm_pitch(goal: str, context: str = "", n_agents: int = 3) -> SwarmResult:
    """Shortcut: run swarm for pitch/copy generation."""
    return get_engine().run_sync(SwarmTask(
        goal=goal, context=context, task_type="pitch", n_agents=n_agents,
    ))

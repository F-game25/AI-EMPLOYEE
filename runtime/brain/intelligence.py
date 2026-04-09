"""intelligence.py — IntelligenceCore: the unified intelligence layer.

This module fuses three things that were previously separate:
  1. Central Brain       — neural decision-making (learns what actions work)
  2. MemoryStore         — persistent per-user facts + conversation history
  3. Personalisation     — user-preference profile that grows over time

All three are accessed through one singleton:

    from brain.intelligence import get_intelligence
    intel = get_intelligence()

    # Before each LLM call — enriches the system prompt with context
    context = intel.build_context("user:default", message)

    # After each exchange — stores memory + trains the brain
    intel.on_exchange("user:default", user_msg, agent_response, agent_id)

    # Provide outcome feedback (optional — improves routing over time)
    intel.reward("user:default", reward=1.0)

All state is kept locally under ~/.ai-employee/.  Nothing is sent to any
external service.

Architecture
------------

                 ┌─────────────────────────────────┐
  chat request → │      IntelligenceCore            │ → enriched system prompt
                 │   ┌──────────┐  ┌────────────┐  │
                 │   │  Brain   │  │MemoryStore │  │
                 │   │(neural   │  │(facts +    │  │
                 │   │ routing) │  │ convo hist)│  │
                 │   └─────┬────┘  └─────┬──────┘  │
                 │         │             │          │
                 │   ┌─────▼─────────────▼──────┐  │
                 │   │   Personalisation         │  │
                 │   │   (preferences, tone,     │  │
                 │   │    recurring topics)      │  │
                 │   └───────────────────────────┘  │
                 └─────────────────────────────────┘
  exchange done → intel.on_exchange() → store memory + train brain
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import re
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("intelligence")

# ── Paths ─────────────────────────────────────────────────────────────────────
_AI_HOME      = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))
_INTEL_DIR    = _AI_HOME / "state" / "intelligence"
_PROFILE_DIR  = _INTEL_DIR / "profiles"
_INTEL_DIR.mkdir(parents=True, exist_ok=True)
_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_id(raw: str) -> str:
    """Sanitize a user/entity ID for use in file names."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw)
    if not safe or safe in {".", ".."}:
        raise ValueError("Invalid user_id")
    return safe


# ── Feature encoding constants ────────────────────────────────────────────────
# The Brain input vector is 64-dim.  We use a fixed layout so features are
# always aligned whether they come from chat, tasks, or background collection.

_FEATURE_SIZE   = 64   # must match nn_config.yaml input_size
_FEATURE_LAYOUT = {
    # ── conversation features (0–9) ────────────────────────────────────────
    "msg_length":       0,   # normalised message length [0,1]
    "response_length":  1,   # normalised response length [0,1]
    "sentiment_pos":    2,   # positive word count / 20
    "sentiment_neg":    3,   # negative word count / 20
    "is_question":      4,   # 1.0 if message ends with "?"
    "is_command":       5,   # 1.0 if message starts with imperative verb
    "turn_number":      6,   # normalised session turn count
    "session_duration": 7,   # minutes since session start / 60
    "user_frustration": 8,   # escalation signal
    "explicit_praise":  9,   # "thanks", "great", "perfect" etc
    # ── agent routing features (10–19) ────────────────────────────────────
    "routed_agent_0":   10,  # one-hot over 8 agent buckets (spread 10–17)
    "routed_agent_1":   11,
    "routed_agent_2":   12,
    "routed_agent_3":   13,
    "routed_agent_4":   14,
    "routed_agent_5":   15,
    "routed_agent_6":   16,
    "routed_agent_7":   17,
    "mode_starter":     18,  # 1.0 if starter mode
    "mode_business":    19,  # 1.0 if business mode
    # ── memory / personalisation features (20–39) ──────────────────────────
    "memory_depth":     20,  # normalised fact count [0,1]
    "convo_turns":      21,  # normalised conversation turns [0,1]
    "preference_local": 22,  # 1.0 if user prefers local models
    "preference_speed": 23,  # 1.0 if user values speed
    "preference_detail":24,  # 1.0 if user values detail
    "topic_tech":       25,  # recurring topic: technology
    "topic_sales":      26,  # recurring topic: sales/leads
    "topic_finance":    27,  # recurring topic: finance
    "topic_content":    28,  # recurring topic: content/writing
    "topic_strategy":   29,  # recurring topic: strategy/planning
    "avg_reward":       30,  # rolling average reward from past interactions
    "success_rate":     31,  # fraction of interactions with reward > 0
    "days_active":      32,  # normalised (days since first interaction / 365)
    "session_count":    33,  # normalised session count
    "repeat_agent":     34,  # 1.0 if same agent used in last turn
    "personality_0":    35,  # personalisation embedding dims (35–43)
    "personality_1":    36,
    "personality_2":    37,
    "personality_3":    38,
    "personality_4":    39,
    # ── task / outcome features (40–63) ───────────────────────────────────
    "task_complexity":  40,  # estimated task complexity [0,1]
    "task_success":     41,  # most recent task outcome
    "last_loss":        42,  # brain's last loss (normalised)
    "brain_confidence": 43,  # confidence of last brain prediction
    # dims 44–63 are reserved / zero-padded
}

# ── Positive / negative word lists for lightweight sentiment ──────────────────
_POS_WORDS = frozenset(
    "great perfect thanks thank good excellent awesome amazing wonderful"
    " yes please helpful love like nice yes brilliant done".split()
)
_NEG_WORDS = frozenset(
    "wrong bad broken fail error issue problem hate dislike terrible"
    " awful horrible no not never again useless slow crash bug".split()
)

# ── Agent bucket mapping (8 buckets to match output_size) ────────────────────
_AGENT_BUCKETS: Dict[str, int] = {
    "lead":         0,
    "sales":        0,
    "email":        1,
    "outreach":     1,
    "content":      2,
    "writing":      2,
    "finance":      3,
    "analytics":    3,
    "strategy":     4,
    "ceo":          4,
    "tech":         5,
    "engineering":  5,
    "support":      6,
    "customer":     6,
    "general":      7,
    "orchestrator": 7,
    "task":         7,
}


def _agent_to_bucket(agent_id: str) -> int:
    """Map an agent ID string to one of 8 buckets."""
    lower = agent_id.lower()
    for keyword, bucket in _AGENT_BUCKETS.items():
        if keyword in lower:
            return bucket
    return 7  # default: general


def _text_sentiment(text: str) -> Tuple[float, float]:
    """Return (positive_score, negative_score) for a text snippet."""
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.0, 0.0
    pos = min(sum(1 for w in words if w in _POS_WORDS) / 20.0, 1.0)
    neg = min(sum(1 for w in words if w in _NEG_WORDS) / 20.0, 1.0)
    return pos, neg


# ═════════════════════════════════════════════════════════════════════════════
# Personalisation profile
# ═════════════════════════════════════════════════════════════════════════════

class UserProfile:
    """Persistent user preference profile that grows with every interaction.

    Stored as a JSON file under _PROFILE_DIR/{user_id}.json.
    All numeric fields are kept as float for easy embedding.
    """

    _DEFAULTS: Dict[str, Any] = {
        "version":         1,
        "created_at":      "",
        "updated_at":      "",
        "first_seen":      "",
        "interaction_count": 0,
        "session_count":     0,
        "days_active":       0.0,
        # Preferences (0=neutral, grow toward 1 with evidence)
        "prefers_local":    0.0,
        "prefers_speed":    0.0,
        "prefers_detail":   0.0,
        # Rolling averages
        "avg_reward":       0.0,
        "success_rate":     0.5,
        "reward_samples":   0,
        # Recurring topics (count-based, normalised)
        "topics": {
            "tech": 0, "sales": 0, "finance": 0, "content": 0, "strategy": 0,
        },
        # Most-used agents (agent_id → count)
        "agent_counts": {},
        # Tone preferences extracted from positive feedback
        "tone": "balanced",          # "concise" | "detailed" | "balanced"
        # Personality embedding (5 learned dims, all start at 0)
        "personality": [0.0, 0.0, 0.0, 0.0, 0.0],
        # Free-text facts extracted from conversation
        "extracted_facts": [],
    }

    def __init__(self, user_id: str, profile_dir: Optional[Path] = None) -> None:
        self.user_id = user_id
        _dir = (profile_dir if profile_dir is not None else _PROFILE_DIR).resolve()
        _dir.mkdir(parents=True, exist_ok=True)
        # Guard against path-traversal: safe_id only allows alphanumeric/-/_.
        _safe = _safe_id(user_id)
        _candidate = (_dir / f"{_safe}.json").resolve()
        # Ensure the resolved path is still inside the profile directory
        try:
            _candidate.relative_to(_dir)
        except ValueError:
            raise ValueError(f"Unsafe user_id would escape profile dir: {user_id!r}")
        self._path = _candidate
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                # Use deepcopy of defaults to avoid sharing mutable nested objects
                merged = copy.deepcopy(self._DEFAULTS)
                merged.update(raw)
                return merged
            except Exception:
                pass
        d = copy.deepcopy(self._DEFAULTS)
        d["created_at"] = _now_iso()
        d["first_seen"]  = _now_iso()
        return d

    def save(self) -> None:
        with self._lock:
            self._data["updated_at"] = _now_iso()
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    # ── Update methods ─────────────────────────────────────────────────────────

    def record_interaction(
        self,
        user_msg: str,
        agent_response: str,
        agent_id: str,
        reward: float = 0.0,
    ) -> None:
        """Update profile based on one conversation turn."""
        with self._lock:
            d = self._data
            d["interaction_count"] = d.get("interaction_count", 0) + 1

            # Topic detection
            combined = (user_msg + " " + agent_response).lower()
            for topic in ("tech", "sales", "finance", "content", "strategy"):
                if topic in combined or (
                    topic == "tech" and any(w in combined for w in ("code", "api", "software", "python"))
                ) or (
                    topic == "sales" and any(w in combined for w in ("lead", "email", "outreach", "crm"))
                ) or (
                    topic == "finance" and any(w in combined for w in ("invoice", "money", "budget", "revenue"))
                ) or (
                    topic == "content" and any(w in combined for w in ("write", "blog", "post", "article", "copy"))
                ) or (
                    topic == "strategy" and any(w in combined for w in ("plan", "strategy", "goal", "mission"))
                ):
                    d["topics"][topic] = d["topics"].get(topic, 0) + 1

            # Agent usage
            agent_counts = d.setdefault("agent_counts", {})
            agent_counts[agent_id] = agent_counts.get(agent_id, 0) + 1

            # Reward rolling average
            n = d.get("reward_samples", 0) + 1
            prev_avg = d.get("avg_reward", 0.0)
            d["avg_reward"] = prev_avg + (reward - prev_avg) / n
            d["reward_samples"] = n

            # Success rate
            if n == 1:
                d["success_rate"] = 1.0 if reward > 0 else 0.0
            else:
                prev_sr = d.get("success_rate", 0.5)
                d["success_rate"] = prev_sr + ((1.0 if reward > 0 else 0.0) - prev_sr) / n

            # Preference signals from message content
            if any(w in user_msg.lower() for w in ("quick", "fast", "brief", "short", "tldr", "tl;dr")):
                d["prefers_speed"]  = min(d.get("prefers_speed", 0) + 0.05, 1.0)
            if any(w in user_msg.lower() for w in ("detail", "explain", "elaborate", "thorough", "deep", "full")):
                d["prefers_detail"] = min(d.get("prefers_detail", 0) + 0.05, 1.0)
            if any(w in user_msg.lower() for w in ("local", "offline", "private", "ollama")):
                d["prefers_local"]  = min(d.get("prefers_local", 0) + 0.1, 1.0)

            # Tone detection
            if d.get("prefers_speed", 0) > 0.4:
                d["tone"] = "concise"
            elif d.get("prefers_detail", 0) > 0.4:
                d["tone"] = "detailed"

            # Personality embedding: nudge in direction of reward signal
            pe = d.get("personality", [0.0] * 5)
            bucket = _agent_to_bucket(agent_id)
            if bucket < 5:
                pe[bucket] = max(-1.0, min(1.0, pe[bucket] + reward * 0.02))
            d["personality"] = pe

        self.save()

    def update_session(self) -> None:
        with self._lock:
            self._data["session_count"] = self._data.get("session_count", 0) + 1
            first = self._data.get("first_seen", "") or _now_iso()
            try:
                dt0 = datetime.fromisoformat(first.replace("Z", "+00:00"))
                dt1 = datetime.now(timezone.utc)
                days = (dt1 - dt0).total_seconds() / 86400.0
                self._data["days_active"] = round(days, 2)
            except Exception:
                pass
        self.save()

    def add_extracted_fact(self, key: str, value: str) -> None:
        with self._lock:
            facts = self._data.setdefault("extracted_facts", [])
            # Update if exists, else append
            for f in facts:
                if f.get("key") == key:
                    f["value"] = value
                    f["ts"]    = _now_iso()
                    break
            else:
                facts.append({"key": key, "value": value, "ts": _now_iso()})
            # Keep last 50 extracted facts
            self._data["extracted_facts"] = facts[-50:]
        self.save()

    def to_feature_vector(self) -> List[float]:
        """Return a 5-dim personality embedding for use in feature vectors."""
        return list(self._data.get("personality", [0.0] * 5))

    # ── Accessors ──────────────────────────────────────────────────────────────

    @property
    def tone(self) -> str:
        return self._data.get("tone", "balanced")

    @property
    def avg_reward(self) -> float:
        return float(self._data.get("avg_reward", 0.0))

    @property
    def success_rate(self) -> float:
        return float(self._data.get("success_rate", 0.5))

    @property
    def interaction_count(self) -> int:
        return int(self._data.get("interaction_count", 0))

    @property
    def prefers_local(self) -> float:
        return float(self._data.get("prefers_local", 0.0))

    @property
    def prefers_speed(self) -> float:
        return float(self._data.get("prefers_speed", 0.0))

    @property
    def prefers_detail(self) -> float:
        return float(self._data.get("prefers_detail", 0.0))

    @property
    def days_active(self) -> float:
        return float(self._data.get("days_active", 0.0))

    @property
    def session_count(self) -> int:
        return int(self._data.get("session_count", 0))

    @property
    def top_topics(self) -> List[str]:
        topics = self._data.get("topics", {})
        return sorted(topics, key=lambda k: topics[k], reverse=True)[:3]

    @property
    def favourite_agent(self) -> Optional[str]:
        counts = self._data.get("agent_counts", {})
        if not counts:
            return None
        return max(counts, key=lambda k: counts[k])

    @property
    def extracted_facts(self) -> List[Dict]:
        return list(self._data.get("extracted_facts", []))

    @property
    def data(self) -> Dict[str, Any]:
        return dict(self._data)


# ═════════════════════════════════════════════════════════════════════════════
# Feature encoder
# ═════════════════════════════════════════════════════════════════════════════

class FeatureEncoder:
    """Encode a conversation exchange + user profile into a 64-dim feature vector."""

    def encode(
        self,
        user_msg:   str,
        agent_resp: str,
        agent_id:   str,
        mode:       str,
        profile:    UserProfile,
        brain_confidence: float = 0.5,
        brain_last_loss:  float = 0.0,
        session_turn:     int   = 0,
        session_start_ts: Optional[float] = None,
    ) -> List[float]:
        """Return a 64-element list[float] ready to be wrapped in torch.tensor()."""
        vec = [0.0] * _FEATURE_SIZE

        # ── conversation features ──────────────────────────────────────────────
        vec[_FEATURE_LAYOUT["msg_length"]]      = min(len(user_msg)   / 2000.0, 1.0)
        vec[_FEATURE_LAYOUT["response_length"]] = min(len(agent_resp) / 5000.0, 1.0)
        pos, neg = _text_sentiment(user_msg)
        vec[_FEATURE_LAYOUT["sentiment_pos"]]   = pos
        vec[_FEATURE_LAYOUT["sentiment_neg"]]   = neg
        vec[_FEATURE_LAYOUT["is_question"]]     = 1.0 if user_msg.rstrip().endswith("?") else 0.0
        _imperative = ("write", "create", "make", "build", "generate", "find", "get",
                       "send", "run", "start", "stop", "show", "list", "do", "help")
        vec[_FEATURE_LAYOUT["is_command"]]      = 1.0 if any(
            user_msg.lower().startswith(v) for v in _imperative
        ) else 0.0
        vec[_FEATURE_LAYOUT["turn_number"]]     = min(session_turn / 50.0, 1.0)
        if session_start_ts is not None:
            import time
            elapsed_min = (time.monotonic() - session_start_ts) / 60.0
            vec[_FEATURE_LAYOUT["session_duration"]] = min(elapsed_min / 60.0, 1.0)
        frust = min(neg * 3.0, 1.0)  # frustration = amplified negativity
        vec[_FEATURE_LAYOUT["user_frustration"]] = frust
        _praise = frozenset("thanks thank great perfect awesome amazing excellent".split())
        vec[_FEATURE_LAYOUT["explicit_praise"]] = 1.0 if any(
            w in user_msg.lower().split() for w in _praise
        ) else 0.0

        # ── agent routing one-hot ──────────────────────────────────────────────
        bucket = _agent_to_bucket(agent_id)
        onehot_base = _FEATURE_LAYOUT["routed_agent_0"]
        vec[onehot_base + bucket] = 1.0

        # ── mode ──────────────────────────────────────────────────────────────
        if mode == "starter":
            vec[_FEATURE_LAYOUT["mode_starter"]]  = 1.0
        elif mode == "business":
            vec[_FEATURE_LAYOUT["mode_business"]] = 1.0

        # ── memory / personalisation ───────────────────────────────────────────
        vec[_FEATURE_LAYOUT["memory_depth"]]    = min(len(profile.extracted_facts) / 50.0, 1.0)
        vec[_FEATURE_LAYOUT["convo_turns"]]     = min(profile.interaction_count / 200.0, 1.0)
        vec[_FEATURE_LAYOUT["preference_local"]]  = profile.prefers_local
        vec[_FEATURE_LAYOUT["preference_speed"]]  = profile.prefers_speed
        vec[_FEATURE_LAYOUT["preference_detail"]] = profile.prefers_detail

        topics = profile.top_topics
        for i, topic_key in enumerate(("tech", "sales", "finance", "content", "strategy")):
            if topic_key in topics:
                vec[_FEATURE_LAYOUT[f"topic_{topic_key}"]] = 1.0

        vec[_FEATURE_LAYOUT["avg_reward"]]    = (profile.avg_reward + 1.0) / 2.0  # normalise to [0,1]
        vec[_FEATURE_LAYOUT["success_rate"]]  = profile.success_rate
        vec[_FEATURE_LAYOUT["days_active"]]   = min(profile.days_active / 365.0, 1.0)
        vec[_FEATURE_LAYOUT["session_count"]] = min(profile.session_count / 100.0, 1.0)

        # Personality dims
        pe = profile.to_feature_vector()
        for i in range(min(5, len(pe))):
            vec[_FEATURE_LAYOUT[f"personality_{i}"]] = (pe[i] + 1.0) / 2.0  # [-1,1] → [0,1]

        # ── task / brain feedback ──────────────────────────────────────────────
        vec[_FEATURE_LAYOUT["brain_confidence"]] = max(0.0, min(float(brain_confidence), 1.0))
        vec[_FEATURE_LAYOUT["last_loss"]]         = min(float(brain_last_loss) / 5.0, 1.0)

        # Clamp all values to [0, 1] for numerical stability
        return [max(0.0, min(1.0, v)) for v in vec]


# ═════════════════════════════════════════════════════════════════════════════
# Fact extractor — pulls structured facts from free text
# ═════════════════════════════════════════════════════════════════════════════

_FACT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("name",       re.compile(r"(?:my name is|i'm|i am|call me)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)", re.I)),
    ("company",    re.compile(r"(?:my company|our company|i work at|working at|at a company called)\s+([A-Za-z0-9 &']+?)(?:\.|,|$)", re.I)),
    ("industry",   re.compile(r"(?:in the|work in|we're in the)\s+([\w\s]+?)\s+(?:industry|space|sector|niche)", re.I)),
    ("goal",       re.compile(r"(?:my goal is|i want to|we want to|i need to|we need to)\s+(.{10,100}?)(?:\.|,|$)", re.I)),
    ("language",   re.compile(r"(?:using|written in|prefer)\s+(python|javascript|typescript|go|rust|java|c\+\+|php)", re.I)),
    ("budget",     re.compile(r"(?:budget is|spending|budget of)\s+\$?([\d,]+(?:k|K)?)\s*(?:per\s+\w+|/\w+|a\s+\w+)?", re.I)),
    ("location",   re.compile(r"(?:based in|i'm from|we're in|located in)\s+([A-Za-z]+(?: [A-Za-z]+)*)", re.I)),
]


def extract_facts_from_text(text: str) -> List[Tuple[str, str]]:
    """Extract structured key-value facts from a message using regex patterns.

    Returns a list of (key, value) tuples.  Empty list if none found.
    """
    found = []
    for key, pattern in _FACT_PATTERNS:
        m = pattern.search(text)
        if m:
            value = m.group(1).strip(" .,")
            if value:
                found.append((key, value))
    return found


# ═════════════════════════════════════════════════════════════════════════════
# IntelligenceCore
# ═════════════════════════════════════════════════════════════════════════════

class IntelligenceCore:
    """Unified intelligence layer — Brain + Memory + Personalisation.

    This is a process-wide singleton (use ``get_intelligence()``).
    All methods are thread-safe.
    """

    def __init__(self, profile_dir: Optional[Path] = None) -> None:
        self._lock             = threading.RLock()
        self._encoder          = FeatureEncoder()
        self._profiles: Dict[str, UserProfile] = {}
        self._session_turns: Dict[str, int]     = {}
        self._session_starts: Dict[str, float]  = {}
        self._last_state: Dict[str, Any]         = {}   # per user: {state_vec, action, agent_id}
        self._brain = None          # lazy-loaded Brain singleton
        self._memory = None         # lazy-loaded MemoryStore
        # Optional explicit profile directory (useful for testing / multi-tenant)
        self._profile_dir: Optional[Path] = profile_dir
        logger.info("IntelligenceCore initialised")

    # ── Lazy loaders ──────────────────────────────────────────────────────────

    def _get_brain(self):
        """Return the Brain singleton, or None if unavailable."""
        if self._brain is not None:
            return self._brain
        with self._lock:
            if self._brain is not None:
                return self._brain
            try:
                _runtime = Path(__file__).resolve().parents[1]
                if str(_runtime) not in sys.path:
                    sys.path.insert(0, str(_runtime))
                from brain.brain import get_brain  # noqa: PLC0415
                self._brain = get_brain()
            except Exception as exc:
                logger.warning("IntelligenceCore: Brain unavailable — %s", exc)
        return self._brain

    def _get_memory(self):
        """Return the MemoryStore singleton, or None if unavailable."""
        if self._memory is not None:
            return self._memory
        with self._lock:
            if self._memory is not None:
                return self._memory
            try:
                _mem_dir = Path(__file__).resolve().parents[1] / "agents" / "memory"
                if str(_mem_dir) not in sys.path:
                    sys.path.insert(0, str(_mem_dir))
                from memory_store import MemoryStore  # noqa: PLC0415
                self._memory = MemoryStore()
            except Exception as exc:
                logger.warning("IntelligenceCore: MemoryStore unavailable — %s", exc)
        return self._memory

    def _profile(self, user_id: str) -> UserProfile:
        with self._lock:
            if user_id not in self._profiles:
                self._profiles[user_id] = UserProfile(user_id, profile_dir=self._profile_dir)
        return self._profiles[user_id]

    # ── Session management ────────────────────────────────────────────────────

    def start_session(self, user_id: str) -> None:
        """Record a new session for personalisation tracking."""
        import time
        with self._lock:
            self._session_turns[user_id]  = 0
            self._session_starts[user_id] = time.monotonic()
        self._profile(user_id).update_session()

    def _turn(self, user_id: str) -> Tuple[int, Optional[float]]:
        """Return (current_turn, session_start_ts) and increment turn."""
        with self._lock:
            turn = self._session_turns.get(user_id, 0)
            start = self._session_starts.get(user_id)
            self._session_turns[user_id] = turn + 1
        return turn, start

    # ── Context builder (call BEFORE the LLM) ─────────────────────────────────

    def build_context(self, user_id: str, message: str, mode: str = "power") -> str:
        """Build a personalised context string to inject into the system prompt.

        This enriches every LLM call with:
          - Stored facts about the user
          - Recent conversation history
          - Tone/preference hints
          - Top topics and favourite agent

        Args:
            user_id:  User identifier (e.g. "user:default", "user:alice").
            message:  The current user message.
            mode:     Current system mode ("starter" | "business" | "power").

        Returns:
            A compact multi-line string to prepend to the system prompt.
            Empty string if no relevant context is available.
        """
        parts: List[str] = []
        profile = self._profile(user_id)
        memory  = self._get_memory()

        # User profile snapshot
        if profile.interaction_count > 0:
            parts.append(f"[User Profile — {profile.interaction_count} interactions, {profile.days_active:.0f} days active]")
            if profile.tone != "balanced":
                parts.append(f"Preferred response tone: {profile.tone}.")
            if profile.top_topics:
                parts.append(f"Recurring topics: {', '.join(profile.top_topics)}.")
            if profile.favourite_agent:
                parts.append(f"Frequently uses: {profile.favourite_agent} agent.")
            if profile.prefers_local > 0.5:
                parts.append("User prefers local / offline models.")
            if profile.avg_reward > 0.3:
                parts.append(f"Engagement score: {profile.avg_reward:+.2f} (positive pattern).")
            elif profile.avg_reward < -0.2:
                parts.append("User has expressed frustration — be extra clear and concise.")

        # Extracted facts
        facts = profile.extracted_facts
        if facts:
            fact_lines = [f"  {f['key']}: {f['value']}" for f in facts[-10:]]
            parts.append("Known facts:\n" + "\n".join(fact_lines))

        # Conversation history from MemoryStore
        if memory:
            try:
                history = memory.get_conversation(user_id, last_n=6)
                if history:
                    parts.append("Recent conversation:")
                    for turn in history:
                        role    = turn.get("role", "?").capitalize()
                        content = turn.get("content", "")[:300]
                        parts.append(f"  {role}: {content}")
            except Exception as exc:
                logger.debug("IntelligenceCore.build_context memory error: %s", exc)

        if not parts:
            return ""

        header = "─── Personalised Context ───────────────────────────────────────"
        footer = "────────────────────────────────────────────────────────────────"
        return f"{header}\n" + "\n".join(parts) + f"\n{footer}"

    # ── Exchange handler (call AFTER the LLM responds) ────────────────────────

    def on_exchange(
        self,
        user_id:        str,
        user_msg:       str,
        agent_response: str,
        agent_id:       str,
        mode:           str = "power",
        reward:         float = 0.0,
    ) -> None:
        """Process one completed conversation exchange.

        Stores the exchange in MemoryStore, updates the user profile,
        extracts any structured facts, and trains the Brain on the outcome.

        Args:
            user_id:        User identifier.
            user_msg:       The user's message.
            agent_response: The AI's response.
            agent_id:       The agent that handled the request.
            mode:           Current system mode.
            reward:         Outcome quality signal (−1 bad, 0 neutral, +1 good).
                            The system infers a soft reward automatically if 0.
        """
        # Infer reward from response content if caller didn't provide one
        if reward == 0.0:
            reward = self._infer_reward(user_msg, agent_response)

        profile = self._profile(user_id)
        turn, start_ts = self._turn(user_id)

        # 1. Persist to MemoryStore ─────────────────────────────────────────────
        memory = self._get_memory()
        if memory:
            try:
                memory.append_conversation(user_id, "user",      user_msg,       entity_type="user")
                memory.append_conversation(user_id, "assistant",  agent_response, entity_type="user")
                memory.update_score(user_id, reward * 0.1)
            except Exception as exc:
                logger.debug("IntelligenceCore memory write error: %s", exc)

        # 2. Extract facts from user message ────────────────────────────────────
        for key, value in extract_facts_from_text(user_msg):
            profile.add_extracted_fact(key, value)
            if memory:
                try:
                    memory.remember(user_id, key, value, entity_type="user")
                except Exception:
                    pass

        # 3. Update personalisation profile ─────────────────────────────────────
        profile.record_interaction(user_msg, agent_response, agent_id, reward=reward)

        # 4. Train the Brain ────────────────────────────────────────────────────
        brain = self._get_brain()
        if brain is not None:
            try:
                import torch

                # Build state vector for this exchange
                brain_confidence = 0.5
                brain_last_loss  = float(brain.stats().get("last_loss", 0.0))

                state_vec = self._encoder.encode(
                    user_msg   = user_msg,
                    agent_resp = agent_response,
                    agent_id   = agent_id,
                    mode       = mode,
                    profile    = profile,
                    brain_confidence = brain_confidence,
                    brain_last_loss  = brain_last_loss,
                    session_turn     = turn,
                    session_start_ts = start_ts,
                )
                state = torch.tensor(state_vec, dtype=torch.float32)

                # Action = agent bucket (what specialist was used)
                action = _agent_to_bucket(agent_id)

                # Retrieve previous state if available (for next_state)
                prev = self._last_state.get(user_id)
                if prev is not None:
                    prev_state = torch.tensor(prev["state"], dtype=torch.float32)
                    prev_action = prev["action"]
                    brain.store_experience(prev_state, prev_action, reward, state)

                # Store current state for next turn's next_state
                with self._lock:
                    self._last_state[user_id] = {
                        "state":  state_vec,
                        "action": action,
                        "agent":  agent_id,
                    }

            except Exception as exc:
                logger.warning("IntelligenceCore Brain training error: %s", exc)

    def reward(self, user_id: str, reward: float) -> None:
        """Provide explicit outcome feedback for the last exchange.

        Call this when you know the result (e.g. user clicked 'thumbs up',
        task completed successfully, etc.).

        Args:
            user_id: User identifier.
            reward:  Outcome quality (−1 very bad, 0 neutral, +1 very good).
        """
        brain = self._get_brain()
        if brain is None:
            return
        last = self._last_state.get(user_id)
        if last is None:
            return
        try:
            import torch
            # Re-use stored state as both current and next (terminal transition)
            state = torch.tensor(last["state"], dtype=torch.float32)
            brain.store_experience(state, last["action"], reward, state)
        except Exception as exc:
            logger.warning("IntelligenceCore.reward error: %s", exc)

    # ── Agent routing hint ────────────────────────────────────────────────────

    def suggest_agent_bucket(self, user_id: str, user_msg: str, mode: str = "power") -> int:
        """Ask the Brain which agent bucket to use for this message.

        Returns an integer 0–7 (agent bucket index).
        Falls back to 7 (general/orchestrator) if Brain is unavailable.

        This is used by ``_generate_llm_response`` to augment keyword routing
        with learned routing preferences.
        """
        brain = self._get_brain()
        if brain is None:
            return 7
        profile  = self._profile(user_id)
        state_vec = self._encoder.encode(
            user_msg   = user_msg,
            agent_resp = "",
            agent_id   = "task-orchestrator",
            mode       = mode,
            profile    = profile,
        )
        try:
            import torch
            state  = torch.tensor(state_vec, dtype=torch.float32)
            action, _conf = brain.get_action(state)
            return int(action) % 8
        except Exception:
            return 7

    # ── Reward inference ──────────────────────────────────────────────────────

    @staticmethod
    def _infer_reward(user_msg: str, agent_response: str) -> float:
        """Infer a soft reward from message content when no explicit signal given.

        Heuristics:
          - Error / failure keywords in response → −0.5
          - Positive / praise keywords in user message → +0.5
          - Negative / frustration keywords in user message → −0.3
          - Neutral / no signal → 0.0
        """
        resp_lower = agent_response.lower()
        msg_lower  = user_msg.lower()

        # Error in response
        if any(w in resp_lower for w in ("error", "failed", "sorry", "cannot", "unavailable",
                                          "no model", "timed out", "check your")):
            return -0.5

        # Explicit praise from user
        if any(w in msg_lower for w in ("thanks", "thank you", "great", "perfect",
                                         "awesome", "exactly", "that's right", "yes")):
            return 0.5

        # Frustration from user
        if any(w in msg_lower for w in ("wrong", "not right", "that's wrong", "no",
                                         "terrible", "broken", "hate", "useless")):
            return -0.3

        return 0.0

    # ── Stats / diagnostics ───────────────────────────────────────────────────

    def stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a stats dict for monitoring / dashboard."""
        brain = self._get_brain()
        result: Dict[str, Any] = {
            "brain_available":     brain is not None,
            "memory_available":    self._get_memory() is not None,
            "active_profiles":     len(self._profiles),
            "brain_stats":         brain.stats() if brain else {},
        }
        if user_id:
            profile = self._profile(user_id)
            result["profile"] = {
                "interaction_count": profile.interaction_count,
                "session_count":     profile.session_count,
                "days_active":       profile.days_active,
                "avg_reward":        profile.avg_reward,
                "success_rate":      profile.success_rate,
                "top_topics":        profile.top_topics,
                "favourite_agent":   profile.favourite_agent,
                "tone":              profile.tone,
                "extracted_facts":   profile.extracted_facts,
                "personality":       profile.to_feature_vector(),
            }
        return result

    def profile_summary(self, user_id: str) -> str:
        """Return a compact human-readable profile summary for the UI."""
        profile = self._profile(user_id)
        if profile.interaction_count == 0:
            return "No profile yet — start chatting to personalise your AI."
        lines = [
            f"Interactions: {profile.interaction_count}  |  Sessions: {profile.session_count}  |  Active: {profile.days_active:.0f} days",
            f"Tone: {profile.tone}  |  Success rate: {profile.success_rate:.0%}",
        ]
        if profile.top_topics:
            lines.append(f"Top topics: {', '.join(profile.top_topics)}")
        if profile.favourite_agent:
            lines.append(f"Favourite agent: {profile.favourite_agent}")
        if profile.extracted_facts:
            lines.append(f"Known facts: {len(profile.extracted_facts)}")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# Singleton access
# ═════════════════════════════════════════════════════════════════════════════

_intel_instance:  Optional[IntelligenceCore] = None
_intel_lock = threading.Lock()


def get_intelligence() -> IntelligenceCore:
    """Return the process-wide IntelligenceCore singleton (thread-safe)."""
    global _intel_instance
    if _intel_instance is not None:
        return _intel_instance
    with _intel_lock:
        if _intel_instance is None:
            _intel_instance = IntelligenceCore()
    return _intel_instance

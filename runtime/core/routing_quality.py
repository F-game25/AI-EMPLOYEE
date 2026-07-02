"""C3 — Model-routing quality: difficulty estimation, capability-vs-difficulty
guard, output quality scoring, and a redacted model->quality ledger.

Why this exists
---------------
Before C3 the router (``compute_planner`` + ``model_lanes``) chose a tier from
keyword/context heuristics with **no capability-vs-difficulty guard** (audit
§137) and **no feedback** on whether a model's output was any good. A hard task
could silently land on a weak model, and nothing recorded which model produced
which quality.

This module adds three pure, config-driven pieces:
  1. ``estimate_difficulty(goal, context_len)`` — heuristic task difficulty.
  2. ``guard_tier(base_tier, goal, context_len)`` — never lets a hard task run
     below its capability floor (escalates the rung; never downgrades; never
     auto-selects a paid/remote target — that stays gated downstream).
  3. ``score_output`` + ``record_quality`` + ``quality_stats`` — a cheap,
     deterministic output-quality signal logged to a **redacted** JSONL ledger
     (model, task tier, difficulty, score — NO prompt/response text), so routing
     is observable and can learn.

Design rules honoured: no model names or magic numbers in logic (all in
``config/routing_quality.json`` with baked-in fallback defaults); never raises
into the routing path; the ledger never stores prompt/response content.
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from core.file_lock import FileLock
except Exception:  # noqa: BLE001 — fall back to a no-op lock if unavailable
    from contextlib import contextmanager

    @contextmanager
    def FileLock(_path, *_a, **_k):  # type: ignore
        yield

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "routing_quality.json"

# Baked-in defaults — used when the JSON is missing/partial so logic never breaks.
_DEFAULTS: dict[str, Any] = {
    "difficulty": {
        "context_token_thresholds": {"medium": 2000, "high": 8000, "critical": 16000},
        "context_weight": 0.35,
        "length_chars_full_weight": 600,
        "length_weight": 0.15,
        "signal_weights": {
            "multi_step": 0.20, "code": 0.18, "architecture": 0.22,
            "security": 0.25, "financial": 0.18, "reasoning": 0.15,
        },
        "level_thresholds": {"medium": 0.25, "high": 0.50, "critical": 0.78},
    },
    "capability_floor": {"low": "FAST", "medium": "NORMAL", "high": "HEAVY", "critical": "DEEP_THINKING"},
    "tier_rank": {"FAST": 1, "NORMAL": 2, "HEAVY": 3, "CODE": 3, "DEEP_THINKING": 4},
    "output_scoring": {
        "min_chars": 40, "good_chars": 200, "min_score_pass": 0.5,
        "failure_markers": ["i cannot", "i can't", "as an ai", "i'm unable", "i am unable",
                            "cannot assist", "unable to help"],
        "error_markers": ["traceback (most recent call last)", "internal server error"],
    },
    "ledger": {"filename": "model_quality.jsonl", "max_lines": 5000},
}

# Signal detectors (compiled once). These mirror compute_planner's vocabulary so
# the guard agrees with the base classifier, plus risk-weighted domains.
# NOTE: prefixes use a LEADING \b only (no trailing \b) so a prefix like "secur"
# matches its whole word family ("security", "secure") and "auth" matches
# "authorization". Erring toward firing a signal is the safe direction here — the
# guard only ever *escalates* compute, never starves it.
_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "multi_step": re.compile(
        r"\b(and then|after that|step \d|step-by-step|pipeline|workflow|orchestrat|"
        r"multi[- ]?step|each of|for every|finally|migrat)", re.I),
    "code": re.compile(
        r"\b(code|implement|build|function|debug|refactor|script|program|class|module|"
        r"api|endpoint|sql|query|algorithm|compile|deploy)", re.I),
    "architecture": re.compile(
        r"\b(architect|design|scalab|distribut|microservice|schema|infrastructure|"
        r"throughput|concurren|high[- ]availab|fault[- ]toleran)", re.I),
    "security": re.compile(
        r"\b(secur|auth|permission|secret|credential|encrypt|token|vulnerab|injection|"
        r"sandbox|tenant isolation|access control|privilege|isolat)", re.I),
    "financial": re.compile(
        r"\b(payment|invoice|trading|price|pricing|revenue|tax|billing|refund|margin|"
        r"financ|on[- ]?chain|smart contract|wallet)", re.I),
    "reasoning": re.compile(
        r"\b(analy[sz]e|compare|evaluate|strateg|optimi[sz]e|research|investigate|"
        r"trade[- ]?off|root cause)", re.I),
}

_DIFFICULTY_ORDER = ("low", "medium", "high", "critical")

_LEDGER_LOCK = threading.Lock()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* so a partial nested override (e.g.
    a single difficulty.signal_weights key) keeps the sibling defaults instead of
    replacing the whole nested map."""
    for key, val in override.items():
        if key.startswith("_"):
            continue
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


@functools.lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    """Load config recursively merged over baked defaults. Never raises."""
    cfg = json.loads(json.dumps(_DEFAULTS))  # deep copy of defaults
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        _deep_merge(cfg, loaded if isinstance(loaded, dict) else {})
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001 — config problems never break routing
        logger.warning("routing_quality: config load failed, using defaults: %s", exc)
    return cfg


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# ── 1. Difficulty estimation ──────────────────────────────────────────────────

def estimate_difficulty(goal: str, context_len: int = 0) -> dict[str, Any]:
    """Heuristic task difficulty in [0,1] with a discrete level + the signals fired.

    Pure + deterministic. ``context_len`` is an approximate input-token count
    (same units compute_planner already uses).

    Returns {score, level, signals, context_len}.
    """
    g = (goal or "").strip()
    cfg = _config()["difficulty"]
    signals: list[str] = []
    score = 0.0

    weights = cfg["signal_weights"]
    for name, pattern in _SIGNAL_PATTERNS.items():
        if name in weights and pattern.search(g):
            score += float(weights[name])
            signals.append(name)

    # Length contribution (longer asks tend to be harder), saturating.
    full = max(1, int(cfg.get("length_chars_full_weight", 600)))
    score += float(cfg.get("length_weight", 0.0)) * _clamp01(len(g) / full)

    # Context-size contribution, stepped by configured token thresholds.
    cw = float(cfg.get("context_weight", 0.0))
    th = cfg.get("context_token_thresholds", {})
    if cw and context_len:
        if context_len >= int(th.get("critical", 16000)):
            score += cw
        elif context_len >= int(th.get("high", 8000)):
            score += cw * 0.66
        elif context_len >= int(th.get("medium", 2000)):
            score += cw * 0.33

    score = _clamp01(score)
    level = _level_for_score(score)
    return {"score": round(score, 4), "level": level, "signals": signals, "context_len": int(context_len or 0)}


def _level_for_score(score: float) -> str:
    lt = _config()["difficulty"]["level_thresholds"]
    if score >= float(lt.get("critical", 0.78)):
        return "critical"
    if score >= float(lt.get("high", 0.50)):
        return "high"
    if score >= float(lt.get("medium", 0.25)):
        return "medium"
    return "low"


# ── 2. Capability-vs-difficulty guard ─────────────────────────────────────────

def tier_rank(tier: str) -> int:
    """Capability rank of a tier (higher = more capable). Unknown → 0."""
    return int(_config()["tier_rank"].get((tier or "").strip().upper(), 0))


def min_tier_for_level(level: str) -> str:
    """The capability-floor tier a difficulty level requires."""
    return _config()["capability_floor"].get((level or "low").strip().lower(), "NORMAL")


def guard_enabled() -> bool:
    """C3 guard on unless explicitly disabled (ROUTING_QUALITY_GUARD=0/off/false)."""
    return os.environ.get("ROUTING_QUALITY_GUARD", "1").strip().lower() not in {"0", "off", "false", "no"}


def guard_tier(base_tier: str, goal: str, context_len: int = 0) -> dict[str, Any]:
    """Raise ``base_tier`` to the difficulty floor if it is too weak for the task.

    Only ever *escalates* (never downgrades). The specialist CODE lane is left
    intact — a code task keeps its coder model (its size is already chosen by
    VRAM in model_lanes); the guard governs the general FAST/NORMAL/HEAVY/DEEP
    size ladder. Returns the (possibly raised) tier plus why.

    Returns {tier, base_tier, escalated, difficulty, floor_tier, reason, enabled}.
    """
    base = (base_tier or "NORMAL").strip().upper()
    diff = estimate_difficulty(goal, context_len)
    floor = min_tier_for_level(diff["level"]).strip().upper()

    if not guard_enabled():
        return {"tier": base, "base_tier": base, "escalated": False, "difficulty": diff,
                "floor_tier": floor, "reason": "guard disabled (ROUTING_QUALITY_GUARD)", "enabled": False}

    # Never move a task out of the specialist coder lane.
    if base == "CODE":
        return {"tier": base, "base_tier": base, "escalated": False, "difficulty": diff,
                "floor_tier": floor, "reason": "code lane preserved (specialist coder model)", "enabled": True}

    if tier_rank(floor) > tier_rank(base):
        return {"tier": floor, "base_tier": base, "escalated": True, "difficulty": diff,
                "floor_tier": floor,
                "reason": f"{diff['level']} difficulty (score {diff['score']}, signals "
                          f"{diff['signals'] or ['none']}) requires >= {floor}; raised from {base}",
                "enabled": True}

    return {"tier": base, "base_tier": base, "escalated": False, "difficulty": diff,
            "floor_tier": floor,
            "reason": f"{base} already meets {diff['level']}-difficulty floor ({floor})", "enabled": True}


# ── 3. Output quality scoring ─────────────────────────────────────────────────

def score_output(goal: str, output: str, *, task_type: str | None = None) -> dict[str, Any]:
    """Cheap, deterministic quality score in [0,1] for a model output.

    Catches the common regressions a weak/failing model produces: empty/too
    short, refusals ("I cannot…"), raw error dumps, and answers that ignore the
    ask entirely. NOT a correctness oracle — it complements the JS
    ``result_verifier`` (which runs real tests), giving a routing-time signal.

    Returns {score, passed, reasons}.
    """
    cfg = _config()["output_scoring"]
    text = (output or "").strip()
    low = text.lower()
    reasons: list[str] = []
    score = 1.0

    min_chars = int(cfg.get("min_chars", 40))
    good_chars = int(cfg.get("good_chars", 200))

    if not text:
        return {"score": 0.0, "passed": False, "reasons": ["empty_output"]}

    if len(text) < min_chars:
        score -= 0.5
        reasons.append("too_short")
    elif len(text) < good_chars:
        score -= 0.15
        reasons.append("thin")

    for marker in cfg.get("failure_markers", []):
        if marker in low:
            score -= 0.5
            reasons.append("refusal_or_disclaimer")
            break

    for marker in cfg.get("error_markers", []):
        if marker in low:
            score -= 0.6
            reasons.append("error_dump")
            break

    # Relevance: does the output share meaningful tokens with the goal?
    goal_terms = {t for t in re.findall(r"[a-zA-Z]{4,}", (goal or "").lower())}
    if goal_terms:
        overlap = len({t for t in re.findall(r"[a-zA-Z]{4,}", low)} & goal_terms)
        if overlap == 0:
            score -= 0.3
            reasons.append("off_topic")

    score = _clamp01(score)
    passed = score >= float(cfg.get("min_score_pass", 0.5))
    return {"score": round(score, 4), "passed": passed, "reasons": reasons or ["ok"]}


# ── 4. Model -> quality ledger (redacted) ─────────────────────────────────────

def _state_dir() -> Path:
    """State dir, matching cost_ledger (~/.ai-employee/state), STATE_DIR-overridable."""
    base = os.environ.get("STATE_DIR")
    path = Path(base) if base else (Path.home() / ".ai-employee" / "state")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return path


def _current_tenant_id() -> "str | None":
    """Active tenant id if a request-scoped tenant context is set, else None.
    Uses the non-raising accessor so single-tenant / background callers are fine."""
    try:
        from core.tenancy import get_tenant_manager
        ctx = get_tenant_manager().get_current_tenant()
        return ctx.tenant_id if ctx is not None else None
    except Exception:  # noqa: BLE001 — tenancy optional; never break telemetry
        return None


def _goal_hash(goal: str) -> "str | None":
    """A tenant-keyed HMAC-SHA256 fingerprint of the goal for dedup/traceability
    ONLY (the goal text itself is never stored). Keying by tenant prevents cross-
    tenant correlation and offline dictionary attacks on the local ledger; this is
    not a cryptographic guarantee, just defense-in-depth over a plain SHA-1 prefix."""
    if not goal:
        return None
    key = (_current_tenant_id() or "global").encode("utf-8")
    return hmac.new(key, goal.encode("utf-8", "ignore"), hashlib.sha256).hexdigest()[:16]


def _ledger_path() -> Path:
    """Tenant-scoped ledger when a tenant context is active (so one tenant's quality
    data is never co-mingled with another's), shared path otherwise."""
    filename = _config()["ledger"].get("filename", "model_quality.jsonl")
    tid = _current_tenant_id()
    if tid:
        try:
            from core.tenancy import get_tenant_state_file
            return get_tenant_state_file(filename, tenant_id=tid)
        except Exception:  # noqa: BLE001 — fall back to shared on any tenancy error
            pass
    return _state_dir() / filename


def logging_enabled() -> bool:
    """model->quality logging on unless ROUTING_QUALITY_LOG=0/off/false."""
    return os.environ.get("ROUTING_QUALITY_LOG", "1").strip().lower() not in {"0", "off", "false", "no"}


def record_quality(
    model: str,
    *,
    score: float,
    passed: bool,
    task_type: str | None = None,
    difficulty: str | None = None,
    difficulty_score: float | None = None,
    tenant_id: str = "default",
    goal: str | None = None,
    reasons: list[str] | None = None,
) -> bool:
    """Append one **redacted** model->quality row to the JSONL ledger.

    Stores only: ts, model, tenant, task_type, difficulty(+score), quality
    score/passed, reasons, and a short goal *hash* (traceability, NOT content).
    Never stores prompt/response text. Bounded by ledger.max_lines. Never raises.
    """
    if not logging_enabled() or not model:
        return False
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": str(model),
        "tenant": str(tenant_id or "default"),
        "task_type": (task_type or "").strip() or None,
        "difficulty": (difficulty or "").strip() or None,
        "difficulty_score": difficulty_score,
        "score": round(float(score), 4),
        "passed": bool(passed),
        "reasons": list(reasons or []),
        "goal_hash": _goal_hash(goal),
    }
    try:
        path = _ledger_path()
        # Thread lock (intra-process) + fcntl FileLock (cross-process): append+trim
        # of the shared JSONL must be atomic across workers or rows interleave/truncate.
        with _LEDGER_LOCK:
            try:
                with FileLock(path):
                    with open(path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
                    _trim_ledger(path)
            except TimeoutError:
                logger.debug("routing_quality: ledger lock timeout; skipping append")
                return False
        return True
    except Exception as exc:  # noqa: BLE001 — telemetry must never break a run
        logger.debug("routing_quality: ledger append failed: %s", exc)
        return False


def _trim_ledger(path: Path) -> None:
    max_lines = int(_config()["ledger"].get("max_lines", 5000) or 0)
    if max_lines <= 0:
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            path.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def score_and_record(
    goal: str,
    output: str,
    model: str,
    *,
    task_type: str | None = None,
    tenant_id: str = "default",
    context_len: int = 0,
) -> dict[str, Any]:
    """Convenience for call sites: score an output and log model->quality in one
    call. Returns the score dict (with 'recorded' flag). Never raises."""
    try:
        diff = estimate_difficulty(goal, context_len)
        result = score_output(goal, output, task_type=task_type)
        recorded = record_quality(
            model, score=result["score"], passed=result["passed"], task_type=task_type,
            difficulty=diff["level"], difficulty_score=diff["score"], tenant_id=tenant_id,
            goal=goal, reasons=result["reasons"],
        )
        return {**result, "difficulty": diff["level"], "recorded": recorded}
    except Exception as exc:  # noqa: BLE001
        logger.debug("routing_quality.score_and_record failed: %s", exc)
        return {"score": None, "passed": None, "reasons": ["scoring_error"], "recorded": False}


def quality_stats(model: str | None = None, *, limit: int = 5000) -> dict[str, Any]:
    """Aggregate model->quality from the ledger (for diagnostics / future routing).

    Returns {samples, by_model: {model: {n, avg_score, pass_rate}}, overall}.
    """
    path = _ledger_path()
    by_model: dict[str, dict[str, float]] = {}
    total_n = 0
    total_score = 0.0
    total_pass = 0
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines()[-int(limit):]:
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                m = row.get("model")
                if not m or (model and m != model):
                    continue
                s = float(row.get("score") or 0.0)
                p = 1 if row.get("passed") else 0
                agg = by_model.setdefault(m, {"n": 0, "score_sum": 0.0, "pass_sum": 0})
                agg["n"] += 1
                agg["score_sum"] += s
                agg["pass_sum"] += p
                total_n += 1
                total_score += s
                total_pass += p
    except Exception as exc:  # noqa: BLE001
        logger.debug("routing_quality.quality_stats read failed: %s", exc)

    summary = {
        m: {
            "n": a["n"],
            "avg_score": round(a["score_sum"] / a["n"], 4) if a["n"] else None,
            "pass_rate": round(a["pass_sum"] / a["n"], 4) if a["n"] else None,
        }
        for m, a in by_model.items()
    }
    overall = {
        "n": total_n,
        "avg_score": round(total_score / total_n, 4) if total_n else None,
        "pass_rate": round(total_pass / total_n, 4) if total_n else None,
    }
    return {"samples": total_n, "by_model": summary, "overall": overall}

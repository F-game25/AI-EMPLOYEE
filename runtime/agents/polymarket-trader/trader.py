"""Polymarket Trader bot with MiroFish swarm intelligence + Alpha Insider strategy selection.

PAPER trading mode by default. Set LIVE_TRADING=true in polymarket-trader.env to enable live orders.
State is written to ~/.ai-employee/state/polymarket-trader.state.json

MiroFish integration: the inline MiroFishPredictor runs a lightweight swarm
simulation on each market quote to estimate the probability of YES resolution.
The mirofish-researcher agent (if running) also writes deeper estimates to
~/.ai-employee/config/polymarket_estimates.json which are blended with the
inline simulation for higher-quality signals.

Alpha Insider integration: fetches top-performing strategy ratings from
Alpha Insider (https://alphainsider.com) and uses them to weight decisions.
Requires ALPHA_INSIDER_API_KEY in .env.  Works in degraded mode without a key.

Strategy selector: tracks performance of each parameter configuration and
auto-adjusts edge thresholds and position sizes toward the best performers.
"""
import json
import os
import random
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "polymarket-trader.state.json"
STRATEGY_PERF_FILE = AI_HOME / "state" / "trader-strategy-performance.json"

POLL_SECONDS = int(os.environ.get("PM_POLL_SECONDS", "60"))
LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() == "true"
KILL_SWITCH = os.environ.get("KILL_SWITCH", "false").lower() == "true"
MAX_POSITION_USD = float(os.environ.get("MAX_POSITION_USD", "25"))
EDGE_THRESHOLD = float(os.environ.get("EDGE_THRESHOLD", "0.07"))
ALLOW_MARKETS = [m.strip() for m in os.environ.get("ALLOW_MARKETS", "").split(",") if m.strip()]
MIROFISH_ENABLED = os.environ.get("MIROFISH_ENABLED", "true").lower() == "true"
MIROFISH_AGENTS = int(os.environ.get("MIROFISH_AGENTS", "200"))
MIROFISH_ROUNDS = int(os.environ.get("MIROFISH_ROUNDS", "15"))

# Alpha Insider
ALPHA_INSIDER_API_KEY = os.environ.get("ALPHA_INSIDER_API_KEY", "")
ALPHA_INSIDER_URL = os.environ.get("ALPHA_INSIDER_URL", "https://alphainsider.com/api/v1")
ALPHA_INSIDER_ENABLED = os.environ.get("ALPHA_INSIDER_ENABLED", "true").lower() == "true"
ALPHA_INSIDER_TIMEOUT = int(os.environ.get("ALPHA_INSIDER_TIMEOUT", "10"))

# Strategy selector auto-tuning
STRATEGY_SELECTOR_ENABLED = os.environ.get("STRATEGY_SELECTOR_ENABLED", "true").lower() == "true"
STRATEGY_MIN_TRADES = int(os.environ.get("STRATEGY_MIN_TRADES", "5"))  # min trades before scoring


# Mask to constrain Python's arbitrary-precision hash to a 32-bit unsigned
# integer, ensuring a reproducible seed range for random.Random.
_SEED_MASK = 0xFFFFFFFF


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── MiroFish Swarm Intelligence ───────────────────────────────────────────────

class _MiroFishAgent:
    """A single simulated market participant agent in the MiroFish swarm.

    Each agent has its own personality traits (optimism bias, herd tendency,
    expertise level) that govern how it processes market signals and how much
    it is influenced by the emerging crowd consensus — mirroring the
    autonomous agent design of the full MiroFish prediction engine.
    """

    __slots__ = ("optimism_bias", "herd_tendency", "expertise", "belief")

    def __init__(self, rng: random.Random) -> None:
        self.optimism_bias = rng.gauss(0, 0.15)     # bullish (+) / bearish (-) personality
        self.herd_tendency = rng.uniform(0.1, 0.8)  # susceptibility to crowd opinion
        self.expertise = rng.uniform(0.3, 1.0)      # signal-processing quality
        self.belief = 0.5                            # current probability estimate

    def update(self, signal: float, crowd_belief: float, rng: random.Random) -> None:
        noise = rng.gauss(0, (1.0 - self.expertise) * 0.08)
        raw = signal + self.optimism_bias * 0.1 + noise
        blended = (1 - self.herd_tendency) * raw + self.herd_tendency * crowd_belief
        self.belief = max(0.02, min(0.98, blended))


class MiroFishPredictor:
    """Lightweight MiroFish-inspired swarm intelligence predictor.

    Simulates N autonomous agents with distinct personality profiles to estimate
    the probability of a prediction-market outcome resolving YES.  Each agent
    seeds its initial belief from the current market price plus Gaussian noise,
    then iteratively updates by blending its own signal processing with the
    emerging crowd consensus — capturing the collective-behaviour dynamic that
    the full MiroFish engine models with LLM-driven agents.

    Optional context signals (sentiment, volume_trend, news_impact in [-1, 1])
    shift the underlying signal fed to each agent, allowing external research
    from the mirofish-researcher agent to be incorporated.
    """

    def __init__(self, n_agents: int = 200, n_rounds: int = 15) -> None:
        self.n_agents = n_agents
        self.n_rounds = n_rounds

    def predict(
        self,
        market_id: str,
        current_price: float,
        context: Optional[dict] = None,
    ) -> dict:
        """Run the swarm simulation and return a probability estimate.

        Args:
            market_id:     Polymarket market identifier (used as deterministic seed).
            current_price: Current YES price in [0, 1].
            context:       Optional signals dict with keys sentiment, volume_trend,
                           news_impact each in [-1, 1].

        Returns:
            dict with prob_yes, prob_no, confidence, agent_agreement,
            predicted_move, sim_agents, sim_rounds, current_price.
        """
        ctx = context or {}
        seed = hash(f"{market_id}:{current_price:.4f}") & _SEED_MASK
        rng = random.Random(seed)

        signal = self._compute_signal(current_price, ctx)
        agents = [_MiroFishAgent(rng) for _ in range(self.n_agents)]
        for a in agents:
            a.belief = max(0.02, min(0.98,
                current_price + rng.gauss(0, 0.08) + a.optimism_bias * 0.05))

        for _ in range(self.n_rounds):
            crowd = sum(a.belief for a in agents) / len(agents)
            round_signal = max(0.02, min(0.98, signal + rng.gauss(0, 0.015)))
            for a in agents:
                a.update(round_signal, crowd, rng)

        beliefs = [a.belief for a in agents]
        prob_yes = sum(beliefs) / len(beliefs)
        variance = sum((b - prob_yes) ** 2 for b in beliefs) / len(beliefs)
        std_dev = variance ** 0.5
        bull = sum(1 for b in beliefs if b > 0.5)
        agreement = max(bull, len(beliefs) - bull) / len(beliefs)
        confidence = max(0.0, min(1.0, agreement - std_dev * 1.5))

        return {
            "market_id": market_id,
            "prob_yes": round(prob_yes, 4),
            "prob_no": round(1 - prob_yes, 4),
            "confidence": round(confidence, 4),
            "agent_agreement": round(agreement, 4),
            "std_dev": round(std_dev, 4),
            "predicted_move": (
                "UP" if prob_yes > current_price + 0.01
                else "DOWN" if prob_yes < current_price - 0.01
                else "FLAT"
            ),
            "sim_agents": self.n_agents,
            "sim_rounds": self.n_rounds,
            "current_price": current_price,
        }

    @staticmethod
    def _compute_signal(price: float, ctx: dict) -> float:
        sig = price
        sig += ctx.get("sentiment", 0.0) * 0.05
        sig += ctx.get("volume_trend", 0.0) * 0.03
        sig += ctx.get("news_impact", 0.0) * 0.04
        return max(0.02, min(0.98, sig))


# ── Polymarket client stub ────────────────────────────────────────────────────

@dataclass
class MarketQuote:
    market_id: str
    yes_price: float  # 0..1
    no_price: float   # 0..1


class PolymarketClient:
    """Stub client. Implement with a real Polymarket/CLOB client."""

    def get_quotes(self) -> list:
        return []

    def place_order_yes(self, market_id: str, usd_amount: float, max_price: float) -> str:
        raise NotImplementedError

    def place_order_no(self, market_id: str, usd_amount: float, max_price: float) -> str:
        raise NotImplementedError


# ── Alpha Insider strategy signals ────────────────────────────────────────────

class AlphaInsiderClient:
    """Fetches top-rated trading strategy signals from Alpha Insider.

    Alpha Insider (https://alphainsider.com) provides strategy performance
    ratings, ranking quantitative strategies by risk-adjusted returns.
    The API returns strategy scores we use to weight our trading decisions.

    Works in degraded mode (returns neutral signals) when:
    - No ALPHA_INSIDER_API_KEY is set
    - The API is unreachable
    """

    _CACHE_TTL = 3600  # Re-fetch strategies every hour

    def __init__(self) -> None:
        self._cache: dict = {}
        self._cache_ts: float = 0.0

    def _fetch(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make an authenticated GET request to the Alpha Insider API."""
        if not ALPHA_INSIDER_API_KEY:
            return None
        qs = urllib.parse.urlencode({**(params or {}), "apiKey": ALPHA_INSIDER_API_KEY})
        url = f"{ALPHA_INSIDER_URL}/{endpoint.lstrip('/')}?{qs}"
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "AI-Employee/1.0"},
            )
            with urllib.request.urlopen(req, timeout=ALPHA_INSIDER_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            print(f"[{now_iso()}] alpha-insider: fetch error for {endpoint}: {exc}")
            return None

    def get_top_strategies(self, limit: int = 10) -> list:
        """Return top-rated strategies sorted by performance score."""
        now_ts = time.time()
        if now_ts - self._cache_ts < self._CACHE_TTL and self._cache.get("strategies"):
            return self._cache["strategies"]

        data = self._fetch("strategies", {"limit": limit, "sort": "performance", "order": "desc"})
        strategies = []
        if data and isinstance(data, dict):
            raw = data.get("strategies") or data.get("data") or data.get("results") or []
            for s in raw:
                strategies.append({
                    "id": s.get("id", s.get("strategy_id", "")),
                    "name": s.get("name", ""),
                    "score": float(s.get("score", s.get("performance_score", 0.5))),
                    "win_rate": float(s.get("win_rate", s.get("winRate", 0.5))),
                    "sharpe": float(s.get("sharpe_ratio", s.get("sharpe", 1.0))),
                    "avg_edge": float(s.get("avg_edge", s.get("averageEdge", 0.0))),
                    "description": s.get("description", ""),
                })

        self._cache = {"strategies": strategies}
        self._cache_ts = now_ts
        return strategies

    def get_market_signal(self, market_id: str) -> Optional[dict]:
        """Get Alpha Insider's signal for a specific market."""
        data = self._fetch(f"signals/{market_id}")
        if not data:
            return None
        return {
            "market_id": market_id,
            "signal": data.get("signal", 0.0),       # -1 (strong NO) to +1 (strong YES)
            "confidence": data.get("confidence", 0.5),
            "strategy_id": data.get("strategy_id", ""),
            "source": "alpha_insider",
        }

    def get_strategy_signal_adjustment(self, strategies: list) -> float:
        """Compute an overall signal adjustment factor from top strategies.

        Returns a value in [-0.1, +0.1] to be added to the probability estimate.
        Positive = strategies suggest over-weighting YES positions.
        """
        if not strategies:
            return 0.0
        total_weight = sum(s.get("score", 0.5) for s in strategies)
        if total_weight == 0:
            return 0.0
        # Weight strategies by their performance score
        weighted_edge = sum(s.get("avg_edge", 0.0) * s.get("score", 0.5) for s in strategies)
        adjustment = (weighted_edge / total_weight) * 0.5  # Scale down to safe range
        return max(-0.10, min(0.10, adjustment))


# ── Strategy performance tracker ─────────────────────────────────────────────

@dataclass
class StrategyConfig:
    """A parameter configuration variant being evaluated."""
    edge_threshold: float
    position_size: float
    mirofish_weight: float       # 0..1 weight for inline MiroFish (rest = researcher)
    trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    score: float = 0.0

    def update_score(self) -> None:
        if self.trades >= STRATEGY_MIN_TRADES:
            win_rate = self.wins / self.trades if self.trades else 0.0
            avg_pnl = self.total_pnl / self.trades if self.trades else 0.0
            self.score = win_rate * 0.6 + min(1.0, avg_pnl / 10.0) * 0.4
        else:
            self.score = 0.0  # Not enough data yet

    def to_dict(self) -> dict:
        return {
            "edge_threshold": self.edge_threshold,
            "position_size": self.position_size,
            "mirofish_weight": self.mirofish_weight,
            "trades": self.trades,
            "wins": self.wins,
            "total_pnl": self.total_pnl,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyConfig":
        cfg = cls(
            edge_threshold=d.get("edge_threshold", EDGE_THRESHOLD),
            position_size=d.get("position_size", MAX_POSITION_USD),
            mirofish_weight=d.get("mirofish_weight", 0.4),
        )
        cfg.trades = d.get("trades", 0)
        cfg.wins = d.get("wins", 0)
        cfg.total_pnl = d.get("total_pnl", 0.0)
        cfg.score = d.get("score", 0.0)
        return cfg


class StrategySelector:
    """Tracks performance of parameter configurations and selects the best.

    Maintains a small set of strategy variants (epsilon-greedy exploration):
    - Always uses the best-performing variant (exploitation)
    - Occasionally tries an under-tested variant (exploration)
    - Records trade outcomes to update scores
    """

    _EXPLORE_RATE = 0.15  # 15% chance to explore a less-tested variant

    def __init__(self) -> None:
        self._configs: list[StrategyConfig] = self._load_or_init()

    def _load_or_init(self) -> list:
        if STRATEGY_PERF_FILE.exists():
            try:
                data = json.loads(STRATEGY_PERF_FILE.read_text())
                configs = [StrategyConfig.from_dict(c) for c in data.get("configs", [])]
                if configs:
                    return configs
            except Exception:
                pass
        # Default: explore a grid of edge thresholds and position sizes
        configs = []
        for edge in (0.05, 0.07, 0.10, 0.12):
            for mf_w in (0.3, 0.5):
                configs.append(StrategyConfig(
                    edge_threshold=edge,
                    position_size=MAX_POSITION_USD,
                    mirofish_weight=mf_w,
                ))
        return configs

    def save(self) -> None:
        STRATEGY_PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
        STRATEGY_PERF_FILE.write_text(json.dumps(
            {"configs": [c.to_dict() for c in self._configs], "updated_at": now_iso()},
            indent=2,
        ))

    def best(self) -> StrategyConfig:
        """Return the current best-performing config (or least-tested for exploration)."""
        scored = [c for c in self._configs if c.trades >= STRATEGY_MIN_TRADES]
        if not scored or random.random() < self._EXPLORE_RATE:
            # Explore: pick the config with fewest trades
            return min(self._configs, key=lambda c: c.trades)
        return max(scored, key=lambda c: c.score)

    def record_outcome(self, config: StrategyConfig, win: bool, pnl: float) -> None:
        """Update a config's performance record after a trade resolves."""
        config.trades += 1
        if win:
            config.wins += 1
        config.total_pnl += pnl
        config.update_score()
        self.save()

    def summary(self) -> list:
        return sorted(
            [c.to_dict() for c in self._configs],
            key=lambda c: c["score"], reverse=True,
        )


# ── Strategy ──────────────────────────────────────────────────────────────────

class Strategy:
    """Trading strategy that blends researcher estimates, MiroFish simulation, and Alpha Insider.

    Probability estimate is built from up to three sources, using the currently
    selected StrategyConfig weights:
      - Researcher estimate (from polymarket_estimates.json): 60% base weight
      - Inline MiroFish simulation: 40% base weight (adjustable by StrategyConfig)
      - Alpha Insider adjustment: additive ±0.10 signal overlay
    """

    def __init__(
        self,
        estimates_path: Path,
        predictor: Optional[MiroFishPredictor] = None,
        alpha_client: Optional[AlphaInsiderClient] = None,
        selector: Optional[StrategySelector] = None,
    ) -> None:
        self.estimates_path = estimates_path
        self.predictor = predictor
        self.alpha_client = alpha_client
        self.selector = selector

    def load_estimates(self) -> dict:
        if not self.estimates_path.exists():
            return {}
        try:
            return json.loads(self.estimates_path.read_text())
        except Exception:
            return {}

    def decide(self, quote: MarketQuote, est_prob: Optional[float]) -> Optional[dict]:
        # Get current best strategy config
        cfg = self.selector.best() if self.selector and STRATEGY_SELECTOR_ENABLED else None
        mf_weight = cfg.mirofish_weight if cfg else 0.4
        edge_thr = cfg.edge_threshold if cfg else EDGE_THRESHOLD
        pos_size = cfg.position_size if cfg else MAX_POSITION_USD

        mirofish_result: Optional[dict] = None
        if self.predictor is not None:
            mirofish_result = self.predictor.predict(quote.market_id, quote.yes_price)
            if est_prob is not None:
                prob = est_prob * (1 - mf_weight) + mirofish_result["prob_yes"] * mf_weight
            else:
                prob = mirofish_result["prob_yes"]
        else:
            prob = est_prob

        if prob is None:
            return None

        # Apply Alpha Insider signal adjustment
        alpha_adjustment = 0.0
        alpha_signal = None
        if self.alpha_client and ALPHA_INSIDER_ENABLED:
            try:
                strategies = self.alpha_client.get_top_strategies(limit=5)
                alpha_adjustment = self.alpha_client.get_strategy_signal_adjustment(strategies)
                # Also check market-specific signal
                mkt_signal = self.alpha_client.get_market_signal(quote.market_id)
                if mkt_signal:
                    alpha_adjustment += mkt_signal.get("signal", 0.0) * 0.05
                    alpha_signal = mkt_signal
            except Exception:
                pass

        prob = max(0.01, min(0.99, prob + alpha_adjustment))
        edge = prob - quote.yes_price

        if edge >= edge_thr:
            decision = {
                "side": "YES",
                "edge": round(edge, 4),
                "est_prob": round(prob, 4),
                "price": quote.yes_price,
                "usd": pos_size,
                "max_price": min(0.999, quote.yes_price * 1.01),
                "strategy_config": cfg.to_dict() if cfg else None,
                "alpha_adjustment": round(alpha_adjustment, 4),
            }
            if mirofish_result:
                decision["mirofish"] = mirofish_result
            if alpha_signal:
                decision["alpha_signal"] = alpha_signal
            return decision
        return None


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    predictor = (
        MiroFishPredictor(n_agents=MIROFISH_AGENTS, n_rounds=MIROFISH_ROUNDS)
        if MIROFISH_ENABLED
        else None
    )
    client = PolymarketClient()
    alpha_client = AlphaInsiderClient() if ALPHA_INSIDER_ENABLED else None
    selector = StrategySelector() if STRATEGY_SELECTOR_ENABLED else None
    strategy = Strategy(
        AI_HOME / "config" / "polymarket_estimates.json",
        predictor=predictor,
        alpha_client=alpha_client,
        selector=selector,
    )

    ai_key_set = bool(ALPHA_INSIDER_API_KEY)
    print(
        f"[{now_iso()}] polymarket-trader started "
        f"LIVE={LIVE_TRADING} KILL={KILL_SWITCH} allow_markets={ALLOW_MARKETS} "
        f"mirofish={MIROFISH_ENABLED}(agents={MIROFISH_AGENTS},rounds={MIROFISH_ROUNDS}) "
        f"alpha_insider={ALPHA_INSIDER_ENABLED}(key={'set' if ai_key_set else 'not set'}) "
        f"strategy_selector={STRATEGY_SELECTOR_ENABLED}"
    )

    while True:
        if KILL_SWITCH:
            write_state({
                "ts": now_iso(), "bot": "polymarket-trader",
                "status": "killed", "note": "KILL_SWITCH=true", "live": False,
            })
            time.sleep(5)
            continue

        estimates = strategy.load_estimates()
        quotes = client.get_quotes()

        # Fetch Alpha Insider top strategies for logging
        alpha_strategies = []
        if alpha_client and ALPHA_INSIDER_ENABLED:
            try:
                alpha_strategies = alpha_client.get_top_strategies(limit=5)
            except Exception:
                pass

        actions = []
        for q in quotes:
            if ALLOW_MARKETS and q.market_id not in ALLOW_MARKETS:
                continue
            est = estimates.get(q.market_id)
            decision = strategy.decide(q, est)
            if decision:
                actions.append({"market_id": q.market_id, **decision})

        executed = []
        for a in actions:
            if not LIVE_TRADING:
                executed.append({**a, "executed": False, "mode": "paper"})
                continue
            try:
                if a["side"] == "YES":
                    oid = client.place_order_yes(a["market_id"], a["usd"], a["max_price"])
                else:
                    oid = client.place_order_no(a["market_id"], a["usd"], a["max_price"])
                executed.append({**a, "executed": True, "order_id": oid, "mode": "live"})
            except Exception as e:
                executed.append({**a, "executed": False, "error": str(e), "mode": "live"})

        # Get current best strategy config for state reporting
        best_cfg = selector.best().to_dict() if selector and STRATEGY_SELECTOR_ENABLED else None

        write_state({
            "ts": now_iso(),
            "bot": "polymarket-trader",
            "status": "running",
            "live": LIVE_TRADING,
            "kill": KILL_SWITCH,
            "mirofish_enabled": MIROFISH_ENABLED,
            "alpha_insider_enabled": ALPHA_INSIDER_ENABLED,
            "alpha_insider_key_set": ai_key_set,
            "alpha_strategies_count": len(alpha_strategies),
            "best_strategy_config": best_cfg,
            "strategy_configs": selector.summary()[:3] if selector else [],
            "actions_found": len(actions),
            "executed": executed[:50],
        })

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

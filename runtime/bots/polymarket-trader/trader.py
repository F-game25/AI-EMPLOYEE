"""Polymarket Trader bot with MiroFish swarm intelligence integration.

PAPER trading mode by default. Set LIVE_TRADING=true in polymarket-trader.env to enable live orders.
State is written to ~/.ai-employee/state/polymarket-trader.state.json

MiroFish integration: the inline MiroFishPredictor runs a lightweight swarm
simulation on each market quote to estimate the probability of YES resolution.
The mirofish-researcher agent (if running) also writes deeper estimates to
~/.ai-employee/config/polymarket_estimates.json which are blended with the
inline simulation for higher-quality signals.
"""
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "polymarket-trader.state.json"

POLL_SECONDS = int(os.environ.get("PM_POLL_SECONDS", "60"))
LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() == "true"
KILL_SWITCH = os.environ.get("KILL_SWITCH", "false").lower() == "true"
MAX_POSITION_USD = float(os.environ.get("MAX_POSITION_USD", "25"))
EDGE_THRESHOLD = float(os.environ.get("EDGE_THRESHOLD", "0.07"))
ALLOW_MARKETS = [m.strip() for m in os.environ.get("ALLOW_MARKETS", "").split(",") if m.strip()]
MIROFISH_ENABLED = os.environ.get("MIROFISH_ENABLED", "true").lower() == "true"
MIROFISH_AGENTS = int(os.environ.get("MIROFISH_AGENTS", "200"))
MIROFISH_ROUNDS = int(os.environ.get("MIROFISH_ROUNDS", "15"))


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
        seed = hash(f"{market_id}:{current_price:.4f}") & 0xFFFFFFFF
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


# ── Strategy ──────────────────────────────────────────────────────────────────

class Strategy:
    """Trading strategy that blends researcher estimates with inline MiroFish simulation.

    When both a researcher estimate (from polymarket_estimates.json written by
    mirofish-researcher) and an inline MiroFish simulation are available, they
    are combined — researcher estimates carry 60 % weight, inline simulation
    40 % — to produce the final probability used for edge calculation.
    """

    def __init__(
        self,
        estimates_path: Path,
        predictor: Optional[MiroFishPredictor] = None,
    ) -> None:
        self.estimates_path = estimates_path
        self.predictor = predictor

    def load_estimates(self) -> dict:
        if not self.estimates_path.exists():
            return {}
        try:
            return json.loads(self.estimates_path.read_text())
        except Exception:
            return {}

    def decide(self, quote: MarketQuote, est_prob: Optional[float]) -> Optional[dict]:
        mirofish_result: Optional[dict] = None
        if self.predictor is not None:
            mirofish_result = self.predictor.predict(quote.market_id, quote.yes_price)
            if est_prob is not None:
                # Blend: researcher estimate (60 %) + inline simulation (40 %)
                prob = est_prob * 0.6 + mirofish_result["prob_yes"] * 0.4
            else:
                prob = mirofish_result["prob_yes"]
        else:
            prob = est_prob

        if prob is None:
            return None

        edge = prob - quote.yes_price
        if edge >= EDGE_THRESHOLD:
            decision = {
                "side": "YES",
                "edge": round(edge, 4),
                "est_prob": round(prob, 4),
                "price": quote.yes_price,
                "usd": MAX_POSITION_USD,
                "max_price": min(0.999, quote.yes_price * 1.01),
            }
            if mirofish_result:
                decision["mirofish"] = mirofish_result
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
    strategy = Strategy(
        AI_HOME / "config" / "polymarket_estimates.json",
        predictor=predictor,
    )

    print(
        f"[{now_iso()}] polymarket-trader started "
        f"LIVE={LIVE_TRADING} KILL={KILL_SWITCH} allow_markets={ALLOW_MARKETS} "
        f"mirofish={MIROFISH_ENABLED}(agents={MIROFISH_AGENTS},rounds={MIROFISH_ROUNDS})"
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

        write_state({
            "ts": now_iso(),
            "bot": "polymarket-trader",
            "status": "running",
            "live": LIVE_TRADING,
            "kill": KILL_SWITCH,
            "mirofish_enabled": MIROFISH_ENABLED,
            "actions_found": len(actions),
            "executed": executed[:50],
        })

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

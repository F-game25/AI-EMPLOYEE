"""MiroFish Market Researcher — standalone market research agent.

Uses MiroFish swarm-intelligence simulation to predict Polymarket outcome
probabilities and write estimates to the shared config file so that the
polymarket-trader can consume them.

How it works
────────────
Inspired by the MiroFish open-source engine (github.com/666ghj/MiroFish),
this agent creates N autonomous agents with distinct personality profiles
(optimism bias, herd tendency, expertise) that each form an independent
probability estimate for a market outcome.  The agents run for multiple
interaction rounds, iteratively blending their own signal processing with
the emerging crowd consensus — capturing the collective-behaviour dynamics
that MiroFish models in its full LLM-driven engine.

For richer signals, populate ~/.ai-employee/config/mirofish_signals.json:
  {
    "<market-id>": {
      "sentiment":     0.3,   // -1 (very bearish) to +1 (very bullish)
      "volume_trend":  0.1,   // -1 (declining)    to +1 (increasing)
      "news_impact":   0.2    // -1 (negative)     to +1 (positive)
    }
  }

Outputs
───────
• ~/.ai-employee/config/polymarket_estimates.json  — prob_yes per market
  (consumed by polymarket-trader)
• ~/.ai-employee/state/mirofish-researcher.state.json  — full research report
"""
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "mirofish-researcher.state.json"
ESTIMATES_FILE = AI_HOME / "config" / "polymarket_estimates.json"
SIGNALS_FILE = AI_HOME / "config" / "mirofish_signals.json"

RESEARCH_INTERVAL = int(os.environ.get("MIROFISH_RESEARCH_INTERVAL", "300"))
MIROFISH_AGENTS = int(os.environ.get("MIROFISH_AGENTS", "500"))
MIROFISH_ROUNDS = int(os.environ.get("MIROFISH_ROUNDS", "20"))
MIROFISH_SCENARIOS = int(os.environ.get("MIROFISH_SCENARIOS", "5"))
RESEARCH_MARKETS = [
    m.strip() for m in os.environ.get("RESEARCH_MARKETS", "").split(",") if m.strip()
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Mask to constrain Python's arbitrary-precision hash to a 32-bit unsigned
# integer, ensuring a reproducible seed range for random.Random.
_SEED_MASK = 0xFFFFFFFF

# Gaussian noise applied to each context signal across scenario runs.
_SCENARIO_SENTIMENT_NOISE = 0.10
_SCENARIO_VOLUME_NOISE = 0.05
_SCENARIO_NEWS_NOISE = 0.05


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_estimates() -> dict:
    if not ESTIMATES_FILE.exists():
        return {}
    try:
        return json.loads(ESTIMATES_FILE.read_text())
    except Exception:
        return {}


def save_estimates(estimates: dict) -> None:
    ESTIMATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ESTIMATES_FILE.write_text(json.dumps(estimates, indent=2))


def load_signals() -> dict:
    """Load optional external signals from the mirofish_signals.json config."""
    if not SIGNALS_FILE.exists():
        return {}
    try:
        return json.loads(SIGNALS_FILE.read_text())
    except Exception:
        return {}


# ── MiroFish Swarm Intelligence ───────────────────────────────────────────────

class _MiroFishAgent:
    """A single simulated market participant agent in the MiroFish swarm."""

    __slots__ = ("optimism_bias", "herd_tendency", "expertise", "belief")

    def __init__(self, rng: random.Random) -> None:
        self.optimism_bias = rng.gauss(0, 0.15)
        self.herd_tendency = rng.uniform(0.1, 0.8)
        self.expertise = rng.uniform(0.3, 1.0)
        self.belief = 0.5

    def update(self, signal: float, crowd_belief: float, rng: random.Random) -> None:
        noise = rng.gauss(0, (1.0 - self.expertise) * 0.08)
        raw = signal + self.optimism_bias * 0.1 + noise
        blended = (1 - self.herd_tendency) * raw + self.herd_tendency * crowd_belief
        self.belief = max(0.02, min(0.98, blended))


class MiroFishPredictor:
    """Deep MiroFish swarm predictor used by the researcher agent.

    Runs more agents and more rounds than the inline trader predictor,
    plus a multi-scenario analysis to produce confidence intervals.
    """

    def __init__(self, n_agents: int = 500, n_rounds: int = 20) -> None:
        self.n_agents = n_agents
        self.n_rounds = n_rounds

    def predict(
        self,
        market_id: str,
        current_price: float,
        context: Optional[dict] = None,
    ) -> dict:
        """Run swarm simulation and return a probability estimate dict."""
        ctx = context or {}
        # Seed is hour-granular: [:13] captures "YYYY-MM-DDTHH" so results
        # refresh every hour even when the market price has not changed.
        seed = hash(f"{market_id}:{current_price:.4f}:{now_iso()[:13]}") & _SEED_MASK
        rng = random.Random(seed)

        signal = self._compute_signal(current_price, ctx)
        agents = [_MiroFishAgent(rng) for _ in range(self.n_agents)]
        for a in agents:
            a.belief = max(0.02, min(0.98,
                current_price + rng.gauss(0, 0.08) + a.optimism_bias * 0.05))

        for phase in range(self.n_rounds):
            # Reduce noise in later phases (simulating market price discovery)
            round_noise = 0.02 * max(0.2, 1 - phase / self.n_rounds)
            crowd = sum(a.belief for a in agents) / len(agents)
            round_signal = max(0.02, min(0.98, signal + rng.gauss(0, round_noise)))
            for a in agents:
                a.update(round_signal, crowd, rng)

        beliefs = [a.belief for a in agents]
        prob_yes = sum(beliefs) / len(beliefs)
        variance = sum((b - prob_yes) ** 2 for b in beliefs) / len(beliefs)
        std_dev = variance ** 0.5
        bull = sum(1 for b in beliefs if b > 0.5)
        agreement = max(bull, len(beliefs) - bull) / len(beliefs)
        confidence = max(0.0, min(1.0, agreement - std_dev * 1.5))

        very_bull = sum(1 for b in beliefs if b > 0.7) / len(beliefs)
        very_bear = sum(1 for b in beliefs if b < 0.3) / len(beliefs)

        return {
            "market_id": market_id,
            "prob_yes": round(prob_yes, 4),
            "prob_no": round(1 - prob_yes, 4),
            "confidence": round(confidence, 4),
            "agent_agreement": round(agreement, 4),
            "std_dev": round(std_dev, 4),
            "distribution": {
                "very_bullish": round(very_bull, 3),
                "neutral": round(max(0, 1 - very_bull - very_bear), 3),
                "very_bearish": round(very_bear, 3),
            },
            "predicted_move": (
                "UP" if prob_yes > current_price + 0.01
                else "DOWN" if prob_yes < current_price - 0.01
                else "FLAT"
            ),
            "sim_agents": self.n_agents,
            "sim_rounds": self.n_rounds,
            "current_price": current_price,
            "ts": now_iso(),
        }

    def run_scenarios(
        self,
        market_id: str,
        current_price: float,
        n_scenarios: int = 5,
        context: Optional[dict] = None,
    ) -> dict:
        """Run N independent scenario simulations and return aggregated statistics.

        Each scenario slightly perturbs the context signals to model uncertainty
        in the input data, producing a confidence interval around the estimate.
        """
        ctx = context or {}
        base_rng = random.Random(hash(f"scenarios:{market_id}") & _SEED_MASK)
        scenario_probs: list[float] = []

        for i in range(n_scenarios):
            scenario_ctx = {
                "sentiment":    ctx.get("sentiment", 0.0)    + base_rng.gauss(0, _SCENARIO_SENTIMENT_NOISE),
                "volume_trend": ctx.get("volume_trend", 0.0) + base_rng.gauss(0, _SCENARIO_VOLUME_NOISE),
                "news_impact":  ctx.get("news_impact", 0.0)  + base_rng.gauss(0, _SCENARIO_NEWS_NOISE),
            }
            result = self.predict(f"{market_id}_s{i}", current_price, scenario_ctx)
            scenario_probs.append(result["prob_yes"])

        mean_p = sum(scenario_probs) / len(scenario_probs)
        s_std = (
            sum((p - mean_p) ** 2 for p in scenario_probs) / len(scenario_probs)
        ) ** 0.5

        return {
            "scenario_mean_prob_yes": round(mean_p, 4),
            "scenario_std": round(s_std, 4),
            "scenario_range": [
                round(min(scenario_probs), 4),
                round(max(scenario_probs), 4),
            ],
            "n_scenarios": n_scenarios,
        }

    @staticmethod
    def _compute_signal(price: float, ctx: dict) -> float:
        sig = price
        sig += ctx.get("sentiment", 0.0) * 0.05
        sig += ctx.get("volume_trend", 0.0) * 0.03
        sig += ctx.get("news_impact", 0.0) * 0.04
        return max(0.02, min(0.98, sig))


# ── Research loop ─────────────────────────────────────────────────────────────

def research_markets(
    predictor: MiroFishPredictor,
    markets: list,
    signals: dict,
    n_scenarios: int,
) -> dict:
    """Run MiroFish research on every market and return results keyed by market_id."""
    results: dict = {}
    for market_info in markets:
        if isinstance(market_info, str):
            market_id = market_info
            current_price = 0.5
            ctx = signals.get(market_id, {})
        else:
            market_id = market_info.get("id", market_info.get("market_id", "unknown"))
            current_price = float(
                market_info.get("yes_price", market_info.get("price", 0.5))
            )
            ctx = {**signals.get(market_id, {}), **market_info.get("context", {})}

        try:
            prediction = predictor.predict(market_id, current_price, ctx)
            scenario_analysis = predictor.run_scenarios(
                market_id, current_price, n_scenarios=n_scenarios, context=ctx
            )
            results[market_id] = {**prediction, "scenario_analysis": scenario_analysis}
            print(
                f"[{now_iso()}] mirofish-researcher: {market_id} "
                f"prob_yes={prediction['prob_yes']:.3f} "
                f"move={prediction['predicted_move']} "
                f"confidence={prediction['confidence']:.3f}"
            )
        except Exception as exc:
            print(f"[{now_iso()}] mirofish-researcher: ERROR on {market_id}: {exc}")

    return results


def main() -> None:
    predictor = MiroFishPredictor(n_agents=MIROFISH_AGENTS, n_rounds=MIROFISH_ROUNDS)
    print(
        f"[{now_iso()}] mirofish-researcher started "
        f"interval={RESEARCH_INTERVAL}s "
        f"agents={MIROFISH_AGENTS} rounds={MIROFISH_ROUNDS} "
        f"scenarios={MIROFISH_SCENARIOS}"
    )

    while True:
        signals = load_signals()
        markets_to_research = RESEARCH_MARKETS or list(signals.keys())

        if not markets_to_research:
            print(
                f"[{now_iso()}] mirofish-researcher: no markets configured. "
                f"Set RESEARCH_MARKETS env var or populate {SIGNALS_FILE}"
            )
            write_state({
                "bot": "mirofish-researcher",
                "ts": now_iso(),
                "status": "idle",
                "note": (
                    "No markets configured. "
                    "Set RESEARCH_MARKETS in mirofish-researcher.env "
                    "or add market IDs to config/mirofish_signals.json"
                ),
                "mirofish_agents": MIROFISH_AGENTS,
                "mirofish_rounds": MIROFISH_ROUNDS,
            })
            time.sleep(RESEARCH_INTERVAL)
            continue

        research = research_markets(
            predictor, markets_to_research, signals, n_scenarios=MIROFISH_SCENARIOS
        )

        # Update shared estimates file consumed by polymarket-trader
        estimates = load_estimates()
        for market_id, result in research.items():
            estimates[market_id] = result["prob_yes"]
        save_estimates(estimates)

        write_state({
            "bot": "mirofish-researcher",
            "ts": now_iso(),
            "status": "running",
            "mirofish_agents": MIROFISH_AGENTS,
            "mirofish_rounds": MIROFISH_ROUNDS,
            "mirofish_scenarios": MIROFISH_SCENARIOS,
            "markets_analyzed": len(research),
            "research": research,
        })
        print(
            f"[{now_iso()}] mirofish-researcher: cycle complete, "
            f"analyzed {len(research)} markets"
        )

        time.sleep(RESEARCH_INTERVAL)


if __name__ == "__main__":
    main()

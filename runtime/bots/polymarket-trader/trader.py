import os
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "run" / "polymarket-trader.state.json"

POLL_SECONDS = int(os.environ.get("PM_POLL_SECONDS", "5"))
LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() == "true"
KILL_SWITCH = os.environ.get("KILL_SWITCH", "false").lower() == "true"

MAX_POSITION_USD = float(os.environ.get("MAX_POSITION_USD", "25"))
EDGE_THRESHOLD = float(os.environ.get("EDGE_THRESHOLD", "0.07"))
ALLOW_MARKETS = [m.strip() for m in os.environ.get("ALLOW_MARKETS", "").split(",") if m.strip()]

def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

@dataclass
class MarketQuote:
    market_id: str
    yes_price: float
    no_price: float

class PolymarketClient:
    def get_quotes(self) -> list[MarketQuote]:
        return []
    def place_order_yes(self, market_id: str, usd_amount: float, max_price: float) -> str:
        raise NotImplementedError

class Strategy:
    def __init__(self, estimates_path: Path):
        self.estimates_path = estimates_path

    def load_estimates(self) -> dict[str, float]:
        if not self.estimates_path.exists():
            return {}
        return json.loads(self.estimates_path.read_text())

    def decide(self, quote: MarketQuote, est_prob: Optional[float]) -> Optional[dict]:
        if est_prob is None:
            return None
        edge = est_prob - quote.yes_price
        if edge >= EDGE_THRESHOLD:
            return {
                "side": "YES",
                "edge": edge,
                "est_prob": est_prob,
                "price": quote.yes_price,
                "usd": MAX_POSITION_USD,
                "max_price": min(0.999, quote.yes_price * 1.01),
            }
        return None

def main():
    client = PolymarketClient()
    strategy = Strategy(AI_HOME / "config" / "polymarket_estimates.json")
    print(f"polymarket-trader started LIVE_TRADING={LIVE_TRADING} KILL_SWITCH={KILL_SWITCH} allow_markets={ALLOW_MARKETS}")

    while True:
        if KILL_SWITCH:
            write_state({"ts": time.time(), "status": "killed"})
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
            executed.append({**a, "executed": False, "error": "Client not implemented", "mode": "live"})

        write_state({"ts": time.time(), "actions_found": len(actions), "executed": executed[:50]})
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()

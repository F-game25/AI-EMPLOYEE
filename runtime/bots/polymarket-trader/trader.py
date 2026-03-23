"""Polymarket Trader bot.

PAPER trading mode by default. Set LIVE_TRADING=true in polymarket-trader.env to enable live orders.
State is written to ~/.ai-employee/state/polymarket-trader.state.json
"""
import json
import os
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


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


class Strategy:
    def __init__(self, estimates_path: Path):
        self.estimates_path = estimates_path

    def load_estimates(self) -> dict:
        if not self.estimates_path.exists():
            return {}
        try:
            return json.loads(self.estimates_path.read_text())
        except Exception:
            return {}

    def decide(self, quote: MarketQuote, est_prob: Optional[float]) -> Optional[dict]:
        if est_prob is None:
            return None
        edge = est_prob - quote.yes_price
        if edge >= EDGE_THRESHOLD:
            return {
                "side": "YES",
                "edge": round(edge, 4),
                "est_prob": est_prob,
                "price": quote.yes_price,
                "usd": MAX_POSITION_USD,
                "max_price": min(0.999, quote.yes_price * 1.01),
            }
        return None


def main():
    client = PolymarketClient()
    strategy = Strategy(AI_HOME / "config" / "polymarket_estimates.json")

    print(
        f"[{now_iso()}] polymarket-trader started "
        f"LIVE={LIVE_TRADING} KILL={KILL_SWITCH} allow_markets={ALLOW_MARKETS}"
    )

    while True:
        if KILL_SWITCH:
            write_state({"ts": now_iso(), "bot": "polymarket-trader", "status": "killed",
                         "note": "KILL_SWITCH=true", "live": False})
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
            "actions_found": len(actions),
            "executed": executed[:50],
        })

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

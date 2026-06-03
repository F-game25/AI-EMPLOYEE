"""Product Scout — monitors configured niches and flags high-scoring products via HITL.

Reads ECOM_WATCH_NICHES (comma-separated, default: "accessoires,kantoorartikelen,fitness"),
calls product_researcher.research_products() for each, and submits a HITL notification
for any product scoring >7 on demand, marge AND concurrentie simultaneously.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure runtime/ is on path when executed standalone
_runtime = Path(__file__).resolve().parents[3] / "runtime"
if str(_runtime) not in sys.path:
    sys.path.insert(0, str(_runtime))

from agents.base import BaseAgent


class ProductScoutAgent(BaseAgent):
    agent_id = "product-scout"
    required_fields = ()  # no required fields — reads env

    def execute(self, payload: dict) -> dict:
        raw_niches = os.environ.get("ECOM_WATCH_NICHES", "accessoires,kantoorartikelen,fitness")
        niches = [n.strip() for n in raw_niches.split(",") if n.strip()]
        markt = payload.get("markt", "nl")
        min_marge = int(payload.get("min_marge", 30))

        from core.product_researcher import research_products
        from core.hitl_gate import get_hitl_gate

        gate = get_hitl_gate()
        all_flagged: list[dict] = []
        summaries: list[dict] = []

        for niche in niches:
            try:
                result = research_products(niche, markt, min_marge)
            except Exception as exc:
                summaries.append({"niche": niche, "ok": False, "error": str(exc)})
                continue

            producten = result.get("producten", [])
            high_scorers = [
                p for p in producten
                if p.get("demand", 0) > 7
                and p.get("marge", 0) > 7
                and p.get("concurrentie", 0) > 7
            ]

            for product in high_scorers:
                hitl_result = gate.require_approval(
                    agent=self.agent_id,
                    action=f"Hoog-scorend product gevonden: {product['naam']} (niche: {niche})",
                    payload={
                        "product": product,
                        "niche": niche,
                        "markt": markt,
                        "scores": {
                            "demand": product["demand"],
                            "marge": product["marge"],
                            "concurrentie": product["concurrentie"],
                        },
                    },
                    submitted_by=self.agent_id,
                    blocking=False,
                )
                all_flagged.append({
                    "naam": product["naam"],
                    "niche": niche,
                    "hitl_request_id": hitl_result.get("request_id"),
                    "demand": product["demand"],
                    "marge": product["marge"],
                    "concurrentie": product["concurrentie"],
                })

            summaries.append({
                "niche": niche,
                "ok": result.get("ok", False),
                "producten_gevonden": len(producten),
                "hoog_scorend": len(high_scorers),
            })

        return {
            "ok": True,
            "niches_gescand": len(niches),
            "hoog_scorende_producten": all_flagged,
            "hitl_notifications": len(all_flagged),
            "samenvatting": summaries,
        }

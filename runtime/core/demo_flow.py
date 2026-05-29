"""Demo-website sales flow — entry point for the full pipeline.

Usage (Python):
    from core.demo_flow import run_demo_flow

    result = run_demo_flow(
        bedrijfsnaam="Loodgieter Jansen",
        plaats="Brielle",
        branche="loodgieterswerk",
        diensten=["lekkage reparatie", "cv-ketel onderhoud", "badkamer installatie"],
        contact="06-12345678",
        prijs=299.0,
    )

Flow:
  1. Maak order aan (status: gevonden)
  2. Genereer HTML demo via demo_generator (status: demo_klaar)
  3. Zet order in HITL-gate ter_review (status: ter_review)
  4. Return order + HITL request_id zodat Lars kan goedkeuren

Hard limit: verwerkt altijd EXACT 1 bedrijf per aanroep.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_demo_flow(
    *,
    bedrijfsnaam: str,
    plaats: str,
    branche: str,
    diensten: list[str] | None = None,
    contact: str = "",
    prijs: float = 299.0,
) -> dict[str, Any]:
    """Run the full flow for ONE business. Returns a result dict."""

    # ── Stap 1: order aanmaken ─────────────────────────────────────────────────
    from core.orders_store import order_aanmaken, status_bijwerken
    order = order_aanmaken(
        bedrijfsnaam=bedrijfsnaam,
        plaats=plaats,
        branche=branche,
        contact=contact,
        prijs=prijs,
    )
    order_id = order["id"]
    logger.info("demo_flow: order aangemaakt %s voor '%s'", order_id, bedrijfsnaam)

    # ── Stap 2: demo genereren ─────────────────────────────────────────────────
    from core.demo_generator import genereer_demo
    gen = genereer_demo(
        bedrijfsnaam=bedrijfsnaam,
        plaats=plaats,
        branche=branche,
        diensten=diensten,
    )
    if gen["status"] != "ok":
        logger.error("demo_flow: generatie mislukt: %s", gen.get("error"))
        return {"status": "error", "stage": "demo_generatie", "error": gen.get("error"), "order": order}

    demo_pad = gen["path"]
    order = status_bijwerken(order_id, "demo_klaar", demo_pad=demo_pad)
    logger.info("demo_flow: demo klaar → %s", demo_pad)

    # ── Stap 3: naar HITL-gate (ter_review) ───────────────────────────────────
    from core.hitl_gate import get_hitl_gate
    gate = get_hitl_gate()

    hitl_result = gate.require_approval(
        agent="demo_flow",
        action=f"Demo-website goedkeuren: {bedrijfsnaam} ({plaats})",
        payload={
            "order_id":      order_id,
            "bedrijfsnaam":  bedrijfsnaam,
            "plaats":        plaats,
            "branche":       branche,
            "demo_pad":      demo_pad,
            "prijs":         prijs,
            "instructie":    (
                f"Open het HTML-bestand om de demo te bekijken:\n  {demo_pad}\n\n"
                "Keur goed (approve) als de demo verstuurbaar is, of wijs af (reject) "
                "om opnieuw te genereren."
            ),
        },
        submitted_by="demo_flow",
        blocking=False,  # niet-blokkend — Lars beslist via dashboard
    )

    order = status_bijwerken(order_id, "ter_review")
    logger.info(
        "demo_flow: order %s → ter_review | HITL request %s",
        order_id, hitl_result.get("request_id"),
    )

    return {
        "status":           "ter_review",
        "order":            order,
        "demo_pad":         demo_pad,
        "demo_bytes":       gen["bytes"],
        "hitl_request_id":  hitl_result.get("request_id"),
        "hitl_message":     hitl_result.get("message"),
    }


def goedkeuren(order_id: str, *, decided_by: str = "lars") -> dict[str, Any]:
    """Approve the HITL request for an order and set status → goedgekeurd."""
    from core.orders_store import order_ophalen, status_bijwerken
    from core.hitl_gate import get_hitl_gate

    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}

    gate = get_hitl_gate()
    pending = gate.pending_requests()
    req = next((r for r in pending if r["payload"].get("order_id") == order_id), None)
    if not req:
        return {"ok": False, "error": "Geen openstaand HITL-verzoek voor dit order"}

    gate.approve(req["id"], decided_by=decided_by)
    order = status_bijwerken(order_id, "goedgekeurd")
    return {"ok": True, "order": order}

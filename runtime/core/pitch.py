"""Pitch-generator en betalingsafhandeling voor de website-sales pipeline.

Workflow na blok 3:
  goedgekeurd → [genereer_pitch] → pitch klaar → Lars verstuurt ZELF
             → [markeer_gepitcht] → gepitcht
             → [markeer_akkoord]  → akkoord
             → [markeer_betaald]  → betaald
             → [markeer_live]     → live

NIETS gaat automatisch naar buiten. Lars stuurt de pitch zelf.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:latest")

# Lars' eigen PayPal.me link — stel in via env of ~/.ai-employee/.env
# Voorbeeld: PAYPAL_LINK=https://paypal.me/larsfluks
_PAYPAL_LINK = os.environ.get("PAYPAL_LINK", "https://paypal.me/jouwlink")

# BASE_URL for demo links sent to customers — set to your public URL or ngrok tunnel.
# Falls back to localhost only as a last resort; set this in .env for production use.
_BASE_URL = os.environ.get("BASE_URL", "http://localhost:8787").rstrip("/")

# Validate at import time — target is fully determined by env var, never by user input.
if not _OLLAMA_HOST.startswith(("http://", "https://")):
    raise ValueError(f"OLLAMA_HOST must start with http:// or https://, got: {_OLLAMA_HOST!r}")


def _llm(prompt: str, max_tokens: int = 350) -> str:
    payload = {
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "system": (
            "Je bent Lars, een Nederlandse freelancer die lokale bedrijven helpt "
            "aan hun eerste website. Schrijf vriendelijk, direct en lokaal — geen "
            "verkoopjargon. Schrijf als een echt persoon, niet als een bedrijf."
        ),
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    req = urllib.request.Request(
        f"{_OLLAMA_HOST}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310 — scheme validated above
        body = json.loads(resp.read())
    return body.get("response", "").strip()


def genereer_pitch(order_id: str, *, demo_url: str = "") -> dict[str, Any]:
    """Genereer een pitch-bericht voor een goedgekeurde order.

    Parameters
    ----------
    order_id  : ID van de order (moet status=goedgekeurd hebben).
    demo_url  : Optionele publieke URL van de demo (bv. file:// pad of gehoste link).
                Als leeg: het lokale bestandspad wordt gebruikt.

    Returns
    -------
    dict met 'pitch_tekst', 'paypal_link', 'order'.
    Zet de pitch_tekst ook op in het orders-record (kolom pitch_tekst als die
    bestaat; anders wordt hij alleen teruggegeven).
    """
    from core.orders_store import order_ophalen

    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}
    if order["status"] != "goedgekeurd":
        return {
            "ok": False,
            "error": f"Order heeft status '{order['status']}', verwacht 'goedgekeurd'",
        }

    naam    = order["bedrijfsnaam"]
    plaats  = order["plaats"]
    branche = order["branche"]
    prijs   = order["prijs"]
    demo    = demo_url or order.get("demo_pad", "")
    paypal  = f"{_PAYPAL_LINK}/{int(prijs)}" if not _PAYPAL_LINK.endswith(str(int(prijs))) else _PAYPAL_LINK

    demo_link = demo if demo.startswith("http") else f"http://localhost:8787/api/demos/{Path(demo).name}"

    prompt = (
        f"Schrijf een persoonlijk bericht (max 120 woorden) van Lars aan {naam} in {plaats}.\n"
        f"Verplichte structuur, in exact deze volgorde:\n"
        f"1. Begin met: 'Hoi {naam},' gevolgd door één zin over wat ze doen ({branche} in {plaats}).\n"
        f"2. Schrijf: 'Ik heb alvast een website voor jullie gemaakt, speciaal voor {branche} in {plaats}.'\n"
        f"3. Schrijf: 'Bekijk hem hier: {demo_link}'\n"
        f"4. Noem twee concrete dingen die op de site staan (passend bij {branche}).\n"
        f"5. Sluit af met: 'Laat even weten wat je ervan vindt — ik leg het graag toe.'\n"
        f"Daarna: 'Groeten, Lars'\n"
        f"GEEN prijs, GEEN betaallink, GEEN verkooptaal. Schrijf ALLEEN het bericht."
    )

    # Swarm mode: generate 3 pitch variants in parallel, pick strongest
    try:
        from core.swarm_engine import swarm_pitch
        result = swarm_pitch(prompt, context=f"Bedrijf: {naam}, Branche: {branche}, Plaats: {plaats}", n_agents=3)
        tekst = result.answer if result.confidence > 0.4 else _llm(prompt, max_tokens=300)
        logger.info("pitch: swarm confidence=%.2f winner=agent%d", result.confidence, result.winner_agent)
    except Exception as exc:
        logger.debug("pitch: swarm niet beschikbaar (%s), gebruik enkelvoudige LLM", exc)
        tekst = _llm(prompt, max_tokens=300)

    _sla_pitch_op(order_id, tekst)

    return {
        "ok":          True,
        "order_id":    order_id,
        "pitch_tekst": tekst,
        "order":       order_ophalen(order_id),
    }


def markeer_gepitcht(order_id: str) -> dict[str, Any]:
    """Zet status → gepitcht."""
    from core.orders_store import order_ophalen, status_bijwerken
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}
    if order["status"] not in ("goedgekeurd",):
        return {"ok": False, "error": f"Verwacht status 'goedgekeurd', is '{order['status']}'"}
    order = status_bijwerken(order_id, "gepitcht")
    return {"ok": True, "order": order}


def markeer_akkoord(order_id: str) -> dict[str, Any]:
    """Zet status → akkoord en genereert het vervolgbericht met prijs + PayPal-link."""
    from core.orders_store import order_ophalen, status_bijwerken

    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}
    if order["status"] != "gepitcht":
        return {"ok": False, "error": f"Verwacht status 'gepitcht', is '{order['status']}'"}

    naam    = order["bedrijfsnaam"]
    branche = order.get("branche", "")
    prijs   = order["prijs"]

    # MiroFish pricing confidence — simulate 50 belief agents to score acceptance probability
    prijs_advies = ""
    try:
        import random as _rng, math as _math
        _seed = hash(f"{naam}:{prijs}:{branche}") & 0x7FFFFFFF
        _r = _rng.Random(_seed)
        _n = 50
        _signal = max(0.1, min(0.9, 1.0 - (prijs / 600.0)))  # higher price → lower signal
        _beliefs = [_r.uniform(0.3, 0.7) for _ in range(_n)]
        for _ in range(8):
            _crowd = sum(_beliefs) / _n
            _beliefs = [max(0.02, min(0.98, (1 - _r.uniform(0.1, 0.5)) * _signal + _r.uniform(0.1, 0.5) * _crowd + _r.gauss(0, 0.03))) for _ in _beliefs]
        _prob_accept = sum(_beliefs) / _n
        if _prob_accept < 0.45:
            prijs_advies = f"[Swarm: prijs €{prijs:.0f} heeft lage acceptatiekans ({_prob_accept:.0%}) — overweeg €{max(199, prijs - 50):.0f}]"
        elif _prob_accept > 0.72:
            prijs_advies = f"[Swarm: prijs €{prijs:.0f} heeft hoge acceptatiekans ({_prob_accept:.0%})]"
        logger.info("pitch: mirofish pricing prob_accept=%.2f prijs=%.0f", _prob_accept, prijs)
    except Exception as _exc:
        logger.debug("pitch: mirofish pricing fout: %s", _exc)

    paypal = f"{_PAYPAL_LINK}/{int(prijs)}" if not _PAYPAL_LINK.endswith(str(int(prijs))) else _PAYPAL_LINK

    # PAYPAL_LINK niet ingesteld → de placeholder zou anders naar een klant gaan.
    paypal_placeholder = _PAYPAL_LINK == "https://paypal.me/jouwlink"
    waarschuwing = (
        "⚠️ LET OP: PAYPAL_LINK is niet ingesteld — de betaallink hieronder is een PLACEHOLDER. "
        "Zet PAYPAL_LINK=https://paypal.me/jouwnaam in ~/.ai-employee/.env en herstart de server "
        "vóór je dit bericht verstuurt.\n\n"
    ) if paypal_placeholder else ""

    vervolg = (
        f"{waarschuwing}"
        f"Hoi {naam},\n\n"
        f"Top dat je interesse hebt! Dan zetten we hem voor je live.\n\n"
        f"De kosten zijn €{prijs:.0f} eenmalig — geen maandelijkse kosten.\n"
        f"Je kunt direct betalen via: {paypal}\n\n"
        f"Zodra de betaling binnen is, zet ik de site voor jullie live.\n\n"
        f"Groeten, Lars"
    )

    _sla_vervolg_op(order_id, vervolg)
    order = status_bijwerken(order_id, "akkoord")
    order["vervolg_tekst"] = vervolg

    return {"ok": True, "order": order, "vervolg_tekst": vervolg, "paypal_placeholder": paypal_placeholder, "prijs_advies": prijs_advies}


def markeer_betaald(order_id: str, referentie: str = "") -> dict[str, Any]:
    """Zet status → betaald. Vereist een PayPal-transactiereferentie als bewijs van betaling."""
    from core.orders_store import order_ophalen, betaalreferentie_opslaan
    if not referentie or not referentie.strip():
        return {
            "ok": False,
            "error": (
                "Vul eerst de PayPal-transactiereferentie in. "
                "Je vindt deze in je PayPal-account onder 'Activiteit' → de betaling → 'Transactie-ID'. "
                "Zo weet het systeem zeker dat het geld echt binnen is."
            ),
        }
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}
    if order["status"] != "akkoord":
        return {"ok": False, "error": f"Verwacht status 'akkoord', is '{order['status']}' — klant moet eerst akkoord geven"}
    result = betaalreferentie_opslaan(order_id, referentie)
    logger.info("pitch: order %s → betaald (ref: %s)", order_id, referentie)
    return result


def markeer_live(order_id: str) -> dict[str, Any]:
    """Zet status → live. Aanroepen nadat Lars domein/hosting geregeld heeft."""
    from core.orders_store import order_ophalen, status_bijwerken
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}
    if order["status"] != "betaald":
        return {"ok": False, "error": f"Verwacht status 'betaald', is '{order['status']}'"}
    order = status_bijwerken(order_id, "live")
    logger.info("pitch: order %s → live", order_id)
    return {"ok": True, "order": order}


# ── intern: tekst opslaan in DB ──────────────────────────────────────────────

def _sla_pitch_op(order_id: str, tekst: str) -> None:
    from core.orders_store import _conn
    try:
        with _conn() as conn:
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN pitch_tekst TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute("UPDATE orders SET pitch_tekst=? WHERE id=?", (tekst, order_id))
    except Exception as exc:
        logger.warning("pitch: kon pitch_tekst niet opslaan: %s", exc)


def _sla_vervolg_op(order_id: str, tekst: str) -> None:
    from core.orders_store import _conn
    try:
        with _conn() as conn:
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN vervolg_tekst TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute("UPDATE orders SET vervolg_tekst=? WHERE id=?", (tekst, order_id))
    except Exception as exc:
        logger.warning("pitch: kon vervolg_tekst niet opslaan: %s", exc)

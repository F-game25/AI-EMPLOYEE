"""Pitch-generator en betalingsafhandeling voor de website-sales pipeline.

Workflow na blok 3:
  goedgekeurd → [genereer_pitch] → pitch klaar → Lars verstuurt ZELF
             → [markeer_gepitcht] → gepitcht
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

    naam   = order["bedrijfsnaam"]
    plaats = order["plaats"]
    prijs  = order["prijs"]
    demo   = demo_url or order.get("demo_pad", "")
    paypal = f"{_PAYPAL_LINK}/{int(prijs)}" if not _PAYPAL_LINK.endswith(str(int(prijs))) else _PAYPAL_LINK

    aanhef = f"het team van {naam}" if not order.get("contact") else order["contact"]
    demo_display = demo if demo.startswith("http") else f"bestand: {demo}"
    prompt = (
        f"Schrijf een kort, persoonlijk bericht (max 120 woorden) gericht aan {naam} in {plaats}. "
        f"Begin de aanhef met 'Hoi {naam},' — gebruik NIET een verzonnen voornaam. "
        f"De toon is: vriendelijk, direct, lokaal — niet opdringerig. "
        f"Vertel dat ik een gratis demo-website voor ze heb klaargezet. "
        f"Vermeld letterlijk: '{demo_display}'. "
        f"Noem de prijs: €{prijs:.0f} eenmalig, geen maandelijkse kosten. "
        f"Concrete volgende stap: betalen via {paypal} en dan zet ik hem live. "
        f"Sluit af met 'Groeten, Lars'. "
        f"Schrijf ALLEEN het bericht, geen uitleg of extra tekst."
    )

    tekst = _llm(prompt, max_tokens=200)

    # Sla pitch_tekst op in de orders-tabel als die kolom bestaat
    _sla_pitch_op(order_id, tekst)

    return {
        "ok":          True,
        "order_id":    order_id,
        "pitch_tekst": tekst,
        "paypal_link": paypal,
        "order":       order_ophalen(order_id),
    }


def markeer_gepitcht(order_id: str) -> dict[str, Any]:
    """Zet status → gepitcht. Aanroepen NADAT Lars het bericht verstuurd heeft."""
    from core.orders_store import order_ophalen, status_bijwerken
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}
    if order["status"] not in ("goedgekeurd",):
        return {"ok": False, "error": f"Verwacht status 'goedgekeurd', is '{order['status']}'"}
    order = status_bijwerken(order_id, "gepitcht")
    return {"ok": True, "order": order}


def markeer_betaald(order_id: str) -> dict[str, Any]:
    """Zet status → betaald. Lars markeert dit handmatig als het geld binnen is."""
    from core.orders_store import order_ophalen, status_bijwerken
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}
    if order["status"] not in ("gepitcht", "goedgekeurd"):
        return {"ok": False, "error": f"Verwacht status 'gepitcht' of 'goedgekeurd', is '{order['status']}'"}
    order = status_bijwerken(order_id, "betaald")
    logger.info("pitch: order %s → betaald", order_id)
    return {"ok": True, "order": order}


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


# ── intern: pitch opslaan in DB ───────────────────────────────────────────────

def _sla_pitch_op(order_id: str, tekst: str) -> None:
    """Voeg pitch_tekst kolom toe (indien nodig) en sla de tekst op."""
    from core.orders_store import _conn
    try:
        with _conn() as conn:
            # Voeg kolom toe als hij er nog niet is (idempotent)
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN pitch_tekst TEXT DEFAULT ''")
            except Exception:
                pass  # kolom bestaat al
            conn.execute(
                "UPDATE orders SET pitch_tekst=? WHERE id=?",
                (tekst, order_id),
            )
    except Exception as exc:
        logger.warning("pitch: kon pitch_tekst niet opslaan: %s", exc)

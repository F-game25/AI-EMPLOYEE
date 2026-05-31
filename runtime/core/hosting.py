"""Netlify hosting: deploy een demo-HTML naar een gratis Netlify-site.

HITL: Lars klikt de knop — dit script deployt vervolgens automatisch.
Vereist NETLIFY_API_TOKEN in ~/.ai-employee/.env.
Crasht het systeem NIET als het token ontbreekt — geeft een duidelijke fout.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_NETLIFY_TOKEN = os.environ.get("NETLIFY_API_TOKEN", "")
_AI_HOME = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))


def deploy_to_netlify(order_id: str) -> dict[str, Any]:
    """Deploy de demo van order_id als nieuwe Netlify-site.

    Returns dict met:
      ok: bool
      live_url: str (Netlify SSL URL)
      hosting_voorstel: str (kant-en-klare template-tekst voor Lars)
      error: str (alleen bij ok=False)
    """
    if not _NETLIFY_TOKEN:
        return {
            "ok": False,
            "error": (
                "NETLIFY_API_TOKEN is niet ingesteld. "
                "Maak een gratis account op netlify.com → Account Settings → Applications → New access token. "
                "Voeg daarna NETLIFY_API_TOKEN=<jouw-token> toe aan ~/.ai-employee/.env en herstart de server."
            ),
        }

    from core.orders_store import order_ophalen, _conn

    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}

    demo_pad = order.get("demo_pad", "")
    if not demo_pad:
        return {"ok": False, "error": "Order heeft geen demo_pad — genereer eerst een demo."}

    demo_file = Path(demo_pad)
    if not demo_file.exists():
        demo_file = _AI_HOME / "state" / "artifacts" / "demos" / Path(demo_pad).name
    if not demo_file.exists():
        return {"ok": False, "error": f"Demo-bestand niet gevonden: {demo_pad}"}

    html_bytes = demo_file.read_bytes()

    # Netlify Files API: POST multipart met één bestand → nieuwe site
    boundary = "----NetlifyBoundary7f3a9b"
    body_parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{demo_file.name}"\r\n'.encode(),
        b"Content-Type: text/html\r\n\r\n",
        html_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(body_parts)

    req = urllib.request.Request(
        "https://api.netlify.com/api/v1/sites",
        data=body,
        headers={
            "Authorization": f"Bearer {_NETLIFY_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_err = exc.read().decode("utf-8", errors="replace")[:400]
        return {"ok": False, "error": f"Netlify API fout {exc.code}: {body_err}"}
    except Exception as exc:
        return {"ok": False, "error": f"Deploy mislukt: {exc}"}

    live_url = data.get("ssl_url") or data.get("url", "")
    if not live_url:
        return {"ok": False, "error": f"Netlify gaf geen URL terug: {json.dumps(data)[:200]}"}

    # Sla live_url op in de orders-tabel (idempotent kolom)
    _sla_live_url(order_id, live_url)

    naam = order["bedrijfsnaam"]
    hosting_voorstel = (
        f"Beste {naam},\n\n"
        f"Jullie website staat nu live op: {live_url}\n\n"
        f"Voor een eigen domeinnaam (bv. {naam.lower().replace(' ', '')}.nl) "
        f"en doorlopend beheer:\n"
        f"- Domeinnaam: €20/jaar (eenmalig)\n"
        f"- Hosting + onderhoud: €20/maand\n\n"
        f"Interesse? Laat het weten!\n"
        f"Groeten, Lars"
    )

    logger.info("hosting: order %s live op %s", order_id, live_url)
    return {
        "ok": True,
        "live_url": live_url,
        "hosting_voorstel": hosting_voorstel,
        "order_id": order_id,
    }


def _sla_live_url(order_id: str, live_url: str) -> None:
    from core.orders_store import _conn
    try:
        with _conn() as conn:
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN live_url TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute("UPDATE orders SET live_url=? WHERE id=?", (live_url, order_id))
    except Exception as exc:
        logger.warning("hosting: kon live_url niet opslaan: %s", exc)

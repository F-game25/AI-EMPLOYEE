"""WhatsApp Inbound Webhook — receives Twilio WhatsApp messages and updates the CRM.

When a lead replies on WhatsApp, Twilio sends a POST request here. This server:
  1. Validates the Twilio signature (when TWILIO_AUTH_TOKEN is set).
  2. Finds the matching lead in the CRM by phone number.
  3. Records the inbound message in the lead's outreach_messages history.
  4. Sets the lead status to "replied" and clears next_followup to stop follow-ups.
  5. Returns an empty TwiML response so Twilio is satisfied.

Config env vars:
    TWILIO_AUTH_TOKEN         — used to validate webhook signatures (recommended)
    TWILIO_WHATSAPP_FROM      — your Twilio WhatsApp number
    WHATSAPP_WEBHOOK_PORT     — port to listen on (default: 8788)
    WHATSAPP_WEBHOOK_HOST     — host to bind (default: 0.0.0.0)
    AI_HOME                   — path to the AI Employee data directory
"""
import hashlib
import hmac
import json
import logging
import os
import sys
import urllib.parse
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
import uvicorn

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(asctime)s [webhook] %(levelname)s %(message)s",
)
logger = logging.getLogger("whatsapp-webhook")

# ── Config ────────────────────────────────────────────────────────────────────

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
CRM_FILE = AI_HOME / "state" / "lead-generator-crm.json"
STATE_FILE = AI_HOME / "state" / "whatsapp-webhook.state.json"

TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
WEBHOOK_PORT = int(os.environ.get("WHATSAPP_WEBHOOK_PORT", "8788"))
WEBHOOK_HOST = os.environ.get("WHATSAPP_WEBHOOK_HOST", "0.0.0.0")

# ── CRM helpers ───────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_crm() -> dict:
    if not CRM_FILE.exists():
        return {"items": []}
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return {"items": []}


def save_crm(crm: dict) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(crm, indent=2))


def _normalise_phone(raw: str) -> str:
    """Strip the 'whatsapp:' prefix and normalise to E.164."""
    return raw.replace("whatsapp:", "").strip()


def _find_lead_by_phone(crm: dict, phone: str) -> dict | None:
    """Return the first lead whose phone matches (ignoring whatsapp: prefix)."""
    needle = _normalise_phone(phone)
    for lead in crm.get("items", []):
        stored = _normalise_phone(lead.get("phone", ""))
        if stored and stored == needle:
            return lead
    return None


# ── Twilio signature validation ───────────────────────────────────────────────


def _validate_twilio_signature(auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Validate an X-Twilio-Signature header (HMAC-SHA1 over url+sorted params).

    See: https://www.twilio.com/docs/usage/webhooks/webhooks-security
    """
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    computed = b64encode(
        hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return hmac.compare_digest(computed, signature)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="WhatsApp Inbound Webhook", docs_url=None, redoc_url=None)

_TWIML_EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@app.post("/webhook/whatsapp", response_class=PlainTextResponse)
async def whatsapp_inbound(
    request: Request,
    x_twilio_signature: str = Header(default="", alias="X-Twilio-Signature"),
) -> PlainTextResponse:
    """Receive an inbound WhatsApp message from Twilio."""
    # Parse form body
    body_bytes = await request.body()
    try:
        params: dict[str, str] = dict(urllib.parse.parse_qsl(body_bytes.decode("utf-8")))
    except Exception:
        params = {}

    # Validate signature when auth token is configured
    if TWILIO_AUTH_TOKEN:
        url = str(request.url)
        if not x_twilio_signature:
            logger.warning("Request missing X-Twilio-Signature — rejecting")
            raise HTTPException(status_code=403, detail="Missing signature")
        if not _validate_twilio_signature(TWILIO_AUTH_TOKEN, url, params, x_twilio_signature):
            logger.warning("Invalid Twilio signature — rejecting request from %s", request.client)
            raise HTTPException(status_code=403, detail="Invalid signature")

    from_number = params.get("From", "")
    body_text = params.get("Body", "").strip()
    message_sid = params.get("MessageSid", "")

    logger.info("Inbound WhatsApp from=%s sid=%s body=%r", from_number, message_sid, body_text[:80])

    if not from_number:
        return PlainTextResponse(_TWIML_EMPTY, media_type="application/xml")

    # Update CRM
    crm = load_crm()
    lead = _find_lead_by_phone(crm, from_number)

    if lead:
        # Record inbound message
        lead.setdefault("outreach_messages", []).append({
            "channel": "whatsapp",
            "direction": "inbound",
            "message": body_text,
            "message_sid": message_sid,
            "ts": now_iso(),
        })

        # Stop follow-ups — mark as replied unless already in an advanced stage
        if lead.get("status") not in ("qualified", "appointment", "won"):
            lead["status"] = "replied"

        # Clear the follow-up schedule so the follow-up engine skips this lead
        lead["next_followup"] = ""
        lead["updated_at"] = now_iso()
        save_crm(crm)
        logger.info(
            "Lead %s (%s) replied — status set to %s, follow-ups paused",
            lead["id"], lead["name"], lead["status"],
        )
    else:
        logger.info("No lead found for phone %s — storing orphan message", from_number)
        # Store orphan inbound messages so they can be reviewed later
        crm.setdefault("orphan_messages", []).append({
            "from": _normalise_phone(from_number),
            "message": body_text,
            "message_sid": message_sid,
            "ts": now_iso(),
        })
        save_crm(crm)

    return PlainTextResponse(_TWIML_EMPTY, media_type="application/xml")


@app.get("/health")
async def health() -> dict:
    crm = load_crm()
    return {
        "status": "ok",
        "leads": len(crm.get("items", [])),
        "crm_path": str(CRM_FILE),
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "bot": "whatsapp-webhook",
        "status": "starting",
        "ts": now_iso(),
        "port": WEBHOOK_PORT,
    }, indent=2))

    logger.info("Starting WhatsApp webhook server on %s:%d", WEBHOOK_HOST, WEBHOOK_PORT)
    if not TWILIO_AUTH_TOKEN:
        logger.warning(
            "TWILIO_AUTH_TOKEN is not set — webhook signature validation is DISABLED. "
            "Set it in ~/.ai-employee/.env for production use."
        )

    uvicorn.run(app, host=WEBHOOK_HOST, port=WEBHOOK_PORT, log_level="info")


if __name__ == "__main__":
    main()

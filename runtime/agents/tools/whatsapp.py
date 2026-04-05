"""WhatsApp Tool — send WhatsApp messages via Twilio API.

Supports two modes:
    1. Twilio WhatsApp Sandbox / Production (requires TWILIO_ACCOUNT_SID,
       TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM)
    2. Meta WhatsApp Cloud API (requires WHATSAPP_TOKEN, WHATSAPP_PHONE_ID)

Usage (from any bot):

    import sys, os
    from pathlib import Path
    AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
    sys.path.insert(0, str(AI_HOME / "agents" / "tools"))
    from whatsapp import send_whatsapp

    ok, info = send_whatsapp(to="+31612345678", message="Hello from AI Employee!")
    if ok:
        print("Sent:", info["message_sid"])
    else:
        print("Failed:", info["error"])

Config env vars:
    --- Twilio (preferred) ---
    TWILIO_ACCOUNT_SID       — Twilio account SID
    TWILIO_AUTH_TOKEN        — Twilio auth token
    TWILIO_WHATSAPP_FROM     — Twilio WhatsApp number (e.g. whatsapp:+14155238886)

    --- Meta Cloud API (alternative) ---
    WHATSAPP_TOKEN           — Meta permanent access token
    WHATSAPP_PHONE_ID        — Meta phone number ID

    --- Shared ---
    WHATSAPP_DEFAULT_FROM    — default sender number (E.164 format)
    WHATSAPP_DRY_RUN         — if "true", logs but does not send (default: false)
"""
import json
import logging
import os
import urllib.request
import urllib.parse

logger = logging.getLogger("whatsapp")

# ── Twilio configuration ──────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")

# ── Meta Cloud API configuration ──────────────────────────────────────────────
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")

DRY_RUN = os.environ.get("WHATSAPP_DRY_RUN", "false").lower() == "true"


def _twilio_send(to: str, message: str, from_number: str) -> tuple[bool, dict]:
    """Send via Twilio Messaging API (stdlib only)."""
    import base64

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    )
    # Ensure WhatsApp prefix on numbers
    wa_to = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    wa_from = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

    data = urllib.parse.urlencode({
        "To": wa_to,
        "From": wa_from,
        "Body": message,
    }).encode("utf-8")

    credentials = base64.b64encode(
        f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()
    ).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "AI-Employee/1.0",
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            sid = body.get("sid", "")
            status = body.get("status", "")
            logger.info("whatsapp: Twilio sent to %s | sid=%s status=%s", to, sid, status)
            return True, {"message_sid": sid, "status": status, "provider": "twilio"}
    except Exception as exc:
        logger.error("whatsapp: Twilio send failed — %s", exc)
        return False, {"error": str(exc), "provider": "twilio"}


def _meta_send(to: str, message: str) -> tuple[bool, dict]:
    """Send via Meta WhatsApp Cloud API (stdlib only)."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    # Meta expects E.164 without "+" for the to field in some versions,
    # but sending full E.164 is safest.
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.removeprefix("+"),
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "AI-Employee/1.0",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            msg_id = body.get("messages", [{}])[0].get("id", "")
            logger.info("whatsapp: Meta sent to %s | id=%s", to, msg_id)
            return True, {"message_sid": msg_id, "status": "sent", "provider": "meta"}
    except Exception as exc:
        logger.error("whatsapp: Meta send failed — %s", exc)
        return False, {"error": str(exc), "provider": "meta"}


def send_whatsapp(
    to: str,
    message: str,
    from_number: str = "",
) -> tuple[bool, dict]:
    """Send a WhatsApp message to a phone number.

    Tries Twilio first; falls back to Meta Cloud API if Twilio credentials
    are not set.

    Args:
        to:          Recipient phone number in E.164 format (e.g. +31612345678).
        message:     Message text (max 4096 characters).
        from_number: Sender number override; falls back to TWILIO_WHATSAPP_FROM.

    Returns:
        Tuple (success: bool, info: dict).
        On success: info contains message_sid, status, provider.
        On failure: info contains error, provider.
    """
    if DRY_RUN:
        logger.info("whatsapp: DRY_RUN — would send to %s: %s", to, message[:80])
        return True, {"message_sid": "dry_run", "status": "dry_run", "provider": "dry_run"}

    if not to:
        return False, {"error": "No recipient number provided", "provider": "none"}

    message = message[:4096]

    # Try Twilio if credentials are available
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        sender = from_number or TWILIO_WHATSAPP_FROM
        if sender:
            return _twilio_send(to, message, sender)
        logger.warning(
            "whatsapp: Twilio creds set but TWILIO_WHATSAPP_FROM is empty — "
            "set it to your WhatsApp sender number"
        )

    # Try Meta Cloud API
    if WHATSAPP_TOKEN and WHATSAPP_PHONE_ID:
        return _meta_send(to, message)

    return False, {
        "error": (
            "No WhatsApp provider configured. "
            "Set TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_WHATSAPP_FROM "
            "or WHATSAPP_TOKEN + WHATSAPP_PHONE_ID in ~/.ai-employee/.env"
        ),
        "provider": "none",
    }


def is_whatsapp_configured() -> bool:
    """Return True if at least one WhatsApp provider is configured."""
    return bool(
        (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM)
        or (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID)
    )


"""WhatsApp Tool — send WhatsApp messages via Twilio API.

Provides a simple send_whatsapp() helper that wraps the Twilio REST API.
Falls back to a dry-run log if credentials are not configured.

Environment variables (set in ~/.ai-employee/.env):
    TWILIO_ACCOUNT_SID   — Twilio account SID (starts with "AC…")
    TWILIO_AUTH_TOKEN    — Twilio auth token
    TWILIO_WHATSAPP_FROM — Your Twilio WhatsApp sender (e.g. "whatsapp:+14155238886")

Usage:
    from whatsapp import send_whatsapp, WhatsAppClient

    # Simple helper (uses env-vars automatically)
    result = send_whatsapp(to="+31612345678", body="Hello from AI Employee!")
    print(result["status"])  # "sent" | "dry_run" | "error"

    # Full client with custom credentials
    client = WhatsAppClient(account_sid="AC…", auth_token="…", from_number="whatsapp:+1…")
    result = client.send(to="+31612345678", body="Hi!")
"""

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
import base64
from typing import Optional

logger = logging.getLogger("whatsapp")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


def _normalize_to(number: str) -> str:
    """Ensure the recipient is in Twilio WhatsApp format."""
    if not number.startswith("whatsapp:"):
        return f"whatsapp:{number}"
    return number


class WhatsAppClient:
    """Twilio WhatsApp sender.

    Falls back to a dry-run log if credentials are missing/invalid
    so that bots can be tested without real credentials.
    """

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
    ) -> None:
        self.account_sid = account_sid or TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or TWILIO_AUTH_TOKEN
        self.from_number = from_number or TWILIO_WHATSAPP_FROM

    @property
    def _credentials_set(self) -> bool:
        return bool(self.account_sid and self.auth_token)

    def send(self, to: str, body: str) -> dict:
        """Send a WhatsApp message.

        Args:
            to:   Recipient phone number (e.g. "+31612345678" or "whatsapp:+31612345678").
            body: Message text.

        Returns:
            dict with keys:
                status   (str)   — "sent" | "dry_run" | "error"
                sid      (str)   — Twilio message SID (if sent)
                to       (str)   — normalised recipient
                error    (str)   — error message (if status == "error")
        """
        to_norm = _normalize_to(to)

        if not self._credentials_set:
            logger.info(
                "whatsapp [dry_run]: to=%s from=%s body=%s",
                to_norm, self.from_number, body[:80],
            )
            return {
                "status": "dry_run",
                "sid": "",
                "to": to_norm,
                "error": "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not configured",
            }

        url = f"{_TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json"
        data = urllib.parse.urlencode({
            "From": self.from_number,
            "To": to_norm,
            "Body": body,
        }).encode("utf-8")

        # Basic auth header
        credentials = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                sid = result.get("sid", "")
                logger.info("whatsapp: sent to=%s sid=%s", to_norm, sid)
                return {"status": "sent", "sid": sid, "to": to_norm, "error": None}
        except urllib.error.HTTPError as exc:
            body_err = exc.read().decode("utf-8", errors="replace")
            try:
                err_data = json.loads(body_err)
                error_msg = err_data.get("message", body_err)
            except Exception:
                error_msg = body_err
            logger.error("whatsapp: HTTP error %s — %s", exc.code, error_msg)
            return {"status": "error", "sid": "", "to": to_norm, "error": error_msg}
        except Exception as exc:
            logger.error("whatsapp: send failed — %s", exc)
            return {"status": "error", "sid": "", "to": to_norm, "error": str(exc)}


# ── Module-level convenience function ─────────────────────────────────────────

_default_client: Optional[WhatsAppClient] = None


def send_whatsapp(to: str, body: str) -> dict:
    """Send a WhatsApp message using default (env-var) credentials.

    Args:
        to:   Recipient phone number.
        body: Message text.

    Returns:
        dict — see WhatsAppClient.send() for structure.
    """
    global _default_client
    if _default_client is None:
        _default_client = WhatsAppClient()
    return _default_client.send(to=to, body=body)

"""Discord webhook notifications — optional helper used by multiple agents.

Sends a message to a Discord channel via an Incoming Webhook URL.
Set DISCORD_WEBHOOK_URL in ~/.ai-employee/.env to enable.

Usage:
    from discord_notify import notify_discord, is_discord_configured

    if is_discord_configured():
        notify_discord("🎯 10 new leads found in Amsterdam!")
"""
import json
import logging
import os
import urllib.request
from urllib.error import URLError

logger = logging.getLogger("discord-notify")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def is_discord_configured() -> bool:
    """Return True if a Discord webhook URL is set."""
    return bool(DISCORD_WEBHOOK_URL)


def notify_discord(message: str, username: str = "AI Employee") -> bool:
    """Post *message* to the configured Discord webhook channel.

    Returns True on success, False on any failure (never raises).
    Silently skips if DISCORD_WEBHOOK_URL is not set.
    """
    if not DISCORD_WEBHOOK_URL:
        return False
    # Discord messages are capped at 2000 characters
    if len(message) > 2000:
        message = message[:1997] + "…"
    try:
        payload = json.dumps({"content": message, "username": username}).encode()
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except (URLError, Exception) as exc:
        logger.warning("Discord webhook notification failed: %s", exc)
        return False

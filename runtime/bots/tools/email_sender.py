"""Email Sender Tool — send emails via SMTP or SendGrid.

Supports two modes:
    1. SMTP (any provider: Gmail, Outlook, Mailgun, etc.)
    2. SendGrid HTTP API (higher deliverability for bulk outreach)

Usage (from any bot):

    import sys, os
    from pathlib import Path
    AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
    sys.path.insert(0, str(AI_HOME / "bots" / "tools"))
    from email_sender import send_email

    ok, info = send_email(
        to="prospect@example.com",
        subject="Quick question about your growth",
        body="Hi Jane, ...",
    )
    if ok:
        print("Sent:", info["message_id"])
    else:
        print("Failed:", info["error"])

Config env vars:
    --- SMTP ---
    SMTP_HOST        — SMTP server hostname (e.g. smtp.gmail.com)
    SMTP_PORT        — SMTP port (default: 587)
    SMTP_USER        — SMTP username / email address
    SMTP_PASS        — SMTP password or app-specific password
    SMTP_FROM        — From address (defaults to SMTP_USER)
    SMTP_USE_TLS     — Use STARTTLS (default: true); set "false" for SSL port 465

    --- SendGrid (alternative) ---
    SENDGRID_API_KEY — SendGrid API key
    SENDGRID_FROM    — Verified sender email

    --- Shared ---
    EMAIL_DRY_RUN    — if "true", logs but does not send (default: false)
    EMAIL_REPLY_TO   — Reply-To address (optional)
"""
import json
import logging
import os
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger("email_sender")

# ── SMTP configuration ────────────────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "") or SMTP_USER
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() != "false"

# ── SendGrid configuration ────────────────────────────────────────────────────
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENDGRID_FROM = os.environ.get("SENDGRID_FROM", "")

EMAIL_DRY_RUN = os.environ.get("EMAIL_DRY_RUN", "false").lower() == "true"
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "")


def _smtp_send(
    to: str,
    subject: str,
    body: str,
    html_body: Optional[str],
    reply_to: str,
) -> tuple[bool, dict]:
    """Send an email via SMTP using Python stdlib smtplib."""
    import smtplib

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if SMTP_USE_TLS:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20)
            server.ehlo()

        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [to], msg.as_string())
        server.quit()

        message_id = msg.get("Message-ID", "")
        logger.info("email_sender: SMTP sent to %s | subject: %s", to, subject[:60])
        return True, {"message_id": message_id, "provider": "smtp", "status": "sent"}

    except Exception as exc:
        logger.error("email_sender: SMTP send failed — %s", exc)
        return False, {"error": str(exc), "provider": "smtp"}


def _sendgrid_send(
    to: str,
    subject: str,
    body: str,
    html_body: Optional[str],
    reply_to: str,
    from_addr: str,
) -> tuple[bool, dict]:
    """Send an email via SendGrid HTTP API (stdlib only)."""
    payload: dict = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": from_addr},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    if html_body:
        payload["content"].append({"type": "text/html", "value": html_body})
    if reply_to:
        payload["reply_to"] = {"email": reply_to}

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "AI-Employee/1.0",
    }
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            message_id = resp.headers.get("X-Message-Id", "")
            logger.info(
                "email_sender: SendGrid sent to %s | subject: %s | id: %s",
                to, subject[:60], message_id,
            )
            return True, {"message_id": message_id, "provider": "sendgrid", "status": "sent"}
    except Exception as exc:
        logger.error("email_sender: SendGrid send failed — %s", exc)
        return False, {"error": str(exc), "provider": "sendgrid"}
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"

# ── SendGrid configuration ────────────────────────────────────────────────────
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENDGRID_FROM = os.environ.get("SENDGRID_FROM", "")

EMAIL_DRY_RUN = os.environ.get("EMAIL_DRY_RUN", "false").lower() == "true"
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "")


def send_email(
    to: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    from_addr: str = "",
    reply_to: str = "",
) -> tuple[bool, dict]:
    """Send an email to a single recipient.

    Tries SendGrid first (if configured, better deliverability for bulk
    outreach); falls back to SMTP.

    Args:
        to:        Recipient email address.
        subject:   Email subject line.
        body:      Plain-text email body.
        html_body: Optional HTML version of the body.
        from_addr: Sender address override (defaults to SMTP_FROM / SENDGRID_FROM).
        reply_to:  Reply-To address override (defaults to EMAIL_REPLY_TO).

    Returns:
        Tuple (success: bool, info: dict).
        On success: info contains message_id, status, provider.
        On failure: info contains error, provider.
    """
    if EMAIL_DRY_RUN:
        logger.info(
            "email_sender: DRY_RUN — would send to %s | subject: %s", to, subject
        )
        return True, {"message_id": "dry_run", "status": "dry_run", "provider": "dry_run"}

    if not to:
        return False, {"error": "No recipient address provided", "provider": "none"}

    reply_to_addr = reply_to or EMAIL_REPLY_TO

    # Try SendGrid first (better deliverability for bulk/cold outreach)
    if SENDGRID_API_KEY:
        sg_from = from_addr or SENDGRID_FROM or SMTP_FROM
        if sg_from:
            return _sendgrid_send(to, subject, body, html_body, reply_to_addr, sg_from)
        logger.warning(
            "email_sender: SENDGRID_API_KEY set but no from address — "
            "set SENDGRID_FROM in ~/.ai-employee/.env"
        )

    # Fall back to SMTP
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        return _smtp_send(to, subject, body, html_body, reply_to_addr)

    return False, {
        "error": (
            "No email provider configured. "
            "Set SMTP_HOST + SMTP_USER + SMTP_PASS "
            "or SENDGRID_API_KEY + SENDGRID_FROM in ~/.ai-employee/.env"
        ),
        "provider": "none",
    }


def is_email_configured() -> bool:
    """Return True if at least one email provider is configured."""
    smtp_ok = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)
    sg_ok = bool(SENDGRID_API_KEY and (SENDGRID_FROM or SMTP_FROM))
    return smtp_ok or sg_ok


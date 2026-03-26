"""Email Sender Tool — send emails via SMTP.

Provides a simple send_email() helper that uses Python's stdlib smtplib.
Falls back to a dry-run log if credentials are not configured.

Environment variables (set in ~/.ai-employee/.env):
    SMTP_HOST       — SMTP server hostname (e.g. "smtp.gmail.com")
    SMTP_PORT       — SMTP port (default: 587 for STARTTLS, 465 for SSL)
    SMTP_USER       — SMTP username / sender email address
    SMTP_PASS       — SMTP password or app password
    SMTP_USE_SSL    — "true" to use SSL (port 465); default uses STARTTLS

Usage:
    from email_sender import send_email, EmailClient

    # Simple helper (uses env-vars automatically)
    result = send_email(
        to="prospect@example.com",
        subject="Quick question about your website",
        body="Hi Jane, …",
    )
    print(result["status"])  # "sent" | "dry_run" | "error"

    # Full client
    client = EmailClient(host="smtp.gmail.com", port=587, user="me@gmail.com", password="…")
    result = client.send(to="recipient@example.com", subject="Hello", body="World")
"""

import logging
import os
import smtplib
import email.mime.text
import email.mime.multipart
from typing import Optional

logger = logging.getLogger("email_sender")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"


class EmailClient:
    """SMTP email sender with STARTTLS/SSL support.

    Falls back to a dry-run log when credentials are missing so bots
    can be tested without real mail server credentials.
    """

    def __init__(
        self,
        host: str = "",
        port: int = 0,
        user: str = "",
        password: str = "",
        use_ssl: Optional[bool] = None,
    ) -> None:
        self.host = host or SMTP_HOST
        self.port = port or SMTP_PORT
        self.user = user or SMTP_USER
        self.password = password or SMTP_PASS
        self.use_ssl = use_ssl if use_ssl is not None else SMTP_USE_SSL

    @property
    def _credentials_set(self) -> bool:
        return bool(self.host and self.user and self.password)

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str = "",
        from_name: str = "",
        reply_to: str = "",
    ) -> dict:
        """Send an email.

        Args:
            to:        Recipient email address.
            subject:   Email subject line.
            body:      Plain-text body.
            html_body: Optional HTML body (sends multipart/alternative when set).
            from_name: Optional display name for the sender.
            reply_to:  Optional Reply-To address.

        Returns:
            dict with keys:
                status  (str)  — "sent" | "dry_run" | "error"
                to      (str)  — recipient address
                subject (str)  — subject line
                error   (str)  — error message (if status == "error")
        """
        if not self._credentials_set:
            logger.info(
                "email_sender [dry_run]: to=%s subject=%s",
                to, subject[:80],
            )
            return {
                "status": "dry_run",
                "to": to,
                "subject": subject,
                "error": "SMTP_HOST / SMTP_USER / SMTP_PASS not configured",
            }

        sender = f"{from_name} <{self.user}>" if from_name else self.user

        # Build message
        if html_body:
            msg = email.mime.multipart.MIMEMultipart("alternative")
            msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))
            msg.attach(email.mime.text.MIMEText(html_body, "html", "utf-8"))
        else:
            msg = email.mime.text.MIMEText(body, "plain", "utf-8")

        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to
        if reply_to:
            msg["Reply-To"] = reply_to

        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=15) as server:
                    server.login(self.user, self.password)
                    server.sendmail(self.user, [to], msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.user, self.password)
                    server.sendmail(self.user, [to], msg.as_string())

            logger.info("email_sender: sent to=%s subject=%s", to, subject[:80])
            return {"status": "sent", "to": to, "subject": subject, "error": None}

        except smtplib.SMTPAuthenticationError as exc:
            error_msg = f"SMTP authentication failed: {exc}"
            logger.error("email_sender: %s", error_msg)
            return {"status": "error", "to": to, "subject": subject, "error": error_msg}
        except smtplib.SMTPException as exc:
            error_msg = f"SMTP error: {exc}"
            logger.error("email_sender: %s", error_msg)
            return {"status": "error", "to": to, "subject": subject, "error": error_msg}
        except Exception as exc:
            error_msg = str(exc)
            logger.error("email_sender: unexpected error — %s", error_msg)
            return {"status": "error", "to": to, "subject": subject, "error": error_msg}


# ── Module-level convenience function ─────────────────────────────────────────

_default_client: Optional[EmailClient] = None


def send_email(
    to: str,
    subject: str,
    body: str,
    html_body: str = "",
    from_name: str = "",
    reply_to: str = "",
) -> dict:
    """Send an email using default (env-var) SMTP credentials.

    Args:
        to:        Recipient email address.
        subject:   Email subject line.
        body:      Plain-text body.
        html_body: Optional HTML body.
        from_name: Optional display name for the sender.
        reply_to:  Optional Reply-To address.

    Returns:
        dict — see EmailClient.send() for structure.
    """
    global _default_client
    if _default_client is None:
        _default_client = EmailClient()
    return _default_client.send(
        to=to,
        subject=subject,
        body=body,
        html_body=html_body,
        from_name=from_name,
        reply_to=reply_to,
    )

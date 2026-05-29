"""Sentry error tracking and issue monitoring."""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def init_sentry(dsn: Optional[str] = None, environment: str = "production") -> bool:
    """Initialize Sentry error tracking."""
    if not dsn:
        dsn = os.environ.get("SENTRY_DSN", "")

    if not dsn:
        logger.info("Sentry DSN not configured; error tracking disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=environment,
            debug=False,
            max_breadcrumbs=100,
            attach_stacktrace=True,
        )
        logger.info(f"Sentry initialized: {environment}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False


def get_sentry_client():
    """Get Sentry client if available."""
    try:
        import sentry_sdk
        return sentry_sdk.get_client()
    except Exception:
        return None


def capture_exception(exc: Exception, context: dict = None):
    """Capture exception in Sentry."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_context(key, value)
            sentry_sdk.capture_exception(exc)
    except Exception as e:
        logger.error(f"Failed to capture exception in Sentry: {e}")


def capture_message(message: str, level: str = "info", context: dict = None):
    """Capture message in Sentry."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_context(key, value)
            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logger.error(f"Failed to capture message in Sentry: {e}")


def set_user_context(user_id: str, email: str = "", username: str = ""):
    """Set user context for error tracking."""
    try:
        import sentry_sdk
        sentry_sdk.set_user({"id": user_id, "email": email, "username": username})
    except Exception as e:
        logger.error(f"Failed to set user context in Sentry: {e}")


def set_tenant_context(tenant_id: str):
    """Set tenant context for error tracking."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("tenant_id", tenant_id)
    except Exception as e:
        logger.error(f"Failed to set tenant context in Sentry: {e}")

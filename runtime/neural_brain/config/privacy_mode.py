"""Privacy Mode — controls what the system is allowed to do externally.

Three modes (user-configured via PRIVACY_MODE env var or runtime API):

  OFFLINE   — zero external calls. All AI runs locally. No telemetry export.
  HYBRID    — external API keys allowed (OpenRouter/Anthropic). No telemetry export.
  CONNECTED — external APIs + opt-in anonymised telemetry export (user must also
              set TELEMETRY_ENABLED=1 and TELEMETRY_ENDPOINT).

Defaults to HYBRID on first run. User changes this; the system respects it
immediately without restart (hot-switchable via set_mode()).

Rules enforced at call-sites:
  - ModelArchitectureRouter checks can_use_external_apis() before any remote call
  - TelemetryEngine checks can_export_telemetry() before any outbound bundle
  - No module may call the network unless the relevant capability returns True
"""
from __future__ import annotations

import logging
import os
import threading
from enum import Enum
from pathlib import Path
import json

logger = logging.getLogger(__name__)

_MODE_FILE = Path("state/privacy_mode.json")


class PrivacyMode(str, Enum):
    OFFLINE   = "OFFLINE"    # air-gapped — no external calls whatsoever
    HYBRID    = "HYBRID"     # local-first, external APIs allowed by user config
    CONNECTED = "CONNECTED"  # hybrid + opt-in anonymised telemetry export


class PrivacySettings:
    """Live, hot-switchable privacy configuration."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode: PrivacyMode = self._load_initial()
        # Telemetry export sub-toggle (only meaningful in CONNECTED mode)
        self._telemetry_enabled: bool = os.getenv("TELEMETRY_ENABLED", "0") in ("1", "true", "yes")
        self._telemetry_endpoint: str = os.getenv("TELEMETRY_ENDPOINT", "").strip()
        self._auto_update: bool = os.getenv("AUTO_UPDATE", "0") in ("1", "true", "yes")
        self._update_endpoint: str = os.getenv("UPDATE_ENDPOINT", "").strip()
        logger.info(
            "Privacy mode: %s | telemetry=%s | auto_update=%s",
            self._mode.value, self._telemetry_enabled, self._auto_update,
        )

    # ── Mode access ───────────────────────────────────────────────────────────

    def get_mode(self) -> PrivacyMode:
        with self._lock:
            return self._mode

    def set_mode(self, mode: PrivacyMode | str, *, persist: bool = True) -> None:
        if isinstance(mode, str):
            mode = PrivacyMode(mode.upper())
        with self._lock:
            old = self._mode
            self._mode = mode
        if persist:
            self._persist()
        if old != mode:
            self._emit_changed(old, mode)
            logger.info("Privacy mode changed: %s → %s", old.value, mode.value)

    # ── Capability gates (call these at every external call-site) ─────────────

    def can_use_external_apis(self) -> bool:
        """Allow OpenRouter / Anthropic / any remote model call."""
        return self._mode in (PrivacyMode.HYBRID, PrivacyMode.CONNECTED)

    def can_export_telemetry(self) -> bool:
        """Allow sending anonymised telemetry bundles out."""
        with self._lock:
            return (
                self._mode == PrivacyMode.CONNECTED
                and self._telemetry_enabled
                and bool(self._telemetry_endpoint)
            )

    def can_check_updates(self) -> bool:
        """Allow checking for software updates."""
        return self._mode in (PrivacyMode.HYBRID, PrivacyMode.CONNECTED)

    def can_auto_update(self) -> bool:
        return self.can_check_updates() and self._auto_update

    # ── Telemetry sub-settings ────────────────────────────────────────────────

    def set_telemetry(self, enabled: bool, endpoint: str = "") -> None:
        with self._lock:
            self._telemetry_enabled = enabled
            if endpoint:
                self._telemetry_endpoint = endpoint
        self._persist()

    def set_auto_update(self, enabled: bool, endpoint: str = "") -> None:
        with self._lock:
            self._auto_update = enabled
            if endpoint:
                self._update_endpoint = endpoint
        self._persist()

    def get_telemetry_endpoint(self) -> str:
        with self._lock:
            return self._telemetry_endpoint

    def get_update_endpoint(self) -> str:
        with self._lock:
            return self._update_endpoint

    def get_status(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode.value,
                "can_use_external_apis": self.can_use_external_apis(),
                "can_export_telemetry": self.can_export_telemetry(),
                "can_check_updates": self.can_check_updates(),
                "can_auto_update": self.can_auto_update(),
                "telemetry_enabled": self._telemetry_enabled,
                "telemetry_endpoint_set": bool(self._telemetry_endpoint),
                "auto_update": self._auto_update,
                "update_endpoint_set": bool(self._update_endpoint),
            }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_initial(self) -> PrivacyMode:
        # Env var takes priority over persisted file
        env_val = os.getenv("PRIVACY_MODE", "").strip().upper()
        if env_val in PrivacyMode.__members__:
            return PrivacyMode(env_val)
        # Persisted preference
        try:
            if _MODE_FILE.exists():
                data = json.loads(_MODE_FILE.read_text())
                return PrivacyMode(data.get("mode", "HYBRID"))
        except Exception:
            pass
        return PrivacyMode.HYBRID

    def _persist(self) -> None:
        try:
            _MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = {
                    "mode": self._mode.value,
                    "telemetry_enabled": self._telemetry_enabled,
                    "auto_update": self._auto_update,
                }
            _MODE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.debug("Privacy mode persist failed: %s", e)

    def _emit_changed(self, old: PrivacyMode, new: PrivacyMode) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("privacy:mode_changed", source="privacy_settings", payload={
                "from": old.value, "to": new.value,
            })
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_settings: PrivacySettings | None = None
_lock = threading.Lock()


def get_privacy() -> PrivacySettings:
    global _settings
    if _settings is None:
        with _lock:
            if _settings is None:
                _settings = PrivacySettings()
    return _settings


# Convenience shorthand used at call-sites
def can_use_external_apis() -> bool:
    return get_privacy().can_use_external_apis()

def can_export_telemetry() -> bool:
    return get_privacy().can_export_telemetry()

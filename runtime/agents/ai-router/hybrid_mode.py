"""Hybrid Resilient Mode — Dual-Mode Architecture for AI Employee.

Implements a two-mode system that allows the AI to operate optimally when
connected to the internet (ONLINE) and degrade gracefully into a powerful
local-only mode when connectivity is lost (OFFLINE).

Architecture
============

MODE_ONLINE  — Full routing: all cloud + local providers available.
MODE_OFFLINE — Local-only routing: only Ollama and Gemma (via Ollama) are
               used.  Cloud providers (NVIDIA NIM, Anthropic, OpenAI) are
               skipped entirely to avoid hanging calls.
MODE_AUTO    — Connectivity is checked before each call; mode is chosen
               automatically.  Falls back to OFFLINE when the probe fails.

Connectivity Detection
======================
Uses a lightweight probe that tries three targets in order:
  1. DNS resolution (socket connect to 8.8.8.8:53, 1 s timeout) — no HTTP.
  2. HTTPS HEAD to https://www.google.com (2 s timeout).
  3. HTTPS HEAD to https://api.openai.com   (2 s timeout).
One success → considered online.  All fail → considered offline.

The probe result is cached for CONNECTIVITY_CACHE_TTL seconds (default 30) to
avoid repeated network calls on every request.

Manual Override & Fail-Safe
============================
HYBRID_MODE env var:
  "auto"    (default) — auto-detect on every call (with cache)
  "online"  — always treat as online (skip probe)
  "offline" — always treat as offline (skip probe and all cloud calls)

Runtime override via set_hybrid_mode():
  Takes "auto" | "online" | "offline".  Persists for the lifetime of the
  process.  Overrides the env var.

Fail-safe: if a cloud call raises a network error while in ONLINE mode, the
caller can invoke record_provider_failure() to force OFFLINE mode until
connectivity is re-confirmed.  After FAILSAFE_COOLDOWN seconds the mode
reverts to AUTO so connectivity can be re-probed.

Memory Continuity
=================
When switching from OFFLINE → ONLINE, the module emits a "sync_ready" event
so that any attached memory/cache module can push buffered writes.

Environment Variables
=====================
    HYBRID_MODE               — "auto" | "online" | "offline"  (default: auto)
    CONNECTIVITY_CACHE_TTL    — seconds to cache probe result (default: 30)
    CONNECTIVITY_PROBE_TIMEOUT — probe timeout in seconds (default: 3)
    FAILSAFE_COOLDOWN         — seconds before exiting failsafe offline (default: 120)

Usage
=====
    from hybrid_mode import (
        get_hybrid_mode, set_hybrid_mode, is_online,
        get_status, record_provider_failure, MODE_ONLINE, MODE_OFFLINE, MODE_AUTO,
    )

    # Check current effective mode
    if is_online():
        # use cloud providers
    else:
        # use local providers only

    # Force offline for testing
    set_hybrid_mode("offline")

    # Retrieve full status dict
    print(get_status())
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import urllib.request
from typing import Optional

logger = logging.getLogger("hybrid_mode")

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_ONLINE: str = "online"
MODE_OFFLINE: str = "offline"
MODE_AUTO: str = "auto"

_VALID_MODES = {MODE_ONLINE, MODE_OFFLINE, MODE_AUTO}

# ── Configuration ─────────────────────────────────────────────────────────────
CONNECTIVITY_CACHE_TTL: int = int(os.environ.get("CONNECTIVITY_CACHE_TTL", "30"))
CONNECTIVITY_PROBE_TIMEOUT: int = int(os.environ.get("CONNECTIVITY_PROBE_TIMEOUT", "3"))
FAILSAFE_COOLDOWN: int = int(os.environ.get("FAILSAFE_COOLDOWN", "120"))

# Probe endpoints — ordered by cheapness/reliability
_PROBE_DNS_HOST = "8.8.8.8"
_PROBE_DNS_PORT = 53
_PROBE_HTTPS_URLS = [
    "https://www.google.com",
    "https://api.openai.com",
]

# ── Internal state (module-level, protected by _lock) ────────────────────────
_lock = threading.Lock()

# Runtime mode override (None → read from env var)
_runtime_mode: Optional[str] = None

# Connectivity probe cache
_last_probe_time: float = 0.0
_last_probe_result: Optional[bool] = None  # True=online, False=offline, None=unknown

# Failsafe state
_failsafe_active: bool = False
_failsafe_triggered_at: float = 0.0

# Callbacks registered via on_mode_change()
_mode_change_callbacks: list = []

# Last known effective mode (used to detect transitions)
_last_effective_mode: Optional[str] = None


# ── Mode accessors ────────────────────────────────────────────────────────────

def get_hybrid_mode() -> str:
    """Return the currently configured hybrid mode string.

    Returns the runtime override if set, otherwise the HYBRID_MODE env var,
    defaulting to MODE_AUTO.
    """
    with _lock:
        if _runtime_mode is not None:
            return _runtime_mode
    raw = os.environ.get("HYBRID_MODE", MODE_AUTO).strip().lower()
    return raw if raw in _VALID_MODES else MODE_AUTO


def set_hybrid_mode(mode: str) -> None:
    """Set the hybrid mode at runtime, overriding the env var.

    Args:
        mode: One of "auto", "online", or "offline".

    Raises:
        ValueError: If an invalid mode string is provided.
    """
    mode = mode.strip().lower()
    if mode not in _VALID_MODES:
        raise ValueError(f"Invalid hybrid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}")
    global _runtime_mode, _failsafe_active
    with _lock:
        _runtime_mode = mode
        # Resetting to any explicit mode clears the failsafe
        if mode != MODE_AUTO:
            _failsafe_active = False
    logger.info("hybrid_mode: mode set to '%s'", mode)
    _notify_mode_change(mode)


# ── Connectivity probe ────────────────────────────────────────────────────────

def check_connectivity() -> bool:
    """Probe internet connectivity.  Returns True if online, False if offline.

    Tries (in order):
    1. DNS socket connect to 8.8.8.8:53   — cheapest, no HTTP overhead.
    2. HTTPS HEAD to google.com            — fallback if DNS blocked.
    3. HTTPS HEAD to api.openai.com        — secondary HTTPS fallback.

    The result is NOT cached here.  Use is_online() for a cached version.
    """
    timeout = CONNECTIVITY_PROBE_TIMEOUT

    # 1. DNS socket probe (fastest, no HTTP)
    try:
        sock = socket.create_connection((_PROBE_DNS_HOST, _PROBE_DNS_PORT), timeout=timeout)
        sock.close()
        logger.debug("hybrid_mode: connectivity probe OK (DNS socket)")
        return True
    except OSError:
        pass

    # 2 & 3. HTTPS HEAD requests
    for url in _PROBE_HTTPS_URLS:
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "AI-Employee-Probe/1.0"})
            with urllib.request.urlopen(req, timeout=timeout):
                pass
            logger.debug("hybrid_mode: connectivity probe OK (%s)", url)
            return True
        except Exception:
            pass

    logger.debug("hybrid_mode: connectivity probe FAILED — offline")
    return False


def is_online() -> bool:
    """Return True if the system is effectively online.

    Respects the configured mode:
    - MODE_ONLINE  → always True (no probe)
    - MODE_OFFLINE → always False (no probe)
    - MODE_AUTO    → probe with caching, failsafe override considered

    The probe result is cached for CONNECTIVITY_CACHE_TTL seconds.
    """
    global _last_probe_time, _last_probe_result, _failsafe_active, _failsafe_triggered_at
    global _last_effective_mode

    mode = get_hybrid_mode()

    if mode == MODE_ONLINE:
        _maybe_notify_transition(True)
        return True

    if mode == MODE_OFFLINE:
        _maybe_notify_transition(False)
        return False

    # MODE_AUTO: check failsafe first
    with _lock:
        if _failsafe_active:
            elapsed = time.monotonic() - _failsafe_triggered_at
            if elapsed < FAILSAFE_COOLDOWN:
                logger.debug(
                    "hybrid_mode: failsafe active — offline (%ds remaining)",
                    int(FAILSAFE_COOLDOWN - elapsed),
                )
            else:
                # Cooldown expired — reset failsafe and re-probe
                _failsafe_active = False
                logger.info("hybrid_mode: failsafe cooldown expired — re-probing connectivity")

    # Re-check failsafe (after possible reset above) outside the lock
    if is_failsafe_active():
        _maybe_notify_transition(False)
        return False

    # Use cached result if still fresh
    now = time.monotonic()
    cached_result = None
    with _lock:
        cache_age = now - _last_probe_time
        if _last_probe_result is not None and cache_age < CONNECTIVITY_CACHE_TTL:
            cached_result = _last_probe_result

    if cached_result is not None:
        _maybe_notify_transition(cached_result)
        return cached_result

    # Probe (outside lock to avoid blocking other threads)
    result = check_connectivity()

    with _lock:
        _last_probe_time = time.monotonic()
        _last_probe_result = result

    _maybe_notify_transition(result)
    return result


def invalidate_connectivity_cache() -> None:
    """Force the next is_online() call to re-probe (clears cached result)."""
    global _last_probe_time, _last_probe_result
    with _lock:
        _last_probe_time = 0.0
        _last_probe_result = None


# ── Fail-safe mechanism ───────────────────────────────────────────────────────

def record_provider_failure(provider: str = "") -> None:
    """Signal that a cloud provider call failed with a network error.

    In MODE_AUTO, this activates the failsafe which forces offline routing
    for FAILSAFE_COOLDOWN seconds, preventing further hanging cloud calls.
    After the cooldown, the mode reverts to AUTO and connectivity is re-probed.

    Args:
        provider: Optional provider name for logging (e.g. "anthropic").
    """
    global _failsafe_active, _failsafe_triggered_at
    mode = get_hybrid_mode()
    if mode != MODE_AUTO:
        return  # Only auto-mode triggers failsafe; explicit modes are honoured as-is
    with _lock:
        if not _failsafe_active:
            _failsafe_active = True
            _failsafe_triggered_at = time.monotonic()
            logger.warning(
                "hybrid_mode: failsafe triggered by provider='%s' — "
                "forcing offline for %ds",
                provider,
                FAILSAFE_COOLDOWN,
            )
    # Invalidate cache so the next probe starts fresh
    invalidate_connectivity_cache()


def is_failsafe_active() -> bool:
    """Return True if the fail-safe offline override is currently active."""
    with _lock:
        if not _failsafe_active:
            return False
        return (time.monotonic() - _failsafe_triggered_at) < FAILSAFE_COOLDOWN


# ── Status reporting ──────────────────────────────────────────────────────────

def get_status() -> dict:
    """Return a dict describing the current hybrid mode state.

    Keys:
        configured_mode  (str)  — "auto" | "online" | "offline"
        effective_online (bool) — True if currently acting as online
        failsafe_active  (bool) — True if failsafe is forcing offline
        failsafe_remaining_s (int|None) — seconds until failsafe expires, or None
        cache_age_s      (float|None)  — age of connectivity probe cache, or None
        probe_result     (bool|None)   — last raw probe result (None if never probed)
    """
    configured = get_hybrid_mode()
    online = is_online()

    with _lock:
        fs = _failsafe_active and (time.monotonic() - _failsafe_triggered_at) < FAILSAFE_COOLDOWN
        fs_remaining = (
            int(FAILSAFE_COOLDOWN - (time.monotonic() - _failsafe_triggered_at))
            if fs else None
        )
        cache_age = (time.monotonic() - _last_probe_time) if _last_probe_time else None
        probe = _last_probe_result

    return {
        "configured_mode": configured,
        "effective_online": online,
        "failsafe_active": fs,
        "failsafe_remaining_s": fs_remaining,
        "cache_age_s": round(cache_age, 1) if cache_age is not None else None,
        "probe_result": probe,
    }


def offline_unavailable_response(feature: str = "This feature") -> dict:
    """Return a standard response for features unavailable in offline mode.

    Args:
        feature: Human-readable name of the unavailable feature.

    Returns:
        Standard ai_router-compatible error dict with a user-friendly message.
    """
    return {
        "answer": (
            f"[OFFLINE MODE] {feature} requires an internet connection. "
            "The system is currently running in offline mode using local AI models only. "
            "When connectivity is restored, full capabilities will resume automatically."
        ),
        "provider": "offline",
        "model": "",
        "error": "offline_mode",
        "usage": None,
    }


def offline_search_notice(query: str) -> list:
    """Return a notice result list for web search called in offline mode.

    Args:
        query: The search query that could not be performed.

    Returns:
        A single-item list with a notice result compatible with search_web().
    """
    return [
        {
            "title": "[OFFLINE MODE] Web search unavailable",
            "url": "",
            "snippet": (
                f"Web search for '{query}' could not be performed — "
                "the system is currently in offline mode. "
                "Please check your internet connection or switch to online mode."
            ),
            "source": "hybrid_mode",
        }
    ]


# ── Mode-change callbacks ─────────────────────────────────────────────────────

def on_mode_change(callback) -> None:
    """Register a callback to be invoked when the effective mode changes.

    The callback receives a single boolean argument: True → went online,
    False → went offline.  Useful for triggering memory sync on reconnect.

    Args:
        callback: Callable that accepts one bool argument.
    """
    with _lock:
        _mode_change_callbacks.append(callback)


def _notify_mode_change(mode_or_online) -> None:
    """Notify registered callbacks.  Accepts mode string or bool."""
    if isinstance(mode_or_online, str):
        online = mode_or_online == MODE_ONLINE
    else:
        online = bool(mode_or_online)
    with _lock:
        callbacks = list(_mode_change_callbacks)
    for cb in callbacks:
        try:
            cb(online)
        except Exception as exc:
            logger.debug("hybrid_mode: callback error — %s", exc)


def _maybe_notify_transition(online: bool) -> None:
    """Fire callbacks only when the effective mode actually changes."""
    global _last_effective_mode
    with _lock:
        last = _last_effective_mode
        new = MODE_ONLINE if online else MODE_OFFLINE
        if last == new:
            return
        _last_effective_mode = new
    logger.info(
        "hybrid_mode: transition %s → %s",
        last or "unknown",
        new,
    )
    _notify_mode_change(online)

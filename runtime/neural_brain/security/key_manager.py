"""Key Manager — AES-256 encryption keys + HMAC signing keys with automatic rotation.

Keys rotate every 10 minutes by default.
Old keys have a 2-minute grace period so in-flight tokens remain valid.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import struct
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ROTATION_INTERVAL_S = int(os.getenv("KEY_ROTATION_INTERVAL_S", "600"))   # 10 min
_GRACE_PERIOD_S = int(os.getenv("KEY_GRACE_PERIOD_S", "120"))              # 2 min

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    logger.warning("cryptography package not installed — using HMAC-only mode")


@dataclass
class KeyVersion:
    version: int
    key_bytes: bytes      # 32 bytes for AES-256
    hmac_bytes: bytes     # 32 bytes for HMAC-SHA256
    created_at: float
    expires_at: float
    grace_until: float


class KeyManager:
    """Thread-safe rotating key store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._versions: OrderedDict[int, KeyVersion] = OrderedDict()
        self._current_version: int = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._rotate()  # generate initial key

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._rotation_loop, daemon=True, name="key_rotation")
        self._thread.start()
        logger.info("KeyManager started — rotation every %ds, grace %ds", _ROTATION_INTERVAL_S, _GRACE_PERIOD_S)

    def stop(self) -> None:
        self._running = False

    # ── Rotation ──────────────────────────────────────────────────────────────

    def _rotate(self) -> KeyVersion:
        now = time.time()
        with self._lock:
            version = self._current_version + 1
            key = KeyVersion(
                version=version,
                key_bytes=os.urandom(32),
                hmac_bytes=os.urandom(32),
                created_at=now,
                expires_at=now + _ROTATION_INTERVAL_S,
                grace_until=now + _ROTATION_INTERVAL_S + _GRACE_PERIOD_S,
            )
            self._versions[version] = key
            self._current_version = version
            # Purge keys past grace period
            cutoff = now - _GRACE_PERIOD_S
            expired = [v for v, k in self._versions.items() if k.grace_until < now and v != version]
            for v in expired:
                del self._versions[v]
        self._emit_rotated(version)
        logger.info("Key rotated → version=%d", version)
        return key

    def _rotation_loop(self) -> None:
        while self._running:
            time.sleep(_ROTATION_INTERVAL_S)
            try:
                self._rotate()
            except Exception as e:
                logger.error("Key rotation error: %s", e)

    def force_rotate(self) -> int:
        """Admin-triggered immediate rotation."""
        kv = self._rotate()
        return kv.version

    # ── Encryption (AES-256-GCM) ──────────────────────────────────────────────

    def encrypt(self, plaintext: bytes) -> bytes:
        """Returns versioned ciphertext: [4-byte version][12-byte nonce][ciphertext+tag]."""
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography package required for encryption")
        with self._lock:
            kv = self._versions[self._current_version]
        nonce = os.urandom(12)
        aesgcm = AESGCM(kv.key_bytes)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        version_bytes = struct.pack(">I", kv.version)
        return version_bytes + nonce + ct

    def decrypt(self, ciphertext: bytes) -> bytes:
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography package required for decryption")
        version = struct.unpack(">I", ciphertext[:4])[0]
        with self._lock:
            kv = self._versions.get(version)
        if kv is None:
            raise ValueError(f"Unknown key version {version} — key may have expired")
        nonce = ciphertext[4:16]
        ct = ciphertext[16:]
        return AESGCM(kv.key_bytes).decrypt(nonce, ct, None)

    # ── HMAC signing ─────────────────────────────────────────────────────────

    def sign(self, data: bytes) -> tuple[int, bytes]:
        """Returns (version, signature)."""
        with self._lock:
            kv = self._versions[self._current_version]
        sig = hmac.new(kv.hmac_bytes, data, hashlib.sha256).digest()
        return kv.version, sig

    def verify(self, data: bytes, version: int, signature: bytes) -> bool:
        with self._lock:
            kv = self._versions.get(version)
        if kv is None:
            return False
        expected = hmac.new(kv.hmac_bytes, data, hashlib.sha256).digest()
        return hmac.compare_digest(expected, signature)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        now = time.time()
        with self._lock:
            kv = self._versions.get(self._current_version)
            return {
                "current_version": self._current_version,
                "active_versions": len(self._versions),
                "next_rotation_in_s": int((kv.expires_at - now)) if kv else 0,
                "grace_period_s": _GRACE_PERIOD_S,
                "rotation_interval_s": _ROTATION_INTERVAL_S,
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit_rotated(self, version: int) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("security:key_rotated", source="key_manager", payload={"version": version})
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_manager: KeyManager | None = None
_lock = threading.Lock()


def get_key_manager() -> KeyManager:
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = KeyManager()
                _manager.start()
    return _manager

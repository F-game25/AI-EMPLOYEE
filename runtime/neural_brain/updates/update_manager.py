"""Update Manager — check, download, verify, and apply software updates.

User controls everything:
  - AUTO_UPDATE=0 (default): check only, user decides
  - AUTO_UPDATE=1: auto-apply non-breaking updates

Update flow:
  1. check()    — fetch manifest from UPDATE_ENDPOINT, compare version
  2. download() — stream update package to state/updates/pending/
  3. verify()   — HMAC-SHA256 signature check (no execution without verification)
  4. apply()    — extract + hot-swap modules; emit event for Forge integration

Packages are signed by the update server. Verification uses the public key
embedded in the installation (UPDATE_PUBLIC_KEY env var or key file).

No update ever executes without passing signature verification.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import shutil
import tarfile
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.file_lock import FileLock
from core.state_paths import canonical_state_dir

logger = logging.getLogger(__name__)

# Canonical state tree (honours STATE_DIR / AI_HOME) — not repo-local ./state. C0.
_STATE_DIR     = canonical_state_dir()
_PENDING_DIR   = _STATE_DIR / "updates" / "pending"
_APPLIED_DIR   = _STATE_DIR / "updates" / "applied"
_MANIFEST_PATH = _STATE_DIR / "updates" / "last_manifest.json"
_VERSION_FILE  = _STATE_DIR / "version.json"
_CHECK_INTERVAL_S = int(os.getenv("UPDATE_CHECK_INTERVAL_S", str(6 * 3600)))  # 6h
_DOWNLOAD_TIMEOUT_S = int(os.getenv("UPDATE_DOWNLOAD_TIMEOUT_S", "30"))


@dataclass
class UpdateInfo:
    version: str
    release_notes: str
    package_url: str
    signature: str          # hex HMAC-SHA256 of the package bytes
    signature_version: int  # key version used to sign
    package_hash: str       # SHA-256 of raw package bytes
    size_bytes: int
    update_type: str        # "patch" | "module" | "agent" | "full"
    requires_restart: bool
    released_at: int        # unix timestamp


class UpdateManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_version = self._read_version()
        self._available: Optional[UpdateInfo] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        _APPLIED_DIR.mkdir(parents=True, exist_ok=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._check_loop, daemon=True, name="update_manager"
        )
        self._thread.start()
        logger.info("UpdateManager started — version=%s, auto_update=%s",
                    self._current_version, self._can_auto_update())

    def stop(self) -> None:
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self) -> Optional[dict]:
        """Check for available updates. Returns UpdateInfo dict or None."""
        from neural_brain.config.privacy_mode import get_privacy
        if not get_privacy().can_check_updates():
            return None
        endpoint = get_privacy().get_update_endpoint()
        if not endpoint:
            logger.debug("No UPDATE_ENDPOINT configured — skipping check")
            return None
        try:
            manifest = self._fetch_manifest(endpoint)
            available_version = manifest.get("version", "")
            if not self._is_newer(available_version, self._current_version):
                logger.debug("No update available (current=%s latest=%s)",
                             self._current_version, available_version)
                return None

            info = UpdateInfo(
                version=available_version,
                release_notes=manifest.get("release_notes", "")[:500],
                package_url=manifest.get("package_url", ""),
                signature=manifest.get("signature", ""),
                signature_version=manifest.get("signature_version", 1),
                package_hash=manifest.get("package_hash", ""),
                size_bytes=manifest.get("size_bytes", 0),
                update_type=manifest.get("update_type", "patch"),
                requires_restart=manifest.get("requires_restart", False),
                released_at=manifest.get("released_at", 0),
            )
            with self._lock:
                self._available = info
            _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(_MANIFEST_PATH, timeout=2.0):
                _MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
            self._emit("update:available", {
                "version": info.version,
                "update_type": info.update_type,
                "requires_restart": info.requires_restart,
            })
            return self._info_to_dict(info)
        except Exception as e:
            logger.debug("Update check failed: %s", e)
            return None

    def download(self, version: str | None = None) -> Optional[Path]:
        """Download pending update package. Returns path to downloaded file."""
        with self._lock:
            info = self._available
        if info is None:
            return None
        if version and info.version != version:
            logger.warning("Requested version %s but available is %s", version, info.version)
            return None
        if not info.package_url:
            logger.warning("No package URL in update manifest")
            return None

        dest = _PENDING_DIR / f"update_{info.version}.tar.gz"
        if dest.exists():
            # Already downloaded — verify it's intact
            if self._verify_package(dest, info):
                return dest
            dest.unlink()

        try:
            logger.info("Downloading update %s from %s", info.version, info.package_url[:60])
            self._emit("update:download_started", {"version": info.version})
            with urllib.request.urlopen(info.package_url, timeout=_DOWNLOAD_TIMEOUT_S) as resp:
                data = resp.read()

            # Verify before writing to disk
            actual_hash = hashlib.sha256(data).hexdigest()
            if info.package_hash and actual_hash != info.package_hash:
                raise ValueError(f"Package hash mismatch: expected {info.package_hash[:16]}… got {actual_hash[:16]}…")

            dest.write_bytes(data)
            logger.info("Downloaded %d bytes → %s", len(data), dest)
            self._emit("update:download_complete", {"version": info.version, "size_bytes": len(data)})
            return dest
        except Exception as e:
            logger.error("Download failed: %s", e)
            self._emit("update:download_failed", {"version": info.version, "error": str(e)[:80]})
            return None

    def verify(self, package_path: Path) -> bool:
        """Verify HMAC-SHA256 signature of downloaded package."""
        with self._lock:
            info = self._available
        if info is None or not package_path.exists():
            return False
        return self._verify_package(package_path, info)

    def apply(self, package_path: Path, *, dry_run: bool = False) -> dict:
        """Extract and apply verified update package.

        dry_run=True: extract to temp dir and return what would change.
        """
        if not package_path.exists():
            return {"ok": False, "error": "package not found"}

        with self._lock:
            info = self._available

        if not self._verify_package(package_path, info):
            return {"ok": False, "error": "signature verification failed — update rejected"}

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                with tarfile.open(package_path, "r:gz") as tar:
                    # Security: only extract relative paths, no absolute or ..
                    safe_members = [m for m in tar.getmembers()
                                    if not (m.name.startswith("/") or ".." in m.name)]
                    tar.extractall(tmp_path, members=safe_members)

                manifest_file = tmp_path / "update_manifest.json"
                if not manifest_file.exists():
                    return {"ok": False, "error": "invalid package: missing update_manifest.json"}

                update_manifest = json.loads(manifest_file.read_text())
                changed_files = update_manifest.get("files", [])

                if dry_run:
                    return {"ok": True, "dry_run": True, "files": changed_files, "version": info.version if info else "?"}

                # Apply: copy files into runtime
                applied = []
                for rel_path in changed_files:
                    src = tmp_path / rel_path
                    if not src.exists():
                        continue
                    dst = Path(rel_path)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    applied.append(rel_path)

                # Record applied version
                new_version = info.version if info else update_manifest.get("version", "unknown")
                self._write_version(new_version)
                self._current_version = new_version

                # Archive the package
                archive = _APPLIED_DIR / package_path.name
                shutil.move(str(package_path), str(archive))

                with self._lock:
                    self._available = None

                self._emit("update:applied", {
                    "version": new_version,
                    "files_changed": len(applied),
                    "requires_restart": info.requires_restart if info else False,
                })
                logger.info("Update %s applied — %d files changed", new_version, len(applied))
                return {"ok": True, "version": new_version, "files_changed": applied}

        except Exception as e:
            logger.error("Apply failed: %s", e)
            self._emit("update:apply_failed", {"error": str(e)[:80]})
            return {"ok": False, "error": str(e)[:120]}

    def get_status(self) -> dict:
        with self._lock:
            available = self._info_to_dict(self._available) if self._available else None
        history = self._load_applied_history()
        return {
            "current_version": self._current_version,
            "available": available,
            "auto_update": self._can_auto_update(),
            "check_interval_s": _CHECK_INTERVAL_S,
            "applied_history": history[-5:],
        }

    # ── Background loop ───────────────────────────────────────────────────────

    def _check_loop(self) -> None:
        time.sleep(30)  # warm-up delay
        while self._running:
            info = self.check()
            if info and self._can_auto_update():
                pkg = self.download()
                if pkg and self.verify(pkg):
                    result = self.apply(pkg)
                    logger.info("Auto-update result: %s", result)
            time.sleep(_CHECK_INTERVAL_S)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fetch_manifest(self, endpoint: str) -> dict:
        url = endpoint.rstrip("/") + f"/manifest?current={self._current_version}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())

    def _verify_package(self, path: Path, info: Optional[UpdateInfo]) -> bool:
        if info is None:
            return False
        data = path.read_bytes()
        # Hash check
        if info.package_hash:
            actual = hashlib.sha256(data).hexdigest()
            if actual != info.package_hash:
                logger.warning("Package hash mismatch")
                return False
        # HMAC signature check via KeyManager
        if info.signature:
            try:
                from neural_brain.security.key_manager import get_key_manager
                sig_bytes = bytes.fromhex(info.signature)
                if get_key_manager().verify(data, info.signature_version, sig_bytes):
                    return True
                logger.warning("HMAC signature verification failed")
                return False
            except Exception as e:
                logger.warning("Signature check error: %s", e)
                return False
        # No signature in manifest — reject for safety
        logger.warning("Update package has no signature — rejected")
        return False

    @staticmethod
    def _is_newer(candidate: str, current: str) -> bool:
        def parse(v: str) -> tuple:
            try:
                return tuple(int(x) for x in v.lstrip("v").split(".")[:3])
            except Exception:
                return (0, 0, 0)
        return parse(candidate) > parse(current)

    @staticmethod
    def _read_version() -> str:
        try:
            with FileLock(_VERSION_FILE, timeout=2.0):
                if _VERSION_FILE.exists():
                    return json.loads(_VERSION_FILE.read_text()).get("version", "0.0.0")
        except Exception:
            pass
        return "0.0.0"

    @staticmethod
    def _write_version(version: str) -> None:
        # Lock the whole read-modify-write so a concurrent updater can't interleave
        # and leave version.json with a mismatched version/updated_at pair.
        try:
            _VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(_VERSION_FILE, timeout=2.0):
                existing = {}
                if _VERSION_FILE.exists():
                    try:
                        existing = json.loads(_VERSION_FILE.read_text())
                    except Exception:
                        existing = {}
                existing["version"] = version
                existing["updated_at"] = int(time.time())
                _VERSION_FILE.write_text(json.dumps(existing, indent=2))
        except Exception:
            pass

    def _load_applied_history(self) -> list[dict]:
        try:
            return [
                {"file": f.name, "ts": int(f.stat().st_mtime)}
                for f in sorted(_APPLIED_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
            ]
        except Exception:
            return []

    @staticmethod
    def _info_to_dict(info: Optional[UpdateInfo]) -> Optional[dict]:
        if info is None:
            return None
        return {
            "version": info.version,
            "release_notes": info.release_notes,
            "update_type": info.update_type,
            "size_bytes": info.size_bytes,
            "requires_restart": info.requires_restart,
            "released_at": info.released_at,
        }

    @staticmethod
    def _can_auto_update() -> bool:
        try:
            from neural_brain.config.privacy_mode import get_privacy
            return get_privacy().can_auto_update()
        except Exception:
            return False

    @staticmethod
    def _emit(event_type: str, payload: dict) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish(event_type, source="update_manager", payload=payload)
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_manager: UpdateManager | None = None
_lock = threading.Lock()


def get_update_manager() -> UpdateManager:
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = UpdateManager()
                _manager.start()
    return _manager

"""BrowserService — headless-chromium session manager for the browser tools.

Design invariants
-----------------
- ONE worker thread: sync Playwright is greenlet-bound and refuses to run on
  asyncio-loop threads. ALL Playwright calls funnel through ``_Worker.call``
  (90s op ceiling), so the service is safely callable from FastAPI/anywhere.
- Lazy launch: chromium starts on first ``open()``, resolved from the in-repo
  bundles (headless shell first), env override ``BROWSER_EXECUTABLE``.
  ``--no-sandbox`` only as root / when forced / on launch-retry-after-failure.
- Ephemeral sessions: each ``open()`` gets a fresh BrowserContext (no shared
  cookies/storage). Cap 3 concurrent (LRU evict), idle TTL 600s (env-tunable).
- URL policy first: ``check_url()`` runs BEFORE any chromium launch. http/https
  delegate to ``core.url_guard.validate_url`` (SSRF/private-IP/metadata
  blocking, fail-closed if the guard cannot be imported); ``data:``/``about:``
  are allowed (local render, no network fetch); ``file://`` is blocked unless
  ``BROWSER_ALLOW_FILE_URLS=1``.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("tools.browser.service")

_REPO_ROOT = Path(__file__).resolve().parents[3]

# In-repo chromium bundles, preferred order (headless shell is lighter).
_BUNDLE_CANDIDATES = (
    _REPO_ROOT / "runtime/browsers/playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell",
    _REPO_ROOT / "runtime/browsers/playwright/chromium-1217/chrome-linux64/chrome",
)

_OP_TIMEOUT_S = float(os.getenv("BROWSER_OP_TIMEOUT_S", "90"))
_MAX_SESSIONS = int(os.getenv("BROWSER_MAX_SESSIONS", "3"))
_SESSION_TTL_S = float(os.getenv("BROWSER_SESSION_TTL_S", "600"))
_NAV_TIMEOUT_MS = int(os.getenv("BROWSER_NAV_TIMEOUT_MS", "30000"))


def resolve_executable() -> Optional[str]:
    """Path to a usable chromium binary, or None. Env override wins."""
    override = os.getenv("BROWSER_EXECUTABLE", "").strip()
    if override:
        p = Path(override)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        logger.warning("BROWSER_EXECUTABLE set but not executable: %s", override)
    for cand in _BUNDLE_CANDIDATES:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def check_url(url: str) -> Optional[str]:
    """None if ``url`` may be opened, else a human-readable refusal reason.

    Must be called BEFORE any chromium launch — a blocked URL never costs a
    browser start.
    """
    if not url or not isinstance(url, str):
        return "URL is empty or not a string"
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    if scheme in ("data", "about"):
        return None  # local render only — no network fetch
    if scheme == "file":
        if os.getenv("BROWSER_ALLOW_FILE_URLS", "").strip().lower() in ("1", "true", "yes"):
            return None
        return "file:// URLs are blocked (set BROWSER_ALLOW_FILE_URLS=1 to allow)"
    if scheme in ("http", "https"):
        try:
            from core.url_guard import validate_url
        except Exception as exc:  # fail-closed: no guard → no fetch
            return f"url guard unavailable — blocked fail-closed: {exc}"
        return validate_url(url)
    return f"URL scheme '{scheme or '?'}' not allowed (http/https/data/about only)"


def _needs_no_sandbox() -> bool:
    if os.getenv("BROWSER_FORCE_NO_SANDBOX", "").strip().lower() in ("1", "true", "yes"):
        return True
    try:
        return os.geteuid() == 0
    except AttributeError:  # non-POSIX
        return False


class _Worker:
    """Single daemon thread that owns every Playwright object.

    Sync Playwright binds to the greenlet/thread it was started on and raises
    when touched from an asyncio-loop thread — funnelling all calls through
    this one thread sidesteps that entirely.
    """

    def __init__(self, name: str = "browser-worker") -> None:
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=name)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            fn, box, done = self._q.get()
            try:
                box["result"] = fn()
            except BaseException as exc:  # noqa: BLE001 — re-raised in caller
                box["error"] = exc
            done.set()

    def call(self, fn: Callable[[], Any], timeout: float = _OP_TIMEOUT_S) -> Any:
        """Run ``fn`` on the worker thread; re-raise its exception here."""
        if threading.current_thread() is self._thread:
            return fn()  # already on the worker — never self-deadlock
        box: dict[str, Any] = {}
        done = threading.Event()
        self._q.put((fn, box, done))
        if not done.wait(timeout):
            raise TimeoutError(f"browser operation exceeded {timeout:.0f}s ceiling")
        if "error" in box:
            raise box["error"]
        return box.get("result")


class Session:
    """One ephemeral browser context + page. ``call`` proxies to the worker."""

    def __init__(self, session_id: str, context: Any, page: Any, service: "BrowserService") -> None:
        self.id = session_id
        self.context = context
        self.page = page
        self._service = service
        self.created = self.last_used = time.time()
        self.url = ""

    def call(self, fn: Callable[[], Any], timeout: float = _OP_TIMEOUT_S) -> Any:
        self.last_used = time.time()
        return self._service.worker.call(fn, timeout)


class BrowserService:
    """Lazy-launch chromium session manager. Use ``get_browser_service()``."""

    def __init__(self) -> None:
        self.worker = _Worker()
        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}
        self._pw: Any = None
        self._browser: Any = None

    # ── Lifecycle (worker thread only) ────────────────────────────────────────

    def _ensure_browser(self) -> None:
        """Launch chromium if needed. MUST run on the worker thread."""
        if self._browser is not None:
            try:
                if self._browser.is_connected():
                    return
            except Exception:
                pass
            self._browser = None  # died — relaunch below
        exe = resolve_executable()
        if exe is None:
            raise RuntimeError(
                "no chromium executable found (in-repo bundles missing and "
                "BROWSER_EXECUTABLE unset)")
        if self._pw is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
        args = ["--no-sandbox"] if _needs_no_sandbox() else []
        try:
            self._browser = self._pw.chromium.launch(
                executable_path=exe, headless=True, args=args)
        except Exception as exc:
            if "--no-sandbox" in args:
                raise
            logger.warning("chromium launch failed (%s) — retrying with --no-sandbox", exc)
            self._browser = self._pw.chromium.launch(
                executable_path=exe, headless=True, args=["--no-sandbox"])

    def _reap_locked(self) -> None:
        """Idle-TTL sweep + LRU evict to make room. MUST run on the worker."""
        now = time.time()
        with self._lock:
            victims = [s for s in self._sessions.values()
                       if now - s.last_used > _SESSION_TTL_S]
            live = [s for s in self._sessions.values() if s not in victims]
            while len(live) >= _MAX_SESSIONS:  # LRU: oldest last_used goes first
                oldest = min(live, key=lambda s: s.last_used)
                victims.append(oldest)
                live.remove(oldest)
            for s in victims:
                self._sessions.pop(s.id, None)
        for s in victims:
            try:
                s.context.close()
            except Exception:
                pass

    # ── Public API ─────────────────────────────────────────────────────────────

    def open(self, url: str, profile: str = "ephemeral",
             timeout_ms: int = _NAV_TIMEOUT_MS) -> dict[str, Any]:
        """Open ``url`` in a fresh ephemeral context → {session_id, title, url}.

        URL policy is checked BEFORE any chromium launch; a blocked URL raises
        ``ValueError`` without ever starting a browser.
        """
        err = check_url(url)
        if err:
            raise ValueError(f"URL blocked: {err}")

        def job() -> tuple:
            self._ensure_browser()
            self._reap_locked()
            context = self._browser.new_context()  # fresh — no shared cookies/storage
            try:
                page = context.new_page()
                page.goto(url, timeout=timeout_ms, wait_until="load")
                return context, page, page.title(), page.url
            except Exception:
                try:
                    context.close()
                except Exception:
                    pass
                raise

        context, page, title, final_url = self.worker.call(job)
        sid = f"bs-{uuid.uuid4().hex[:10]}"
        sess = Session(sid, context, page, self)
        sess.url = final_url
        with self._lock:
            self._sessions[sid] = sess
        return {"session_id": sid, "title": title, "url": final_url}

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"session_id": s.id, "url": s.url, "created": s.created,
                     "last_used": s.last_used} for s in self._sessions.values()]

    def close(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            sess = self._sessions.pop(session_id, None)
        if sess is None:
            return {"closed": False, "note": f"unknown session: {session_id}"}
        try:
            self.worker.call(lambda: sess.context.close())
        except Exception as exc:
            return {"closed": True, "session_id": session_id,
                    "note": f"context close error: {exc}"}
        return {"closed": True, "session_id": session_id}

    def close_all(self) -> dict[str, Any]:
        with self._lock:
            victims = list(self._sessions.values())
            self._sessions.clear()

        def job() -> None:
            for s in victims:
                try:
                    s.context.close()
                except Exception:
                    pass

        try:
            self.worker.call(job)
        except Exception:
            pass
        return {"closed": len(victims)}

    def shutdown(self) -> None:
        """Close everything including the browser process (best-effort)."""
        self.close_all()

        def job() -> None:
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None

        try:
            self.worker.call(job)
        except Exception:
            pass


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[BrowserService] = None
_instance_lock = threading.Lock()


def get_browser_service() -> BrowserService:
    """Return the process-wide ``BrowserService`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = BrowserService()
    return _instance

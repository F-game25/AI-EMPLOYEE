#!/usr/bin/env python3
"""AI Employee — Live Auto-Updater

Polls the GitHub repository for new commits. When changes are detected:
  1. Downloads only the changed files from the GitHub raw CDN.
  2. Replaces the installed copies in AI_HOME (never touches user data).
  3. Hot-restarts only the agents whose source files changed.
  4. The overall system stays running throughout — no full shutdown needed.

Config (via ~/.ai-employee/.env):
  AI_EMPLOYEE_REPO=F-game25/AI-EMPLOYEE   # GitHub owner/repo
  AI_EMPLOYEE_BRANCH=main                 # branch to track
  AI_EMPLOYEE_UPDATE_INTERVAL=300         # poll interval seconds (default 5 min)
"""
import json
import logging
import os
import signal
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Bootstrap: load .env before anything else ────────────────────────────────
_env_file = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee")) / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(errors="replace").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ── Configuration ─────────────────────────────────────────────────────────────
AI_HOME  = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))
REPO     = os.environ.get("AI_EMPLOYEE_REPO",            "F-game25/AI-EMPLOYEE")
BRANCH   = os.environ.get("AI_EMPLOYEE_BRANCH",          "main")
INTERVAL = int(os.environ.get("AI_EMPLOYEE_UPDATE_INTERVAL", "300"))
# Optional: set GITHUB_TOKEN to avoid anonymous API rate limits (60 req/h → 5000 req/h)
_GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
API_BASE = f"https://api.github.com/repos/{REPO}"

TRIGGER_FILE = AI_HOME / "run"   / "updater.trigger"
STATE_FILE   = AI_HOME / "state" / "updater.json"
COMMIT_FILE  = AI_HOME / "state" / "installed_commit.txt"
LOG_FILE     = AI_HOME / "logs"  / "updater.log"

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [updater] %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger("updater")

# ── HTTP helpers ──────────────────────────────────────────────────────────────
_GH_HEADERS: dict[str, str] = {
    "Accept":     "application/vnd.github.v3+json",
    "User-Agent": "ai-employee-updater/2.0",
}
if _GH_TOKEN:
    _GH_HEADERS["Authorization"] = f"Bearer {_GH_TOKEN}"


def _sanitize_url(url: str) -> str:
    """Return a safe-to-log version of *url*: path only, no scheme/host/query."""
    try:
        return urllib.parse.urlparse(url).path
    except Exception:
        return "<invalid-url>"


def _gh_get(url: str, label: str = "request"):
    """Make an authenticated GET request to the GitHub API.

    *label* is used in log messages instead of the URL so that repo names and
    branch names (which come from environment variables) are never written to
    the log file, preventing CodeQL from flagging them as clear-text logging of
    sensitive data.
    """
    try:
        req = urllib.request.Request(url, headers=_GH_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        logger.warning("GitHub API HTTP %d (%s)", e.code, label)
    except Exception as e:
        logger.warning("GitHub API error (%s): %s - %s", label, type(e).__name__, e)
    return None


def _download_raw(repo_path: str, dest: Path, retries: int = 3) -> bool:
    """Download repo_path from the raw CDN and write it to dest atomically.

    Atomicity matters for shell entry-points like start.sh: bash holds an open
    file-descriptor to the inode it started reading.  A plain write_bytes()
    truncates that inode in-place, so bash sees corrupted content for lines it
    hasn't read yet.  Writing to a sibling temp-file and then os.replace()-ing
    it creates a new inode, leaving bash's open fd pointing at the old content
    for the lifetime of the current run.

    The download is retried up to *retries* times with exponential back-off to
    survive transient network hiccups.

    Note: raw.githubusercontent.com is a public CDN for public repos and does
    not require authentication.  The GitHub token is intentionally excluded here
    and used only for GitHub API calls (see _gh_get) to prevent the token from
    tainting the downloaded file content.
    """
    url = f"{RAW_BASE}/{repo_path}"
    # No Authorization header: raw CDN is public; keeping the token out of CDN
    # requests also prevents security scanners from flagging the downloaded
    # file bytes as "storing sensitive data".
    raw_headers = {"User-Agent": "ai-employee-updater/2.0"}
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=raw_headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.parent / f".{dest.name}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            return True
        except Exception as e:
            if attempt < retries:
                wait = 2 ** attempt
                logger.warning(
                    "Download failed for repo path '%s' (attempt %d/%d): %s — retrying in %ds",
                    repo_path,
                    attempt,
                    retries,
                    e,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "Download failed for repo path '%s' after %d attempts: %s",
                    repo_path,
                    retries,
                    e,
                )
    return False

# ── State helpers ─────────────────────────────────────────────────────────────

# Fields that must never be persisted to the on-disk state file
_STATE_SENSITIVE_KEYS = frozenset({
    "token", "api_key", "secret", "password",
    "github_token", "auth_token", "bearer_token", "access_token",
})


def _save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in data.items() if k.lower() not in _STATE_SENSITIVE_KEYS}
    STATE_FILE.write_text(json.dumps(safe, indent=2), encoding="utf-8")


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def _installed_sha() -> str:
    if COMMIT_FILE.exists():
        return COMMIT_FILE.read_text().strip()
    # Fallback: try git HEAD in AI_HOME
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(AI_HOME), timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _save_sha(sha: str) -> None:
    COMMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMMIT_FILE.write_text(sha, encoding="utf-8")


def _latest_sha() -> str:
    data = _gh_get(f"{API_BASE}/commits/{BRANCH}", label="latest commit")
    if data and isinstance(data, dict):
        return data.get("sha", "")
    return ""


def _changed_files(base_sha: str, head_sha: str) -> "list | None":
    """Return list of changed filenames between two commits.

    Returns:
        list  – on success (may be empty if no files changed).
        None  – if the GitHub API call failed (e.g. rate-limited or network error).

    Note: GitHub's compare API returns at most 300 files.  Very large commits may
    therefore show an incomplete diff; this is an upstream limitation.
    """
    data = _gh_get(f"{API_BASE}/compare/{base_sha}...{head_sha}", label="compare commits")
    if data is None:
        return None
    if isinstance(data, dict):
        return [f["filename"] for f in data.get("files", [])]
    return None

# ── File mapping ──────────────────────────────────────────────────────────────
# Never overwrite these — they contain user data or secrets
_SKIP_PREFIXES = ("runtime/config/", "runtime/state/")


def _repo_path_to_local(repo_path: str) -> "Path | None":
    """Map a repo file path (runtime/…) to its installed location in AI_HOME."""
    for skip in _SKIP_PREFIXES:
        if repo_path.startswith(skip):
            return None
    parts = Path(repo_path).parts
    if not parts or parts[0] != "runtime":
        return None
    rest = parts[1:]
    if not rest:
        return None
    return AI_HOME / Path(*rest)


def _bot_for_file(repo_path: str) -> "str | None":
    parts = Path(repo_path).parts
    if len(parts) >= 3 and parts[0] == "runtime" and parts[1] == "agents":
        return parts[2]
    return None

# ── Bot restart ───────────────────────────────────────────────────────────────

def _restart_bot(bot_name: str) -> None:
    ai_bin = AI_HOME / "bin" / "ai-employee"
    if not ai_bin.exists():
        logger.warning("ai-employee binary missing — cannot restart %s", bot_name)
        return
    try:
        import subprocess
        r = subprocess.run(
            [str(ai_bin), "restart", bot_name],
            capture_output=True, text=True, timeout=60,
        )
        out = (r.stdout + r.stderr).strip()
        logger.info("restart %s → %s", bot_name, out[:200] or "(ok)")
    except Exception as e:
        logger.warning("restart %s failed: %s", bot_name, e)

# ── Core update logic ─────────────────────────────────────────────────────────

def check_and_update(force: bool = False) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    state = _load_state()

    local_sha  = _installed_sha()
    remote_sha = _latest_sha()

    state.update({
        "last_check":       now,
        "local_sha":        local_sha,
        "remote_sha":       remote_sha,
        "interval_seconds": INTERVAL,
        "pid":              os.getpid(),
    })

    if not remote_sha:
        state["status"] = "check_failed"
        _save_state(state)
        logger.warning("Could not reach GitHub API — will retry in %ds", INTERVAL)
        return state

    if not local_sha:
        # First run after install without a commit file — bootstrap
        logger.info("No baseline SHA found — recording current remote SHA (%s)", remote_sha[:8])
        _save_sha(remote_sha)
        state["status"] = "initialized"
        state["local_sha"] = remote_sha
        _save_state(state)
        return state

    if local_sha == remote_sha and not force:
        state["status"] = "up_to_date"
        _save_state(state)
        logger.info("Up to date @ %s", local_sha[:8])
        return state

    logger.info("Update available: %s → %s", local_sha[:8], remote_sha[:8])
    state["status"] = "updating"
    _save_state(state)

    changed = _changed_files(local_sha, remote_sha)
    if changed is None:
        logger.warning("Could not diff commits (API rate-limit or network error) — will retry next cycle")
        state["status"] = "check_failed"
        _save_state(state)
        return state

    if not changed:
        logger.info("No files changed between %s and %s — recording new SHA", local_sha[:8], remote_sha[:8])
        _save_sha(remote_sha)
        state["status"] = "up_to_date"
        state["local_sha"] = remote_sha
        _save_state(state)
        return state

    logger.info("Changed files (%d): %s%s",
                len(changed), changed[:8], " …" if len(changed) > 8 else "")

    # ── Download updated files ────────────────────────────────────────────────
    downloaded: list = []
    skipped:    list = []

    for repo_path in changed:
        dest = _repo_path_to_local(repo_path)
        if dest is None:
            skipped.append(repo_path)
            continue
        if _download_raw(repo_path, dest):
            # Preserve execute bit for shell scripts and the CLI binary
            if dest.suffix == ".sh" or dest.name == "ai-employee":
                dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            downloaded.append(repo_path)
            logger.info("  ✓ %s", repo_path)
        else:
            skipped.append(repo_path)

    # ── Hot-restart only the agents whose files changed ─────────────────────────
    agents_to_restart: set = set()
    for repo_path in downloaded:
        bot = _bot_for_file(repo_path)
        if bot and bot not in ("ai-router",):   # ai-router is a library, not a service
            agents_to_restart.add(bot)

    restarted: list = []
    for bot in sorted(agents_to_restart):
        if bot == "auto-updater":
            # Our own files were updated — new code takes effect on next process restart
            logger.info("auto-updater updated — will use new code after next restart")
            continue
        _restart_bot(bot)
        restarted.append(bot)

    _save_sha(remote_sha)
    state.update({
        "status":           "updated",
        "last_update":      now,
        "update_sha":       remote_sha,
        "local_sha":        remote_sha,
        "changed_files":    changed,
        "downloaded_files": downloaded,
        "restarted_agents":   restarted,
    })
    _save_state(state)
    logger.info("✅ Update complete. Downloaded %d files, restarted: %s",
                len(downloaded), restarted or "none")
    return state

# ── Signal / trigger handling ─────────────────────────────────────────────────
_force_check = False
_wakeup      = threading.Event()   # set by SIGUSR1 to interrupt the sleep early
_shutdown    = threading.Event()   # set by SIGTERM/SIGINT for graceful exit


def _handle_sigusr1(sig, frame):
    global _force_check
    _force_check = True
    _wakeup.set()
    logger.info("SIGUSR1 received — triggering immediate update check")


def _handle_shutdown(sig, frame):  # noqa: ARG001
    logger.info("Signal %s received — auto-updater shutting down …", sig)
    _shutdown.set()
    _wakeup.set()   # wake the inner sleep so we exit promptly


# ── Main loop ─────────────────────────────────────────────────────────────────

def _once() -> None:
    """One-shot startup check: run check_and_update() once, print a brief
    summary to stdout, then exit.  Used by start.sh at boot time so that
    the latest code is in place before any bot is started."""
    import sys

    # Silence the console log handler for the one-shot run so the terminal
    # only shows the clean summary line we print ourselves.
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler) and h.stream in (
            sys.stdout, sys.stderr
        ):
            h.setLevel(logging.ERROR)

    try:
        result = check_and_update()
    except Exception as e:
        print(
            f"\033[1;33m⚠\033[0m Update check error: {type(e).__name__}: {e}",
            flush=True,
        )
        sys.exit(1)

    status = result.get("status", "unknown")
    if status == "updated":
        sha   = (result.get("update_sha") or "unknown")[:8]
        n     = len(result.get("downloaded_files", []))
        agents  = result.get("restarted_agents") or []
        bline = f", restarted: {', '.join(agents)}" if agents else ""
        print(
            f"\033[0;32m✓\033[0m Updated to {sha} — {n} file(s) downloaded{bline}",
            flush=True,
        )
    elif status in ("up_to_date", "initialized"):
        sha = (result.get("local_sha") or "unknown")[:8]
        print(f"\033[0;32m✓\033[0m AI Employee is up to date ({sha})", flush=True)
    else:
        print(
            f"\033[1;33m⚠\033[0m Update check returned: {status} "
            "(check logs for details)",
            flush=True,
        )


def main() -> None:
    import sys

    global _force_check  # modified by _handle_sigusr1 and the trigger-file check

    # ── One-shot startup mode (called by start.sh) ────────────────────────────
    if "--once" in sys.argv:
        _once()
        return

    # ── Background polling mode ───────────────────────────────────────────────
    logger.info("Auto-updater started  interval=%ds", INTERVAL)

    try:
        signal.signal(signal.SIGUSR1, _handle_sigusr1)
    except (AttributeError, OSError):
        pass  # SIGUSR1 not available on Windows

    try:
        signal.signal(signal.SIGTERM, _handle_shutdown)
        signal.signal(signal.SIGINT, _handle_shutdown)
    except (AttributeError, OSError):
        pass

    _save_state({
        "status":           "started",
        "started":          datetime.now(timezone.utc).isoformat(),
        "interval_seconds": INTERVAL,
        "pid":              os.getpid(),
    })

    # Let the rest of the system fully start before the first check
    _shutdown.wait(30)

    while not _shutdown.is_set():
        force = _force_check
        _force_check = False

        # Support trigger file written by the UI ("Check Now" / "Update Now" buttons).
        # Content "force" means force-download even if SHA matches.
        # Content "check" (or anything else) means a normal check without force.
        if TRIGGER_FILE.exists():
            try:
                content = TRIGGER_FILE.read_text().strip()
                TRIGGER_FILE.unlink()
                if content == "force":
                    force = True
                    logger.info("Trigger file 'force' — forcing update download")
                else:
                    logger.info("Trigger file '%s' — running update check", content)
            except Exception:
                pass

        try:
            check_and_update(force=force)
        except Exception as e:
            logger.exception("Updater loop error: %s", e)

        # Interruptible sleep: wake immediately when SIGUSR1 fires or every second
        # to catch a newly written trigger file (written by the UI buttons).
        _wakeup.clear()
        deadline = time.monotonic() + INTERVAL
        while not _shutdown.is_set() and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if _wakeup.wait(timeout=min(1.0, remaining)):
                break
            if TRIGGER_FILE.exists():
                break

    _save_state({"status": "stopped", "stopped": datetime.now(timezone.utc).isoformat()})
    logger.info("Auto-updater stopped.")


if __name__ == "__main__":
    main()

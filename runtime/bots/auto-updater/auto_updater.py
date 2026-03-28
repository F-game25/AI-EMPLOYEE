#!/usr/bin/env python3
"""AI Employee — Live Auto-Updater

Polls the GitHub repository for new commits. When changes are detected:
  1. Downloads only the changed files from the GitHub raw CDN.
  2. Replaces the installed copies in AI_HOME (never touches user data).
  3. Hot-restarts only the bots whose source files changed.
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
import time
import urllib.error
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
AI_HOME = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))
REPO    = os.environ.get("AI_EMPLOYEE_REPO",            "F-game25/AI-EMPLOYEE")
BRANCH  = os.environ.get("AI_EMPLOYEE_BRANCH",          "main")
INTERVAL = int(os.environ.get("AI_EMPLOYEE_UPDATE_INTERVAL", "300"))

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
_GH_HEADERS = {
    "Accept":     "application/vnd.github.v3+json",
    "User-Agent": "ai-employee-updater/2.0",
}


def _gh_get(url: str):
    try:
        req = urllib.request.Request(url, headers=_GH_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        logger.warning("GitHub API HTTP %d: %s", e.code, url)
    except Exception as e:
        logger.warning("GitHub API error (%s): %s", url, e)
    return None


def _download_raw(repo_path: str, dest: Path) -> bool:
    url = f"{RAW_BASE}/{repo_path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-employee-updater/2.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.read())
        return True
    except Exception as e:
        logger.warning("Download failed %s: %s", url, e)
    return False

# ── State helpers ─────────────────────────────────────────────────────────────

def _save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
    data = _gh_get(f"{API_BASE}/commits/{BRANCH}")
    if data and isinstance(data, dict):
        return data.get("sha", "")
    return ""


def _changed_files(base_sha: str, head_sha: str) -> list:
    data = _gh_get(f"{API_BASE}/compare/{base_sha}...{head_sha}")
    if data and isinstance(data, dict):
        return [f["filename"] for f in data.get("files", [])]
    return []

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
    if len(parts) >= 3 and parts[0] == "runtime" and parts[1] == "bots":
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
        "repo":             REPO,
        "branch":           BRANCH,
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
    if not changed:
        logger.warning("Could not diff commits (API limit?) — recording SHA without download")
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

    # ── Hot-restart only the bots whose files changed ─────────────────────────
    bots_to_restart: set = set()
    for repo_path in downloaded:
        bot = _bot_for_file(repo_path)
        if bot and bot not in ("ai-router",):   # ai-router is a library, not a service
            bots_to_restart.add(bot)

    restarted: list = []
    for bot in sorted(bots_to_restart):
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
        "restarted_bots":   restarted,
    })
    _save_state(state)
    logger.info("✅ Update complete. Downloaded %d files, restarted: %s",
                len(downloaded), restarted or "none")
    return state

# ── Signal / trigger handling ─────────────────────────────────────────────────
_force_check = False


def _handle_sigusr1(sig, frame):
    global _force_check
    _force_check = True
    logger.info("SIGUSR1 received — triggering immediate update check")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    global _force_check  # modified by _handle_sigusr1 and the trigger-file check

    logger.info("Auto-updater started  repo=%s  branch=%s  interval=%ds",
                REPO, BRANCH, INTERVAL)

    try:
        signal.signal(signal.SIGUSR1, _handle_sigusr1)
    except (AttributeError, OSError):
        pass  # SIGUSR1 not available on Windows

    _save_state({
        "status":           "started",
        "started":          datetime.now(timezone.utc).isoformat(),
        "repo":             REPO,
        "branch":           BRANCH,
        "interval_seconds": INTERVAL,
        "pid":              os.getpid(),
    })

    # Let the rest of the system fully start before the first check
    time.sleep(30)

    while True:
        force = _force_check
        _force_check = False

        # Support trigger file written by the UI ("Check Now" button)
        if TRIGGER_FILE.exists():
            try:
                TRIGGER_FILE.unlink()
            except Exception:
                pass
            force = True

        try:
            check_and_update(force=force)
        except Exception as e:
            logger.exception("Updater loop error: %s", e)

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

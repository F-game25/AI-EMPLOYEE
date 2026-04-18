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
import shutil
import sys as _sys
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
VERSION_FILE = AI_HOME / "state" / "version.json"
LOG_FILE     = AI_HOME / "logs"  / "updater.log"
GITHUB_COMPARE_API_FILE_LIMIT = 300

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
            if not data:
                raise ValueError(f"downloaded file is empty for {url} -> {dest}")
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


def _write_version_state(commit_sha: str, source: str = "auto-updater") -> None:
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_installed_commit": commit_sha,
        "last_installed_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    VERSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _runtime_files_at_sha(sha: str) -> "list | None":
    """Return all runtime/* file paths for the given commit SHA.

    Used as a safety fallback when GitHub compare results are likely truncated
    (compare API caps file lists at ~300 entries).
    """
    commit = _gh_get(f"{API_BASE}/commits/{sha}", label="commit metadata")
    if not isinstance(commit, dict):
        return None
    commit_info = commit.get("commit")
    if not isinstance(commit_info, dict):
        return None
    tree_info = commit_info.get("tree")
    if not isinstance(tree_info, dict):
        return None
    tree_sha = str(tree_info.get("sha", "")).strip()
    if not tree_sha:
        return None
    tree = _gh_get(f"{API_BASE}/git/trees/{tree_sha}?recursive=1", label="repository tree")
    if not isinstance(tree, dict):
        return None
    items = tree.get("tree")
    if not isinstance(items, list):
        return None
    runtime_files: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "blob":
            continue
        path = item.get("path")
        if isinstance(path, str) and path.startswith("runtime/"):
            runtime_files.append(path)
    return runtime_files

# ── Git-based repo update ─────────────────────────────────────────────────────
_REPO_DIR: "Path | None" = None

def _detect_repo_dir() -> "Path | None":
    """Return the repo root if running from a cloned git repository."""
    global _REPO_DIR
    if _REPO_DIR is not None:
        return _REPO_DIR if _REPO_DIR != Path() else None

    # Check AI_EMPLOYEE_REPO_DIR env var first
    env_dir = os.environ.get("AI_EMPLOYEE_REPO_DIR", "")
    if env_dir:
        p = Path(env_dir)
        if (p / ".git").is_dir() and (p / "backend" / "server.js").is_file():
            _REPO_DIR = p
            return _REPO_DIR

    # Walk up from AI_HOME looking for a git repo with the expected markers
    cur = AI_HOME
    for _ in range(6):
        if (cur / ".git").is_dir() and (cur / "backend" / "server.js").is_file():
            _REPO_DIR = cur
            return _REPO_DIR
        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    _REPO_DIR = Path()  # sentinel: no repo found
    return None


def _git_sync(branch: str = BRANCH) -> "tuple[bool, str]":
    """Perform a hard git sync to origin/<branch> in the repo directory.

    Before fetching, repairs any broken upstream tracking: if the current
    branch is pointing at a remote ref that no longer exists the stale
    upstream is unset and reset to origin/<branch> so that subsequent
    ``git pull`` invocations work without manual intervention.

    Returns (success, new_head_sha).
    """
    import subprocess

    repo = _detect_repo_dir()
    if repo is None:
        return False, ""

    # ── Repair broken upstream tracking ──────────────────────────────────────
    try:
        up_r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True, cwd=str(repo), timeout=10,
        )
        upstream = up_r.stdout.strip()  # e.g. "origin/copilot/redesign-chatbot-ui"
        if upstream:
            # Extract the remote branch name after "origin/"
            remote_branch = upstream.removeprefix("origin/")
            ls_r = subprocess.run(
                ["git", "ls-remote", "--exit-code", "origin", remote_branch],
                capture_output=True, text=True, cwd=str(repo), timeout=15,
            )
            if ls_r.returncode != 0:
                # Stale upstream — unset and re-point to the configured branch.
                # Use a static label in the log message to avoid CodeQL flagging
                # environment-sourced branch names as clear-text sensitive data.
                logger.info(
                    "Stale upstream tracking detected — resetting to configured branch",
                )
                cur_branch_r = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, cwd=str(repo), timeout=10,
                )
                cur_branch = cur_branch_r.stdout.strip()
                subprocess.run(
                    ["git", "branch", "--unset-upstream", cur_branch],
                    capture_output=True, text=True, cwd=str(repo), timeout=10,
                )
                subprocess.run(
                    ["git", "branch", "--set-upstream-to", f"origin/{branch}", cur_branch],
                    capture_output=True, text=True, cwd=str(repo), timeout=10,
                )
    except Exception as e:
        logger.warning("Could not check/repair upstream tracking: %s", e)

    cmd_fetch = ["git", "fetch", "origin"]
    cmd_reset = ["git", "reset", "--hard", f"origin/{branch}"]
    cmd_clean = ["git", "clean", "-fd"]
    step_names = {0: "fetch", 1: "reset", 2: "clean"}

    for step, cmd in enumerate((cmd_fetch, cmd_reset, cmd_clean)):
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(repo), timeout=120,
            )
            if r.returncode != 0:
                logger.warning("git %s failed (exit %d)", step_names[step], r.returncode)
                return False, ""
        except Exception as e:
            logger.warning("git %s error: %s", step_names[step], type(e).__name__)
            return False, ""

    # Read new HEAD
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(repo), timeout=10,
        )
        return True, r.stdout.strip()
    except Exception:
        return True, ""


def _rebuild_frontend(repo_dir: Path) -> bool:
    """Run npm install + npm run build in the frontend directory."""
    import subprocess

    frontend = repo_dir / "frontend"
    if not (frontend / "package.json").is_file():
        logger.warning("frontend/package.json not found — skipping rebuild")
        return False

    logger.info("Rebuilding frontend bundle...")
    try:
        # Install dependencies if needed
        if not (frontend / "node_modules").is_dir():
            logger.info("  Installing frontend dependencies...")
            r = subprocess.run(
                ["npm", "install", "--silent"],
                capture_output=True, text=True, cwd=str(frontend), timeout=300,
            )
            if r.returncode != 0:
                logger.warning("npm install failed: %s", r.stderr.strip()[:300])
                return False

        # Clean old dist
        dist = frontend / "dist"
        if dist.is_dir():
            shutil.rmtree(dist, ignore_errors=True)

        # Build
        env = {**os.environ}
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=str(repo_dir), timeout=10,
            ).stdout.strip()
        except Exception:
            sha = "unknown"
        env["VITE_APP_VERSION"] = sha

        r = subprocess.run(
            ["npm", "run", "build"],
            capture_output=True, text=True, cwd=str(frontend), timeout=300,
            env=env,
        )
        if r.returncode != 0:
            logger.warning("Frontend build failed: %s", r.stderr.strip()[:300])
            return False

        logger.info("  ✓ Frontend build complete")
        return True
    except Exception as e:
        logger.warning("Frontend rebuild error: %s", e)
        return False


# ── File mapping ──────────────────────────────────────────────────────────────
# Never overwrite these — they contain user data or secrets
_SKIP_PREFIXES = ("runtime/config/", "runtime/state/")

# Top-level repo directories/files that should be synced to AI_HOME in CDN mode
_REPO_TOPLEVEL_DIRS = ("backend/", "frontend/", "scripts/")
_REPO_TOPLEVEL_FILES = ("start.sh", "stop.sh", "package.json", "package-lock.json")


def _repo_path_to_local(repo_path: str) -> "Path | None":
    """Map a repo file path to its installed location in AI_HOME.

    Handles runtime/ files (mapped to AI_HOME root) as well as backend/,
    frontend/, scripts/, and top-level files (mapped to AI_HOME/<same path>).
    """
    for skip in _SKIP_PREFIXES:
        if repo_path.startswith(skip):
            return None
    parts = Path(repo_path).parts
    if not parts:
        return None

    # runtime/ → AI_HOME/<rest>  (existing behaviour)
    if parts[0] == "runtime":
        rest = parts[1:]
        if not rest:
            return None
        return AI_HOME / Path(*rest)

    # backend/, frontend/, scripts/ → AI_HOME/<full path>
    for prefix in _REPO_TOPLEVEL_DIRS:
        if repo_path.startswith(prefix):
            return AI_HOME / Path(*parts)

    # Top-level files (start.sh, stop.sh, etc.) → AI_HOME/<filename>
    if len(parts) == 1 and parts[0] in _REPO_TOPLEVEL_FILES:
        return AI_HOME / parts[0]

    return None


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

# ── Terminal progress bar ──────────────────────────────────────────────────────


class TerminalProgress:
    """A simple terminal progress bar for file downloads.

    Usage::

        bar = TerminalProgress(total=12, label="Downloading")
        for i in range(12):
            bar.update(i + 1, detail="runtime/agents/foo/bar.py")
        bar.finish()
    """

    G = "\033[0;32m"
    C = "\033[0;36m"
    Y = "\033[1;33m"
    NC = "\033[0m"
    FILL = "█"
    EMPTY = "░"

    def __init__(self, total: int, label: str = "Downloading", width: int = 0):
        self.total = max(total, 1)
        self.label = label
        # Auto-detect terminal width; cap bar at 40 chars.
        if width <= 0:
            try:
                width = min(shutil.get_terminal_size((80, 24)).columns - 40, 40)
            except Exception:
                width = 30
        self.width = max(width, 10)
        self._stream = _sys.stderr

    def update(self, current: int, detail: str = "") -> None:
        pct = current / self.total
        filled = int(self.width * pct)
        bar = self.FILL * filled + self.EMPTY * (self.width - filled)
        # Truncate detail to keep the line short
        short = detail.rsplit("/", 1)[-1] if detail else ""
        if len(short) > 25:
            short = "…" + short[-24:]
        line = (
            f"\r  {self.C}{self.label}{self.NC} "
            f"[{self.G}{bar}{self.NC}] "
            f"{current}/{self.total} "
            f"{self.Y}{short}{self.NC}"
        )
        self._stream.write(line)
        self._stream.flush()

    def finish(self, message: str = "") -> None:
        pct_bar = self.FILL * self.width
        done = message or "done"
        line = (
            f"\r  {self.C}{self.label}{self.NC} "
            f"[{self.G}{pct_bar}{self.NC}] "
            f"{self.total}/{self.total} "
            f"{self.G}{done}{self.NC}"
        )
        self._stream.write(line + "\n")
        self._stream.flush()


# ── Core update logic ─────────────────────────────────────────────────────────

def _check_and_update_git(remote_sha: str, local_sha: str, state: dict, now: str) -> "dict | None":
    """Attempt a git-based update when running from a cloned repo.

    Parameters:
        remote_sha: The latest commit SHA on the tracked remote branch.
        local_sha:  The currently installed/checked-out commit SHA.
        state:      Mutable state dict that will be persisted after the update.
        now:        ISO-8601 timestamp string for the current check time.

    Returns:
        A state dict on success (git sync completed), or ``None`` to signal
        that the caller should fall back to the CDN file-by-file download path.
    """
    repo_dir = _detect_repo_dir()
    if repo_dir is None:
        return None

    logger.info("Git repo detected — using git sync")

    # Determine which files changed (for frontend rebuild detection)
    changed = _changed_files(local_sha, remote_sha)

    # Hard reset to origin/branch
    ok, new_sha = _git_sync()
    if not ok:
        logger.warning("Git sync failed — falling back to CDN mode")
        return None

    final_sha = new_sha or remote_sha

    # Rebuild frontend if any frontend/ files changed (or if we can't tell)
    frontend_changed = changed is None or any(
        f.startswith("frontend/") for f in (changed or [])
    )
    if frontend_changed:
        _rebuild_frontend(repo_dir)

    _save_sha(final_sha)
    _write_version_state(final_sha, source="auto-updater:git-sync")

    # Also write version.json at repo root state/ directory
    repo_version = repo_dir / "state" / "version.json"
    repo_version.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_commit": final_sha,
        "last_updated_at": now,
        "source": "auto-updater:git-sync",
    }
    repo_version.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    state.update({
        "status":         "updated",
        "last_update":    now,
        "update_sha":     final_sha,
        "local_sha":      final_sha,
        "update_mode":    "git",
        "changed_files":  changed or [],
        "frontend_rebuilt": frontend_changed,
    })
    _save_state(state)
    logger.info("✅ Git sync complete → %s", final_sha[:8])
    return state


def check_and_update(force: bool = False, progress_cb=None) -> dict:
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
        _write_version_state(remote_sha, source="auto-updater:init")
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

    # ── Try git-based update first (when running from a cloned repo) ──────────
    git_result = _check_and_update_git(remote_sha, local_sha, state, now)
    if git_result is not None:
        return git_result

    # ── Fallback: CDN file-by-file download ───────────────────────────────────
    changed = _changed_files(local_sha, remote_sha)
    if changed is None:
        logger.warning("Could not diff commits (API rate-limit or network error) — will retry next cycle")
        state["status"] = "check_failed"
        _save_state(state)
        return state

    # GitHub compare API returns at most 300 changed files. For large updates,
    # use a conservative full runtime sync to avoid silently missing UI changes.
    if len(changed) == GITHUB_COMPARE_API_FILE_LIMIT:
        logger.warning(
            "Compare API returned %d files (likely capped). Falling back to full runtime sync.",
            len(changed),
        )
        runtime_files = _runtime_files_at_sha(remote_sha)
        if runtime_files:
            changed = sorted(set(changed).union(runtime_files))
            logger.info("Fallback added %d runtime file(s) for safe update coverage", len(runtime_files))
        else:
            logger.warning("Runtime fallback file listing failed — proceeding with compare API result only")

    if not changed:
        logger.info("No files changed between %s and %s — recording new SHA", local_sha[:8], remote_sha[:8])
        _save_sha(remote_sha)
        _write_version_state(remote_sha, source="auto-updater:no-diff")
        state["status"] = "up_to_date"
        state["local_sha"] = remote_sha
        _save_state(state)
        return state

    logger.info("Changed files (%d): %s%s",
                len(changed), changed[:8], " …" if len(changed) > 8 else "")

    # ── Download updated files ────────────────────────────────────────────────
    downloaded: list = []
    skipped:    list = []
    # Count only files that map to a local path (the ones we actually download).
    total_dl = sum(1 for p in changed if _repo_path_to_local(p) is not None)
    dl_idx = 0

    for repo_path in changed:
        dest = _repo_path_to_local(repo_path)
        if dest is None:
            skipped.append(repo_path)
            continue
        dl_idx += 1
        if progress_cb is not None:
            progress_cb(dl_idx, total_dl, repo_path)
        if _download_raw(repo_path, dest):
            # Preserve execute bit for shell scripts and the CLI binary
            if dest.suffix == ".sh" or dest.name == "ai-employee":
                dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            downloaded.append(repo_path)
            logger.info("  ✓ %s", repo_path)
        else:
            skipped.append(repo_path)

    # ── Rebuild frontend if any frontend/ files were downloaded ────────────────
    frontend_changed = any(p.startswith("frontend/") for p in downloaded)
    if frontend_changed:
        # Attempt rebuild using AI_HOME/frontend or repo dir
        fe_dir = AI_HOME / "frontend"
        if (fe_dir / "package.json").is_file():
            _rebuild_frontend(AI_HOME)
        else:
            repo_dir = _detect_repo_dir()
            if repo_dir is not None:
                _rebuild_frontend(repo_dir)

    # ── Hot-restart only the agents whose files changed ─────────────────────────
    agents_to_restart: set = set()
    for repo_path in downloaded:
        bot = _bot_for_file(repo_path)
        if bot and bot not in ("ai-router",):   # ai-router is a library, not a service
            agents_to_restart.add(bot)

    # Backend changes require a UI restart to pick up the new server.js
    backend_changed = any(p.startswith("backend/") for p in downloaded)
    if backend_changed:
        agents_to_restart.add("problem-solver-ui")

    restarted: list = []
    for bot in sorted(agents_to_restart):
        if bot == "auto-updater":
            # Our own files were updated — new code takes effect on next process restart
            logger.info("auto-updater updated — will use new code after next restart")
            continue
        _restart_bot(bot)
        restarted.append(bot)

    _save_sha(remote_sha)
    _write_version_state(remote_sha, source="auto-updater:update")
    state.update({
        "status":             "updated",
        "last_update":        now,
        "update_sha":         remote_sha,
        "local_sha":          remote_sha,
        "update_mode":        "cdn",
        "changed_files":      changed,
        "downloaded_files":   downloaded,
        "restarted_agents":   restarted,
        "frontend_rebuilt":   frontend_changed,
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


def _handle_shutdown(signum, frame):  # noqa: ARG001
    logger.info("Signal %s received -- auto-updater shutting down ...", signum)
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

    # ── Progress bar for download phase ──────────────────────────────────────
    _bar = None

    def _progress(current: int, total: int, filename: str) -> None:
        nonlocal _bar
        if _bar is None:
            _bar = TerminalProgress(total=total, label="Updating")
        _bar.update(current, detail=filename)

    try:
        result = check_and_update(progress_cb=_progress)
    except Exception as e:
        if _bar is not None:
            _bar.finish("error")
        print(
            f"\033[1;33m⚠\033[0m Update check error: {type(e).__name__}: {e}",
            flush=True,
        )
        sys.exit(1)

    if _bar is not None:
        _bar.finish("complete")

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

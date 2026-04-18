#!/usr/bin/env bash
# AI Employee — Git Auto-Sync
# Usage: bash scripts/sync.sh
# Or run automatically every X minutes (see scripts/sync-watch.sh and scripts/setup-cron.sh)

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

log_dir="$HOME/.ai-employee/logs"
log_file="$log_dir/sync.log"

# ── 1. Safety checks ──────────────────────────────────────────────────────────
echo -e "${CYAN}── AI Employee Git Sync ──────────────────────────────────────────${NC}"

if ! command -v git &>/dev/null; then
  echo -e "${RED}✗ git is not installed. Please install git and retry.${NC}"
  exit 1
fi

if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo -e "${RED}✗ Not inside a git repository. Run this script from the repo root.${NC}"
  exit 1
fi

if ! git remote get-url origin &>/dev/null; then
  echo -e "${RED}✗ No remote named 'origin' found. Add one with: git remote add origin <url>${NC}"
  exit 1
fi

if ! ping -c1 -W3 github.com &>/dev/null 2>&1 && \
   ! curl -sf --max-time 5 https://github.com &>/dev/null; then
  echo -e "${RED}✗ Cannot reach github.com. Check your internet connection and retry.${NC}"
  exit 1
fi

# ── 2. Repair broken upstream tracking ───────────────────────────────────────
# Detect if the current branch is tracking a remote ref that does not exist,
# which causes `git pull` to fail. Reset tracking to origin/main in that case.
echo ""
echo -e "${CYAN}Checking branch tracking…${NC}"
_CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
_UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"

if [[ -z "$_UPSTREAM" ]]; then
  echo -e "${YELLOW}⚠  No upstream set for branch '$_CURRENT_BRANCH'. Setting to origin/main.${NC}"
  git branch --set-upstream-to=origin/main "$_CURRENT_BRANCH" 2>/dev/null \
    || echo -e "${YELLOW}  (Could not set upstream — will fetch origin/main directly.)${NC}"
elif ! git ls-remote --exit-code origin "${_UPSTREAM#origin/}" &>/dev/null; then
  echo -e "${YELLOW}⚠  Tracked upstream '$_UPSTREAM' does not exist on remote.${NC}"
  echo -e "${YELLOW}   Unsetting stale tracking and switching to origin/main.${NC}"
  git branch --unset-upstream "$_CURRENT_BRANCH" 2>/dev/null || true
  git branch --set-upstream-to=origin/main "$_CURRENT_BRANCH" 2>/dev/null \
    || echo -e "${YELLOW}  (Could not set upstream — will fetch origin/main directly.)${NC}"
  _UPSTREAM="origin/main"
else
  echo -e "${GREEN}✔ Branch '$_CURRENT_BRANCH' correctly tracks '$_UPSTREAM'.${NC}"
fi

# ── 3. Show current status ────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}Current status:${NC}"
git fetch origin --quiet

STATUS_OUTPUT="$(git status --short)"
if [[ -n "$STATUS_OUTPUT" ]]; then
  echo "$STATUS_OUTPUT"
else
  echo "  (working tree clean)"
fi

UNPUSHED="$(git log origin/main..HEAD --oneline 2>/dev/null || true)"
if [[ -n "$UNPUSHED" ]]; then
  echo ""
  echo -e "${CYAN}Local commits not yet pushed:${NC}"
  echo "$UNPUSHED"
fi

# ── 4. Pull latest from GitHub ────────────────────────────────────────────────
UPSTREAM_CHANGES="$(git log HEAD..origin/main --oneline 2>/dev/null || true)"
_PULLED=0

if [[ -n "$UPSTREAM_CHANGES" ]]; then
  echo ""
  echo -e "${CYAN}Pulling upstream changes…${NC}"
  if ! git pull --rebase origin main; then
    git rebase --abort 2>/dev/null || true
    echo ""
    echo -e "${RED}✗ Rebase failed due to conflicts. Nothing was pushed.${NC}"
    echo -e "${YELLOW}Conflicting files:${NC}"
    git diff --name-only --diff-filter=U 2>/dev/null || git ls-files --unmerged | awk '{print $4}' | sort -u
    echo ""
    echo -e "${YELLOW}Resolve conflicts manually, then run this script again.${NC}"
    exit 1
  fi
  echo -e "${GREEN}✔ Pulled and rebased successfully.${NC}"
  _PULLED=1
fi

# ── 5. Rebuild UI bundle & clear stale runtime cache after a pull ─────────────
# Always rebuild when new commits were pulled so the browser sees the latest UI.
# Also purge Python bytecode caches to prevent stale .pyc files from hiding
# runtime code changes.
REPO_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ "$_PULLED" -eq 1 ]]; then
  echo ""
  echo -e "${CYAN}Clearing stale runtime cache (*.pyc / __pycache__)…${NC}"
  find "$REPO_DIR" \( -type d -name "__pycache__" -exec rm -rf {} + \) \
    -o \( -type f -name "*.pyc" -delete \) 2>/dev/null || true
  echo -e "${GREEN}✔ Cache cleared.${NC}"

  if [[ -f "$REPO_DIR/frontend/package.json" ]]; then
    echo ""
    echo -e "${CYAN}Rebuilding UI bundle (frontend changed)…${NC}"
    if [[ ! -d "$REPO_DIR/frontend/node_modules" ]]; then
      npm --prefix "$REPO_DIR/frontend" install --silent \
        || npm --prefix "$REPO_DIR/frontend" install
    fi
    rm -rf "$REPO_DIR/frontend/dist"
    _APP_VER="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    if VITE_APP_VERSION="$_APP_VER" npm --prefix "$REPO_DIR/frontend" run build; then
      echo -e "${GREEN}✔ UI bundle rebuilt (version: ${_APP_VER}).${NC}"
      echo -e "${YELLOW}  Restart the server to serve the new bundle: bash start.sh${NC}"
    else
      echo -e "${RED}✗ Frontend build failed — check the output above.${NC}"
    fi
  fi
fi

# ── 6. Commit local changes if any ───────────────────────────────────────────
DIRTY="$(git status --porcelain)"
if [[ -n "$DIRTY" ]]; then
  AUTO_MSG="sync: auto-commit $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""
  echo -e "${CYAN}Committing local changes…${NC}"
  git add -A
  git commit -m "$AUTO_MSG"
  echo -e "${GREEN}✔ Committed: ${AUTO_MSG}${NC}"
else
  echo ""
  echo "  (no local changes to commit)"
fi

# ── 7. Push to GitHub ─────────────────────────────────────────────────────────
COMMITS_TO_PUSH="$(git log origin/main..HEAD --oneline 2>/dev/null || true)"
PUSH_COUNT=0
if [[ -n "$COMMITS_TO_PUSH" ]]; then
  PUSH_COUNT="$(echo "$COMMITS_TO_PUSH" | wc -l | tr -d ' ')"
fi

echo ""
echo -e "${CYAN}Pushing to origin/main…${NC}"
if ! git push origin main; then
  echo ""
  echo -e "${RED}✗ Push failed. Possible causes:${NC}"
  echo "  • SSH key not added to GitHub (check: ssh -T git@github.com)"
  echo "  • Token expired or missing write access"
  echo "  • Remote has changes you haven't pulled — run the script again"
  exit 1
fi

if [[ "$PUSH_COUNT" -gt 0 ]]; then
  echo -e "${GREEN}✔ Pushed ${PUSH_COUNT} commit(s) to origin/main.${NC}"
else
  echo -e "${GREEN}✔ origin/main is already up to date.${NC}"
fi

# ── 8. Log the result ─────────────────────────────────────────────────────────
mkdir -p "$log_dir"
SHORT_SHA="$(git rev-parse --short HEAD)"
echo "$(date '+%Y-%m-%d %H:%M:%S') | sync complete | $SHORT_SHA" >> "$log_file"

# ── 9. Print summary ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✅ Sync complete${NC}"
echo "   Local:  $(git rev-parse --short HEAD) ($(git log -1 --format='%s'))"
echo "   Remote: origin/main is up to date"
echo "   Log:    $log_file"
echo ""

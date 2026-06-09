#!/usr/bin/env bash
# cleanup-for-windows-download.sh
# Makes the repo clone/download cleanly and run on Windows.
# SAFE: untracks junk (keeps files on disk), adds .gitattributes. Does NOT commit.
#
# Review, then run:   bash scripts/cleanup-for-windows-download.sh
# Inspect with:       git status   (nothing is committed by this script)
# Undo everything:    git reset --hard   (ONLY if you have no other uncommitted work)
#
# What it does:
#   1. git rm --cached the 55 runtime/junk files that .gitignore already lists
#      but that were committed before being ignored (so they keep shipping).
#   2. Writes .gitattributes so Windows gets correct line endings
#      (LF for shell scripts, CRLF for .bat/.ps1) — fixes Git Bash "bad interpreter".
# It does NOT delete anything from your disk and does NOT commit or push.

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

echo "=== 1/2  Untracking committed runtime/junk (files stay on disk) ==="

# These globs match exactly what .gitignore already declares. --cached = untrack only.
# --ignore-unmatch so it never errors if a path is already gone.
git rm -r --cached --ignore-unmatch \
  'python-backend.pid' \
  'state/*.db' 'state/*.db-shm' 'state/*.db-wal' \
  'state/*.jsonl' \
  'state/agents.json' \
  'state/artifacts' \
  'state/codex_cache' \
  'ascend-ai-archived/backend/state/memory.db' \
  '**/__pycache__' \
  '*.pyc' \
  >/dev/null

# Belt-and-suspenders: catch any remaining __pycache__/.pyc the globs missed.
# grep returns non-zero when nothing matches; that's fine under set -e.
remaining=$(git ls-files | grep -E '(__pycache__/|\.pyc$)' || true)
if [ -n "$remaining" ]; then
  echo "$remaining" | while read -r f; do
    git rm --cached --ignore-unmatch "$f" >/dev/null
  done
fi

untracked_count=$(git status --porcelain | grep -c '^D ' || true)
echo "  untracked $untracked_count files (still present on disk)"

echo "=== 2/2  Writing .gitattributes (Windows line-ending safety) ==="
cat > .gitattributes <<'EOF'
# Normalize line endings so a Windows clone runs without "bad interpreter".
# Text files are LF in the repo; checked out per-rule below.
* text=auto eol=lf

# Shell / Python / config MUST stay LF (run under Git Bash / WSL / Docker on Windows).
*.sh    text eol=lf
*.bash  text eol=lf
*.py    text eol=lf
*.json  text eol=lf
*.yml   text eol=lf
*.yaml  text eol=lf
*.toml  text eol=lf
Dockerfile text eol=lf

# Windows-native launchers MUST be CRLF.
*.bat   text eol=crlf
*.cmd   text eol=crlf
*.ps1   text eol=crlf

# Binary assets — never touch.
*.png   binary
*.jpg   binary
*.jpeg  binary
*.gif   binary
*.ico   binary
*.icns  binary
*.db    binary
*.woff  binary
*.woff2 binary
*.ttf   binary
EOF
echo "  wrote .gitattributes"

echo "=== 3/3 (OPTIONAL)  Tidy root doc clutter into docs/archive/ ==="
echo "  Set TIDY_DOCS=1 to move 42 status/phase docs out of the root."
if [[ "${TIDY_DOCS:-0}" == "1" ]]; then
  mkdir -p docs/archive
  # Move only status/phase/summary docs. Keep entry points (README, INSTALL,
  # START_HERE, QUICKSTART, GETTING_STARTED, WINDOWS, CLAUDE, AGENTS, SECURITY,
  # CONTRIBUTING, LICENSE) at the root.
  moved=0
  for f in $(git ls-files | grep -vE '/' | grep -iE '(^PHASE|SUMMARY|DELIVERY|DELIVERABLE|_COMPLETE|BEFORE_AFTER|WHAT_CHANGED|EFFICIENCY_REPORT|FINAL_)' ); do
    git mv "$f" "docs/archive/$f" 2>/dev/null && moved=$((moved+1)) || true
  done
  echo "  moved $moved docs into docs/archive/ (staged, not committed)"
else
  echo "  skipped (run with: TIDY_DOCS=1 bash scripts/cleanup-for-windows-download.sh)"
fi

echo ""
echo "=== DONE (nothing committed) ==="
echo "Next:"
echo "  1. Review:        git status"
echo "  2. Verify junk gone from tracking:"
echo "       git ls-files | grep -E '(__pycache__|\\.pyc\$|\\.pid\$|state/.*\\.db)'   # should be empty"
echo "  3. Test a clean clone locally:"
echo "       git stash && git clone . /tmp/ai-emp-test && ls /tmp/ai-emp-test/state"
echo "  4. When happy, commit:"
echo "       git add -A && git commit -m 'chore: untrack runtime state, add .gitattributes for Windows'"

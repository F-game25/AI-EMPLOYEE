#!/usr/bin/env bash
# AI Employee — Clone to Local Machine
# Usage: bash scripts/clone-to-local.sh [target_directory]
# Default target: /home/$USER/AI-EMPLOYEE
#
# Run this on a fresh machine where the repo has not been downloaded yet.

TARGET="${1:-$HOME/AI-EMPLOYEE}"

if [[ -d "$TARGET/.git" ]]; then
  echo "Repo already exists at $TARGET"
  echo "To update it run: bash $TARGET/scripts/sync.sh"
  exit 0
fi

echo "Cloning AI Employee to $TARGET ..."
git clone https://github.com/F-game25/AI-EMPLOYEE "$TARGET"
echo ""
echo "✅ Done! Your local copy is at: $TARGET"
echo ""
echo "Next steps:"
echo "  cd $TARGET && bash install.sh    # install"
echo "  bash scripts/sync.sh             # sync anytime"

#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/problem-solver-ui"

if [[ -f "$AI_HOME/config/problem-solver-ui.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver-ui.env"
  set +a
fi

python3 "$BOT_HOME/server.py"

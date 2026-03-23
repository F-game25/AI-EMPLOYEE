#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/problem-solver"

if [[ -f "$AI_HOME/config/problem-solver.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver.env"
  set +a
fi

exec python3 "$BOT_HOME/problem_solver.py"

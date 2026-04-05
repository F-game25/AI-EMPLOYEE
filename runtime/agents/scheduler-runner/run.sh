#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/scheduler-runner"

if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/.env"
  set +a
fi

if [[ -f "$AI_HOME/config/scheduler-runner.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/scheduler-runner.env"
  set +a
fi

exec python3 "$AGENT_HOME/scheduler.py"

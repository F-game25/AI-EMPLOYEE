#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/status-reporter"

if [[ -f "$AI_HOME/config/status-reporter.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/status-reporter.env"
  set +a
fi

exec python3 "$AGENT_HOME/status_reporter.py"

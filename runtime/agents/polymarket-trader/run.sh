#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/polymarket-trader"

if [[ -f "$AI_HOME/config/polymarket-trader.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/polymarket-trader.env"
  set +a
fi

exec python3 "$AGENT_HOME/trader.py"

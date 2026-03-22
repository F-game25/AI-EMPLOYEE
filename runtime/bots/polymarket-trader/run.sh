#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/polymarket-trader"

if [[ -f "$AI_HOME/config/polymarket-trader.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/polymarket-trader.env"
  set +a
fi

python3 "$BOT_HOME/trader.py"

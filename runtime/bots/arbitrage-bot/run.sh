#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/arbitrage-bot"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/arbitrage-bot.env" ]]; then set -a; source "$AI_HOME/config/arbitrage-bot.env"; set +a; fi
python3 "$BOT_HOME/arbitrage_bot.py"

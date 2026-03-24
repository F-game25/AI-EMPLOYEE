#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/project-manager"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/project-manager.env" ]]; then set -a; source "$AI_HOME/config/project-manager.env"; set +a; fi
python3 "$BOT_HOME/project_manager.py"

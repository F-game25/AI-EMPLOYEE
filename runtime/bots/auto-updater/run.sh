#!/usr/bin/env bash
# AI Employee — Auto-Updater bot runner
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"

# Load .env so AI_EMPLOYEE_REPO / AI_EMPLOYEE_BRANCH / AI_EMPLOYEE_UPDATE_INTERVAL are visible
if [[ -f "$AI_HOME/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$AI_HOME/.env"
    set +a
fi

exec python3 "$AI_HOME/bots/auto-updater/auto_updater.py"

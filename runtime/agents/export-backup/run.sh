#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/export-backup"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/export-backup.env" ]]; then set -a; source "$AI_HOME/config/export-backup.env"; set +a; fi
exec python3 "$AGENT_HOME/export_backup.py"

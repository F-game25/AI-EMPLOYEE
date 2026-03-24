#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/course-creator"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/course-creator.env" ]]; then set -a; source "$AI_HOME/config/course-creator.env"; set +a; fi
python3 "$BOT_HOME/course_creator.py"

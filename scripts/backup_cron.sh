#!/usr/bin/env bash
# Daily backup cron — run as: 0 2 * * * /path/to/backup_cron.sh
set -euo pipefail

source ~/.ai-employee/.env 2>/dev/null || true

cd "$(dirname "$0")/.."

python3 -c "
import sys
sys.path.insert(0, 'runtime')
from core.backup import BackupManager
result = BackupManager().full_backup_cycle(upload=True)
print(f'Backup: {result}')
exit(0 if result.get('file') else 1)
"

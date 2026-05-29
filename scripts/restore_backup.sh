#!/usr/bin/env bash
# Point-in-time restore: ./restore_backup.sh [<backup_file.dump>]
# Lists available backups if no argument is given.
set -euo pipefail

source ~/.ai-employee/.env 2>/dev/null || true

cd "$(dirname "$0")/.."

# No argument — list available backups and exit
if [[ $# -eq 0 ]]; then
    python3 -c "
import sys, json
sys.path.insert(0, 'runtime')
from core.backup import BackupManager
backups = BackupManager().list_backups()
if not backups:
    print('No local backups found.')
    sys.exit(0)
print(f'{'FILE':<45} {'SIZE (MB)':>10} {'AGE (days)':>11} {'CREATED AT':<20}')
print('-' * 90)
for b in backups:
    print(f\"{b['file']:<45} {b['size_mb']:>10.3f} {b['age_days']:>11} {b['created_at']:<20}\")
"
    exit 0
fi

BACKUP_FILE="$1"

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "ERROR: File not found: $BACKUP_FILE" >&2
    exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL is not set." >&2
    exit 1
fi

read -r -p "Restore $BACKUP_FILE to $DATABASE_URL? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
fi

echo "Restoring $BACKUP_FILE ..."
pg_restore -d "$DATABASE_URL" "$BACKUP_FILE"
echo "Restore complete."

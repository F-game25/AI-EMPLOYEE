#!/usr/bin/env bash
# Disaster recovery restore from Velero backup.
set -euo pipefail

NAMESPACE="${NAMESPACE:-nexus}"
BACKUP_NAME="${BACKUP_NAME:-}"
RESTORE_NAME="${RESTORE_NAME:-dr-restore-$(date +%Y%m%d-%H%M%S)}"

if [[ -z "${BACKUP_NAME}" ]]; then
  echo "Available backups:"
  velero backup get -n velero 2>/dev/null || echo "  (velero not available — list backups manually)"
  echo ""
  echo "Usage: BACKUP_NAME=<backup-name> bash deploy/dr-restore.sh"
  exit 1
fi

echo "Starting disaster recovery restore:"
echo "  Backup:    ${BACKUP_NAME}"
echo "  Namespace: ${NAMESPACE}"
echo "  Restore:   ${RESTORE_NAME}"
read -rp "Proceed? [y/N] " confirm
[[ "${confirm}" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# Scale down current deployment
kubectl scale deployment --all --replicas=0 -n "${NAMESPACE}" || true

# Trigger Velero restore
velero restore create "${RESTORE_NAME}" \
  --from-backup "${BACKUP_NAME}" \
  --include-namespaces "${NAMESPACE}" \
  --wait

echo "Restore ${RESTORE_NAME} completed."
echo "Running smoke tests..."
sleep 30
BASE_URL="${BASE_URL:-http://localhost:8787}" bash deploy/smoke-test.sh

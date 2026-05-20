#!/usr/bin/env bash
# Blue/green traffic swap via ingress patch.
set -euo pipefail

NAMESPACE="${NAMESPACE:-nexus}"
RELEASE="${RELEASE:-aeternus-nexus}"
SLOT="${SLOT:-green}"   # 'blue' or 'green'
DEPLOYMENT="${DEPLOYMENT:-${RELEASE}}"

echo "Switching traffic to slot: ${SLOT}"

# Patch ingress to point to the active slot
kubectl patch ingress "${RELEASE}" \
  -n "${NAMESPACE}" \
  --type json \
  -p "[{\"op\":\"replace\",\"path\":\"/spec/rules/0/http/paths/0/backend/service/name\",\"value\":\"${DEPLOYMENT}-node-${SLOT}\"}]"

# Record active slot in ConfigMap
kubectl patch configmap "${RELEASE}-active-slot" \
  -n "${NAMESPACE}" \
  --type merge \
  -p "{\"data\":{\"slot\":\"${SLOT}\",\"switched_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}" \
  2>/dev/null || \
kubectl create configmap "${RELEASE}-active-slot" \
  -n "${NAMESPACE}" \
  --from-literal="slot=${SLOT}" \
  --from-literal="switched_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "Traffic now routed to: ${SLOT}"
echo "Previous slot is idle — scale down with: SLOT=$([ "${SLOT}" = "blue" ] && echo green || echo blue) bash deploy/blue-green-scale-down.sh"

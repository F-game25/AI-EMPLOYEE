'use strict';

/**
 * Security Event Forwarder
 *
 * Fire-and-forget bridge that ships Node-originated security telemetry
 * (vault/secrets access, auth, etc.) to the Python AI backend, where the
 * in-process BlacklightEngine sentinel scores and responds to attacks.
 *
 * Guarantees:
 *   - NEVER throws (telemetry must never break the secrets read path)
 *   - Times out fast (~2s) and does not block the caller
 *   - Forwards key paths/names + metadata ONLY — never secret values
 */

const jwt = require('jsonwebtoken');

const LOG = '[SecurityEventForwarder]';
const PY_HOST = process.env.PYTHON_BACKEND_HOST || '127.0.0.1';
const PY_PORT = process.env.PYTHON_BACKEND_PORT || 18790;
const ENDPOINT = `http://${PY_HOST}:${PY_PORT}/api/internal/security-event`;
const JWT_SECRET = process.env.JWT_SECRET_KEY || process.env.JWT_SECRET || '';

let _cachedToken = null;
let _cachedExp = 0;  // epoch ms

function _serviceToken() {
  const now = Date.now();
  if (_cachedToken && now < _cachedExp - 30_000) return _cachedToken;
  if (!JWT_SECRET) return null;
  try {
    _cachedToken = jwt.sign(
      { type: 'access', role: 'service', iss: 'ai-employee', tenant_id: 'default', svc: 'secrets' },
      JWT_SECRET,
      { algorithm: 'HS256', expiresIn: '5m', subject: 'svc:secrets' },
    );
    _cachedExp = now + 5 * 60_000;
    return _cachedToken;
  } catch {
    return null;
  }
}

/**
 * Fire-and-forget POST of a security event to the Python sentinel.
 * @param {string} eventType  e.g. 'vault:access', 'vault:access_denied'
 * @param {object} payload    key paths/names + metadata ONLY (no secret values)
 */
function forwardSecurityEvent(eventType, payload = {}) {
  try {
    const headers = { 'Content-Type': 'application/json' };
    const token = _serviceToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const body = JSON.stringify({ event_type: eventType, source: 'node-secrets', payload });

    // Not awaited — must not block the secrets hot path. Errors swallowed.
    fetch(ENDPOINT, {
      method: 'POST',
      headers,
      body,
      signal: AbortSignal.timeout(2000),
    }).catch(() => {});
  } catch (e) {
    try { console.warn(`${LOG} forward failed: ${e.message}`); } catch {}
  }
}

module.exports = { forwardSecurityEvent };

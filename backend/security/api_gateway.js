'use strict';

const PROTECTED_WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const HONEYPOT_PATTERNS = [
  '/.env',
  '/wp-admin',
  '/wp-login.php',
  '/phpmyadmin',
  '/admin',
  '/config',
];

function nowIso() {
  return new Date().toISOString();
}

function createApiGatewayProtector(options = {}) {
  const secretStore = options.secretStore;
  const emitObservabilityEvent = typeof options.emitObservabilityEvent === 'function'
    ? options.emitObservabilityEvent
    : () => {};

  const state = {
    strict_mode: false,
    blocked_requests: 0,
    allowed_requests: 0,
    honeypot_events: [],
    rate_limit_events: 0,
    api_key_protected_requests: 0,
  };
  const ipWindows = new Map();

  function trimWindows(nowTs) {
    for (const [ip, row] of ipWindows.entries()) {
      if (nowTs - row.window_start > 120000) ipWindows.delete(ip);
    }
  }

  function maxRequestsPerMinute() {
    return state.strict_mode ? 60 : 180;
  }

  function recentHoneypot(limit = 20) {
    return state.honeypot_events.slice(0, limit);
  }

  function honeypotHitsInLastMs(ms = 300000) {
    const nowTs = Date.now();
    return state.honeypot_events.filter((item) => (nowTs - Date.parse(item.ts)) <= ms).length;
  }

  function recordSecurityEvent(eventType, payload) {
    emitObservabilityEvent(eventType, payload);
  }

  function maybeHoneypot(req, res) {
    const hitPath = String(req.originalUrl || req.path || '').toLowerCase();
    const matched = HONEYPOT_PATTERNS.find((pattern) => hitPath.includes(pattern));
    if (!matched) return false;
    const event = {
      id: `hp-${Date.now()}-${state.honeypot_events.length + 1}`,
      ts: nowIso(),
      ip: req.ip || req.socket.remoteAddress || 'unknown',
      method: req.method,
      path: req.originalUrl || req.path || '',
      pattern: matched,
      user_agent: req.get('user-agent') || '',
    };
    state.honeypot_events.unshift(event);
    state.honeypot_events = state.honeypot_events.slice(0, 200);
    recordSecurityEvent('honeypot_triggered', { ...event, severity: 'high' });
    res.status(200).json({
      status: 'ok',
      message: 'gateway endpoint reachable',
      request_id: req.gatewayRequestId || '',
    });
    return true;
  }

  function middleware(req, res, next) {
    const nowTs = Date.now();
    trimWindows(nowTs);
    const requestId = `gw-${nowTs}-${(state.allowed_requests + state.blocked_requests + 1)}`;
    req.gatewayRequestId = requestId;
    res.set('X-Gateway-Request-Id', requestId);
    res.set('X-Content-Type-Options', 'nosniff');
    res.set('X-Frame-Options', 'DENY');

    if (maybeHoneypot(req, res)) return;

    const rawPath = String(req.path || '');
    const loweredPath = rawPath.toLowerCase();
    if (loweredPath.includes('..') || loweredPath.includes('%2e%2e')) {
      state.blocked_requests += 1;
      recordSecurityEvent('security_gateway_block', {
        reason: 'path_traversal_pattern',
        path: rawPath,
        request_id: requestId,
      });
      return res.status(400).json({ error: 'invalid_path', request_id: requestId });
    }

    const contentLength = Number(req.get('content-length') || 0);
    if (contentLength > 64 * 1024) {
      state.blocked_requests += 1;
      recordSecurityEvent('security_gateway_block', {
        reason: 'payload_too_large',
        bytes: contentLength,
        request_id: requestId,
      });
      return res.status(413).json({ error: 'payload_too_large', request_id: requestId });
    }

    const ip = req.ip || req.socket.remoteAddress || 'unknown';
    const row = ipWindows.get(ip) || { window_start: nowTs, count: 0 };
    if (nowTs - row.window_start > 60000) {
      row.window_start = nowTs;
      row.count = 0;
    }
    row.count += 1;
    ipWindows.set(ip, row);
    if (row.count > maxRequestsPerMinute()) {
      state.blocked_requests += 1;
      state.rate_limit_events += 1;
      recordSecurityEvent('security_gateway_rate_limited', {
        ip,
        count: row.count,
        limit: maxRequestsPerMinute(),
        request_id: requestId,
      });
      return res.status(429).json({ error: 'rate_limited', request_id: requestId });
    }

    const apiKey = secretStore ? secretStore.get('API_GATEWAY_KEY', { aliases: ['AZTSA_GATEWAY_KEY'] }) : '';
    if (apiKey && PROTECTED_WRITE_METHODS.has(req.method)) {
      state.api_key_protected_requests += 1;
      const provided = String(req.get('x-api-key') || '');
      if (provided !== apiKey) {
        state.blocked_requests += 1;
        recordSecurityEvent('security_gateway_block', {
          reason: 'missing_or_invalid_api_key',
          method: req.method,
          path: rawPath,
          request_id: requestId,
        });
        return res.status(401).json({ error: 'unauthorized', request_id: requestId });
      }
    }

    state.allowed_requests += 1;
    return next();
  }

  function setStrictMode(enabled, reason = '') {
    state.strict_mode = Boolean(enabled);
    recordSecurityEvent('security_gateway_mode', {
      strict_mode: state.strict_mode,
      reason: String(reason || ''),
    });
    return state.strict_mode;
  }

  function status() {
    return {
      strict_mode: state.strict_mode,
      blocked_requests: state.blocked_requests,
      allowed_requests: state.allowed_requests,
      rate_limit_events: state.rate_limit_events,
      honeypot_events: state.honeypot_events.length,
      honeypot_hits_5m: honeypotHitsInLastMs(5 * 60 * 1000),
      api_key_required_for_writes: Boolean(
        secretStore && secretStore.get('API_GATEWAY_KEY', { aliases: ['AZTSA_GATEWAY_KEY'] }),
      ),
      api_key_protected_requests: state.api_key_protected_requests,
      max_requests_per_minute: maxRequestsPerMinute(),
    };
  }

  return {
    middleware,
    status,
    setStrictMode,
    recentHoneypot,
  };
}

module.exports = {
  createApiGatewayProtector,
};

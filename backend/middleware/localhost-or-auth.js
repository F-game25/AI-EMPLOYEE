'use strict';

/**
 * localhost-or-auth — composable auth gate for local-boot endpoints.
 *
 * The desktop shell / supervisor and the first-run webview need to probe runtime
 * identity and report UI boot phases BEFORE any operator token exists. Those callers
 * are always on the loopback interface. This gate lets loopback callers through
 * tokenless, while every non-loopback caller still goes through requireAuth (JWT).
 *
 * Security: the loopback check uses the raw socket address only — never req.ip /
 * X-Forwarded-For (which Express derives with `trust proxy` and a remote client can
 * forge). So an external caller cannot spoof loopback to bypass auth. Deny-by-default
 * for non-loopback is preserved (it falls through to requireAuth).
 */

const LOOPBACK = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);

function isLoopback(req) {
  const raw = (req && (req.socket?.remoteAddress || req.connection?.remoteAddress)) || '';
  return LOOPBACK.has(raw);
}

function makeLocalhostOrAuth(requireAuth) {
  if (typeof requireAuth !== 'function') {
    throw new Error('makeLocalhostOrAuth(requireAuth): requireAuth middleware is required');
  }
  return function localhostOrAuth(req, res, next) {
    if (isLoopback(req)) return next();
    return requireAuth(req, res, next);
  };
}

module.exports = { makeLocalhostOrAuth, isLoopback, LOOPBACK };

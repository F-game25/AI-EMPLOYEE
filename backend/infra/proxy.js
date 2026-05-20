'use strict';

/**
 * Shared HTTP proxy helper for all infra route modules.
 *
 * Each module calls makeProxy(label, timeoutMs?) to get a _proxy function
 * bound to the process-level PYTHON_BASE and the given label for error messages.
 */

const PYTHON_BASE = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 18790}`;

/**
 * @param {string} label   — shown in 502 error messages (e.g. "RPA", "Healing")
 * @param {number} timeout — fetch timeout in ms (default 30 000)
 * @returns {Function}     — async _proxy(req, res, path, body?, method?)
 */
function makeProxy(label, timeout = 30000) {
  return async function _proxy(req, res, path, body = null, method = 'GET') {
    try {
      const opts = {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-Id': req.tenantId || req.headers['x-tenant-id'] || 'system',
        },
      };
      if (body) opts.body = JSON.stringify(body);
      const r = await fetch(`${PYTHON_BASE}${path}`, {
        ...opts,
        signal: AbortSignal.timeout(timeout),
      });
      const data = await r.json();
      res.status(r.status).json(data);
    } catch (e) {
      res.status(502).json({ ok: false, error: `${label} proxy error: ${e.message}` });
    }
  };
}

module.exports = { makeProxy, PYTHON_BASE };

'use strict';
// RBAC middleware for Express — matches Python policy engine (runtime/core/rbac.py).
//
// Permission string format: '<resource>:<action>' or '<resource>:*' (wildcard).
//
// Wildcard resolution:
//   1. Role has '*'           → grants everything (admin).
//   2. Exact string match     → granted.
//   3. Role has '<res>:*'     → grants any '<res>:<action>'.
//   4. Permission is '<res>:*' → granted if role has any '<res>:<x>'.
//
// Usage:
//   const { requirePermission } = require('./middleware/rbac');
//   app.post('/api/settings', requireAuth, requirePermission('settings:write'), handler);

// ── Role → permission grants ──────────────────────────────────────────────────

const ROLE_PERMISSIONS = Object.freeze({
  admin:    new Set(['*']),
  operator: new Set([
    'tasks:*',
    'agents:*',
    'research:read',
    'vault:read',
    'settings:write',
  ]),
  analyst: new Set([
    'tasks:read',
    'research:*',
    'telemetry:read',
    'vault:read',
  ]),
  viewer: new Set([
    'tasks:read',
    'agents:read',
    'telemetry:read',
  ]),
  support: new Set([
    'tasks:read',
    'agents:read',
    'vault:read',
  ]),
});

// ── Core permission check ─────────────────────────────────────────────────────

/**
 * Check whether *role* holds *permission*.
 *
 * @param {string} role       - one of admin | operator | analyst | viewer | support
 * @param {string} permission - e.g. "tasks:read", "vault:write", "admin:*"
 * @returns {boolean}
 */
function hasPermission(role, permission) {
  const grants = ROLE_PERMISSIONS[role] || new Set();

  if (grants.has('*')) return true;                     // super-wildcard
  if (grants.has(permission)) return true;              // exact match

  const resource = permission.split(':')[0];

  if (grants.has(`${resource}:*`)) return true;         // resource wildcard in grants

  // Requested permission is itself a wildcard — allow if role has any grant on resource
  if (permission.endsWith(':*')) {
    for (const g of grants) {
      if (g === '*' || g.startsWith(`${resource}:`)) return true;
    }
  }

  return false;
}

// ── Express middleware factory ────────────────────────────────────────────────

/**
 * Express middleware factory: require *permission* on the calling user.
 *
 * Must be placed *after* requireAuth (or equivalent) so that req.user is set.
 * Defaults to the most-restrictive role ('viewer') when req.user.role is absent.
 *
 * @param {string} permission - permission string to enforce
 * @returns {Function} Express middleware (req, res, next)
 *
 * @example
 *   app.post('/api/settings', requireAuth, requirePermission('settings:write'), handler);
 */
function requirePermission(permission) {
  return (req, res, next) => {
    const role = req.user?.role || 'viewer';
    if (!hasPermission(role, permission)) {
      return res.status(403).json({
        ok: false,
        error: `Role '${role}' lacks permission '${permission}'`,
        code: 'PERMISSION_DENIED',
      });
    }
    next();
  };
}

module.exports = { requirePermission, hasPermission, ROLE_PERMISSIONS };

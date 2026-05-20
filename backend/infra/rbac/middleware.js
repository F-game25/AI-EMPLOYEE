'use strict';

/**
 * RBAC Express middleware.
 *
 * Usage:
 *   const { withRole, withPermission } = require('./infra/rbac/middleware')
 *
 *   // Protect route to manager+
 *   router.get('/sensitive', withRole(ROLES.MANAGER), handler)
 *
 *   // Protect route by permission
 *   router.post('/evolve/deploy', withPermission(PERMISSIONS.EVOLUTION_DEPLOY), handler)
 */

const { ROLES, PERMISSIONS, roleHasPermission } = require('./roles');
const { requirePermission, DECISION } = require('./policy');

/**
 * Middleware: require minimum role level.
 * Role hierarchy: super_admin > org_admin > manager > employee
 */
const ROLE_RANK = {
  [ROLES.SUPER_ADMIN]:      100,
  [ROLES.ORG_ADMIN]:         80,
  [ROLES.MANAGER]:           60,
  [ROLES.EMPLOYEE]:          40,
  [ROLES.AUDITOR]:           30,
  [ROLES.SECURITY_OFFICER]:  30,
};

function withRole(minimumRole) {
  const minRank = ROLE_RANK[minimumRole] || 0;
  return (req, res, next) => {
    const userRole = req.user?.role || ROLES.EMPLOYEE;
    const userRank = ROLE_RANK[userRole] || 0;
    if (userRank >= minRank) return next();
    res.status(403).json({ ok: false, error: `Requires role '${minimumRole}' or higher`, code: 'INSUFFICIENT_ROLE' });
  };
}

/**
 * Inject user role from JWT claims onto req.user.role.
 * Existing JWT middleware writes req.user — this augments it with role if missing.
 */
function injectRole(req, res, next) {
  if (req.user && !req.user.role) {
    // Default role from JWT claim 'role', fall back to employee
    req.user.role = req.user.role || req.user.claims?.role || ROLES.EMPLOYEE;
  }
  next();
}

module.exports = { withRole, withPermission: requirePermission, injectRole, ROLES, PERMISSIONS };

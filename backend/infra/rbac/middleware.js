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

const jwt = require('jsonwebtoken');
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
 * Inject user role from JWT claims onto req.user.
 * Parses the Authorization: Bearer <token> header and populates req.user
 * so that requirePermission() can enforce role-based access control.
 * Routes without a valid JWT get no req.user (role defaults to EMPLOYEE in
 * requirePermission, but tenantMiddleware blocks unauthenticated /api/ requests
 * before this runs for most routes).
 */
function injectRole(req, res, next) {
  if (!req.user) {
    // Try to parse JWT and populate req.user if not already set by another middleware
    const authHeader = req.headers.authorization || '';
    if (authHeader.startsWith('Bearer ')) {
      const secret = process.env.JWT_SECRET_KEY;
      if (secret) {
        try {
          const payload = jwt.verify(authHeader.slice(7), secret, { algorithms: ['HS256'] });
          req.user = {
            id:        payload.sub,
            role:      payload.role || ROLES.EMPLOYEE,
            tenant_id: payload.tenant_id,
            email:     payload.email,
          };
        } catch (_) {
          // Invalid token — req.user stays null; requirePermission will use EMPLOYEE default
        }
      }
    }
  } else if (!req.user.role) {
    req.user.role = req.user.claims?.role || ROLES.EMPLOYEE;
  }
  next();
}

module.exports = { withRole, withPermission: requirePermission, injectRole, ROLES, PERMISSIONS };

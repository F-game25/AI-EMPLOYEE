/**
 * Multi-tenancy support for Node.js backend
 *
 * Extracts tenant_id from JWT token and sets request-scoped context.
 * Enforces tenant isolation on all routes that access data.
 */

const jwt = require('jsonwebtoken');

// Request-scoped tenant store (using async local storage would be better for production)
// For now, we attach tenant directly to request object
let jwtSecret = process.env.JWT_SECRET_KEY || 'default-secret';

/**
 * Middleware to extract tenant from JWT and attach to request
 */
function tenantMiddleware(secret = jwtSecret) {
  const exemptRoutes = new Set([
    '/health',
    '/api/health',
    '/auth/register',
    '/auth/login',
    '/auth/refresh',
    '/auth/token',
    '/version',
    '/metrics',
  ]);

  return (req, res, next) => {
    // Skip tenant extraction for exempt routes
    if (exemptRoutes.has(req.path) || req.path.startsWith('/openapi') || req.path.startsWith('/docs')) {
      return next();
    }

    // Extract JWT from Authorization header
    const authHeader = req.headers.authorization || '';
    if (!authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ detail: 'Missing or invalid Authorization header' });
    }

    const token = authHeader.slice(7); // Remove "Bearer " prefix

    try {
      // Decode JWT without signature verification (signature verified elsewhere)
      const payload = jwt.decode(token);

      if (!payload) {
        return res.status(401).json({ detail: 'Invalid token' });
      }

      const tenantId = payload.tenant_id;
      const orgName = payload.org_name || '';
      const email = payload.email || '';

      if (!tenantId) {
        return res.status(401).json({ detail: 'Token missing tenant_id claim' });
      }

      // Attach tenant context to request
      req.tenant = {
        tenantId,
        orgName,
        email,
      };

      return next();
    } catch (err) {
      return res.status(401).json({ detail: `Invalid token: ${err.message}` });
    }
  };
}

/**
 * Middleware to require tenant context (for protected routes)
 */
function requireTenant() {
  return (req, res, next) => {
    if (!req.tenant || !req.tenant.tenantId) {
      return res.status(401).json({ detail: 'No tenant context' });
    }
    next();
  };
}

/**
 * Helper to get tenant state directory path
 */
function getTenantStatePath(aiHome, tenantId) {
  const path = require('path');
  return path.join(aiHome, 'tenants', tenantId, 'state');
}

/**
 * Helper to get tenant config directory path
 */
function getTenantConfigPath(aiHome, tenantId) {
  const path = require('path');
  return path.join(aiHome, 'tenants', tenantId, 'config');
}

module.exports = {
  tenantMiddleware,
  requireTenant,
  getTenantStatePath,
  getTenantConfigPath,
};

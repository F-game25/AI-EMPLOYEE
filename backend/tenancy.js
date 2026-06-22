/**
 * Multi-tenancy support for Node.js backend
 *
 * Extracts tenant_id from JWT token and sets request-scoped context.
 * Enforces tenant isolation on all routes that access data.
 */

const jwt = require('jsonwebtoken');

// Request-scoped tenant store (using async local storage would be better for production)
// For now, we attach tenant directly to request object
const jwtSecret = process.env.JWT_SECRET_KEY;
if (!jwtSecret) {
  throw new Error('[tenancy] JWT_SECRET_KEY env var is required — refusing to start with default secret');
}

/**
 * Middleware to extract tenant from JWT and attach to request
 */
function tenantMiddleware(secret = jwtSecret) {
  const exemptRoutes = new Set([
    '/',
    '/health',
    '/health/full',
    '/api/health',
    '/api/runtime/identity',
    '/api/auth/token',
    '/api/auth/service-token',
    '/auth/register',
    '/auth/login',
    '/auth/refresh',
    '/auth/token',
    '/version',
    '/metrics',
    '/api/identity/public',
    '/api/onboarding/palettes',
    '/api/identity/finalize',
    '/api/bootstrap/status',
    '/api/bootstrap/start',
    '/api/auth/auto-token',
    '/api/neural-brain/memory/status',
    '/api/neural-brain/memory/list',
    '/api/neural-brain/graph/status',
    '/api/neural-brain/graph/snapshot',
    '/api/neural-brain/threads',
    '/api/neural-brain/forge/evolution/status',
    '/api/readiness',
    '/api/readiness/deep',
  ]);

  // Static asset extensions (frontend bundle) — never require auth
  const staticAssetRe = /\.(js|css|woff2?|ttf|eot|svg|png|jpg|jpeg|gif|ico|map|webp|html)$/i;

  return (req, res, next) => {
    // Skip tenant extraction for exempt routes, openapi/docs, and static assets
    if (
      exemptRoutes.has(req.path) ||
      req.path.startsWith('/openapi') ||
      req.path.startsWith('/docs') ||
      req.path.startsWith('/assets/') ||
      req.path.startsWith('/workspace/') ||
      req.path.startsWith('/api/demos/') ||   // public demo sites (multi-page folder + legacy files), shared with customers
      staticAssetRe.test(req.path)
    ) {
      return next();
    }

    // Allow GET on root and any non-API path (frontend SPA routes)
    if (req.method === 'GET' && !req.path.startsWith('/api/')) {
      return next();
    }

    // Extract JWT from Authorization header
    const authHeader = req.headers.authorization || '';
    if (!authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ detail: 'Missing or invalid Authorization header' });
    }

    const token = authHeader.slice(7); // Remove "Bearer " prefix

    try {
      const payload = jwt.verify(token, secret);

      const tenantId = payload.tenant_id;
      const orgName = payload.org_name || '';
      const email = payload.email || '';

      if (!tenantId) {
        return res.status(401).json({ detail: 'Token missing tenant_id claim' });
      }

      // Attach tenant context to request
      req.tenant = {
        id: tenantId,
        tenantId,
        tenant_id: tenantId,
        orgName,
        org_name: orgName,
        email,
      };
      req.tenantId = tenantId;

      return next();
    } catch (err) {
      return res.status(401).json({ detail: 'Invalid or expired token' });
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

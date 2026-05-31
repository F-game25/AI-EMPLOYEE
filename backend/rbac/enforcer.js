'use strict';

/**
 * RBAC Enforcer — Fine-grained resource-level access control
 *
 * Features:
 *  - Resource-scoped permissions: agents, workflows, memory, economy, security, admin
 *  - Actions: read, write, delete per resource
 *  - User-level + resource-level checks
 *  - Audit logging of permission decisions
 */

const LOG = '[RBACEnforcer]';

// Resources in the system
const RESOURCES = Object.freeze({
  AGENTS: 'agents',
  WORKFLOWS: 'workflows',
  MEMORY: 'memory',
  ECONOMY: 'economy',
  SECURITY: 'security',
  ADMIN: 'admin',
});

// Actions on resources
const ACTIONS = Object.freeze({
  READ: 'read',
  WRITE: 'write',
  DELETE: 'delete',
  EXECUTE: 'execute',
  CONFIGURE: 'configure',
});

/**
 * Define which roles can perform which actions on which resources
 */
const RBAC_MATRIX = {
  super_admin: {
    [RESOURCES.AGENTS]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.DELETE, ACTIONS.EXECUTE, ACTIONS.CONFIGURE],
    [RESOURCES.WORKFLOWS]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.DELETE, ACTIONS.EXECUTE, ACTIONS.CONFIGURE],
    [RESOURCES.MEMORY]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.DELETE],
    [RESOURCES.ECONOMY]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.DELETE],
    [RESOURCES.SECURITY]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.DELETE, ACTIONS.CONFIGURE],
    [RESOURCES.ADMIN]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.DELETE, ACTIONS.CONFIGURE],
  },
  org_admin: {
    [RESOURCES.AGENTS]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.EXECUTE, ACTIONS.CONFIGURE],
    [RESOURCES.WORKFLOWS]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.EXECUTE, ACTIONS.CONFIGURE],
    [RESOURCES.MEMORY]: [ACTIONS.READ, ACTIONS.WRITE],
    [RESOURCES.ECONOMY]: [ACTIONS.READ, ACTIONS.WRITE],
    [RESOURCES.SECURITY]: [ACTIONS.READ, ACTIONS.CONFIGURE],
    [RESOURCES.ADMIN]: [ACTIONS.READ, ACTIONS.CONFIGURE],
  },
  manager: {
    [RESOURCES.AGENTS]: [ACTIONS.READ, ACTIONS.EXECUTE],
    [RESOURCES.WORKFLOWS]: [ACTIONS.READ, ACTIONS.EXECUTE],
    [RESOURCES.MEMORY]: [ACTIONS.READ],
    [RESOURCES.ECONOMY]: [ACTIONS.READ],
    [RESOURCES.SECURITY]: [ACTIONS.READ],
  },
  employee: {
    [RESOURCES.AGENTS]: [ACTIONS.READ],
    [RESOURCES.WORKFLOWS]: [ACTIONS.READ],
    [RESOURCES.MEMORY]: [ACTIONS.READ],
    [RESOURCES.ECONOMY]: [ACTIONS.READ],
  },
  auditor: {
    [RESOURCES.AGENTS]: [ACTIONS.READ],
    [RESOURCES.WORKFLOWS]: [ACTIONS.READ],
    [RESOURCES.MEMORY]: [ACTIONS.READ],
    [RESOURCES.ECONOMY]: [ACTIONS.READ],
    [RESOURCES.SECURITY]: [ACTIONS.READ],
  },
  security_officer: {
    [RESOURCES.AGENTS]: [ACTIONS.READ],
    [RESOURCES.WORKFLOWS]: [ACTIONS.READ],
    [RESOURCES.SECURITY]: [ACTIONS.READ, ACTIONS.WRITE, ACTIONS.CONFIGURE],
    [RESOURCES.ADMIN]: [ACTIONS.READ],
  },
};

class RBACEnforcer {
  constructor(options = {}) {
    this.auditLogger = options.auditLogger || (() => {}); // Audit callback
  }

  /**
   * Check if user can perform action on resource
   * Returns: { allowed: bool, reason: string }
   */
  canUserPerformAction(userRole, action, resource) {
    const roleActions = RBAC_MATRIX[userRole] || {};
    const resourceActions = roleActions[resource] || [];
    const allowed = resourceActions.includes(action);

    return {
      allowed,
      reason: allowed
        ? `Role '${userRole}' can ${action} ${resource}`
        : `Role '${userRole}' cannot ${action} ${resource}`,
    };
  }

  /**
   * Check if user can access specific resource instance
   * This allows for instance-level checks (e.g., can user modify agent X?)
   */
  canUserAccessResource(userRole, action, resource, resourceId, ownerTenantId, userTenantId) {
    // First: role-based check
    const roleCheck = this.canUserPerformAction(userRole, action, resource);
    if (!roleCheck.allowed) {
      return { allowed: false, reason: roleCheck.reason };
    }

    // Second: tenant isolation check
    if (ownerTenantId !== userTenantId) {
      return {
        allowed: false,
        reason: `Cannot access resource from different tenant`,
      };
    }

    return { allowed: true, reason: 'Access granted' };
  }

  /**
   * Enforce permission — throw if denied
   */
  enforce(userRole, action, resource, context = {}) {
    const check = this.canUserPerformAction(userRole, action, resource);
    if (!check.allowed) {
      const err = new Error(check.reason);
      err.code = 'PERMISSION_DENIED';
      err.resource = resource;
      err.action = action;
      this.auditLogger('permission_denied', { userRole, action, resource, context });
      throw err;
    }
    this.auditLogger('permission_granted', { userRole, action, resource, context });
    return check;
  }

  /**
   * Get all permissions for a role
   */
  getRolePermissions(role) {
    return RBAC_MATRIX[role] || {};
  }

  /**
   * Get all available resources
   */
  getAvailableResources() {
    return Object.values(RESOURCES);
  }

  /**
   * Get all available actions
   */
  getAvailableActions() {
    return Object.values(ACTIONS);
  }
}

/**
 * Express middleware factory
 * Usage: app.use(requireAction(ACTIONS.READ, RESOURCES.AGENTS))
 */
function requireAction(action, resource) {
  const enforcer = new RBACEnforcer();
  return (req, res, next) => {
    const userRole = req.user?.role || 'employee';
    try {
      enforcer.enforce(userRole, action, resource, {
        user_id: req.user?.id,
        path: req.path,
      });
      next();
    } catch (err) {
      res.status(403).json({
        ok: false,
        error: err.message,
        code: 'PERMISSION_DENIED',
      });
    }
  };
}

/**
 * Async middleware to check tenant-scoped resource access
 * Usage: app.use(requireResourceAccess(ACTIONS.WRITE, RESOURCES.AGENTS, resourceIdFromParams))
 */
function requireResourceAccess(action, resource, resourceIdFn = null) {
  const enforcer = new RBACEnforcer();
  return (req, res, next) => {
    const userRole = req.user?.role || 'employee';
    const resourceId = resourceIdFn ? resourceIdFn(req) : req.params.id;
    const ownerTenantId = req.resourceOwnerTenantId || req.tenant?.tenantId;
    const userTenantId = req.tenant?.tenantId;

    try {
      enforcer.enforce(userRole, action, resource, {
        resource_id: resourceId,
        user_id: req.user?.id,
        path: req.path,
      });

      // Tenant isolation check if we have owner info
      if (ownerTenantId && userTenantId && ownerTenantId !== userTenantId) {
        throw new Error('Cannot access resource from different tenant');
      }

      next();
    } catch (err) {
      res.status(403).json({
        ok: false,
        error: err.message,
        code: 'PERMISSION_DENIED',
      });
    }
  };
}

module.exports = {
  RBACEnforcer,
  requireAction,
  requireResourceAccess,
  RESOURCES,
  ACTIONS,
  RBAC_MATRIX,
};

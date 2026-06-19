'use strict';

/**
 * Role-Based Access Control — role definitions and permission hierarchy.
 *
 * Role hierarchy (most → least privileged):
 *   SUPER_ADMIN → ORG_ADMIN → MANAGER → EMPLOYEE → AUDITOR | SECURITY_OFFICER
 *
 * Permission model: { resource, action, conditions? }
 *   Resource examples: agents, tasks, workflows, secrets, users, evolution, hitl
 *   Action examples:   read, write, execute, approve, delete, configure
 *
 * Conditions are evaluated at enforcement time (see policy.js).
 */

const ROLES = Object.freeze({
  SUPER_ADMIN:       'super_admin',
  ORG_ADMIN:         'org_admin',
  MANAGER:           'manager',
  OPERATOR:          'operator',
  EMPLOYEE:          'employee',
  AUDITOR:           'auditor',
  SECURITY_OFFICER:  'security_officer',
});

// ── Permission definitions ────────────────────────────────────────────────────
// Format: '<resource>:<action>' or '<resource>:*' for all actions on resource

const PERMISSIONS = Object.freeze({
  // Agents
  AGENTS_READ:        'agents:read',
  AGENTS_WRITE:       'agents:write',
  AGENTS_EXECUTE:     'agents:execute',
  AGENTS_STOP:        'agents:stop',
  AGENTS_CONFIGURE:   'agents:configure',

  // Tasks
  TASKS_READ:         'tasks:read',
  TASKS_SUBMIT:       'tasks:submit',
  TASKS_CANCEL:       'tasks:cancel',
  TASKS_ALL:          'tasks:*',

  // Workflows
  WORKFLOWS_READ:     'workflows:read',
  WORKFLOWS_START:    'workflows:start',
  WORKFLOWS_SIGNAL:   'workflows:signal',
  WORKFLOWS_CANCEL:   'workflows:cancel',

  // HITL
  HITL_READ:          'hitl:read',
  HITL_APPROVE:       'hitl:approve',
  HITL_REJECT:        'hitl:reject',

  // Secrets
  SECRETS_READ:       'secrets:read',
  SECRETS_WRITE:      'secrets:write',
  SECRETS_ROTATE:     'secrets:rotate',
  SECRETS_DELETE:     'secrets:delete',

  // Evolution
  EVOLUTION_READ:     'evolution:read',
  EVOLUTION_APPROVE:  'evolution:approve',
  EVOLUTION_DEPLOY:   'evolution:deploy',
  EVOLUTION_ROLLBACK: 'evolution:rollback',

  // System
  SYSTEM_READ:        'system:read',
  SYSTEM_CONFIGURE:   'system:configure',
  SYSTEM_HALT:        'system:halt',

  // Users & tenants
  USERS_READ:         'users:read',
  USERS_WRITE:        'users:write',
  USERS_DELETE:       'users:delete',
  TENANTS_READ:       'tenants:read',
  TENANTS_WRITE:      'tenants:write',

  // Audit
  AUDIT_READ:         'audit:read',
  AUDIT_EXPORT:       'audit:export',

  // Sandbox
  SANDBOX_EXECUTE:    'sandbox:execute',
  SANDBOX_CONFIGURE:  'sandbox:configure',

  // Finance / limits
  FINANCE_READ:       'finance:read',
  FINANCE_APPROVE:    'finance:approve',    // approve high-cost operations
});

// ── Role → permission grants ──────────────────────────────────────────────────

const ROLE_PERMISSIONS = {
  [ROLES.SUPER_ADMIN]: Object.values(PERMISSIONS),  // all

  [ROLES.ORG_ADMIN]: [
    PERMISSIONS.AGENTS_READ, PERMISSIONS.AGENTS_WRITE, PERMISSIONS.AGENTS_EXECUTE,
    PERMISSIONS.AGENTS_STOP, PERMISSIONS.AGENTS_CONFIGURE,
    PERMISSIONS.TASKS_ALL,
    PERMISSIONS.WORKFLOWS_READ, PERMISSIONS.WORKFLOWS_START, PERMISSIONS.WORKFLOWS_SIGNAL, PERMISSIONS.WORKFLOWS_CANCEL,
    PERMISSIONS.HITL_READ, PERMISSIONS.HITL_APPROVE, PERMISSIONS.HITL_REJECT,
    PERMISSIONS.SECRETS_READ, PERMISSIONS.SECRETS_WRITE, PERMISSIONS.SECRETS_ROTATE,
    PERMISSIONS.EVOLUTION_READ, PERMISSIONS.EVOLUTION_APPROVE,
    PERMISSIONS.SYSTEM_READ, PERMISSIONS.SYSTEM_CONFIGURE,
    PERMISSIONS.USERS_READ, PERMISSIONS.USERS_WRITE,
    PERMISSIONS.TENANTS_READ,
    PERMISSIONS.AUDIT_READ, PERMISSIONS.AUDIT_EXPORT,
    PERMISSIONS.SANDBOX_EXECUTE,
    PERMISSIONS.FINANCE_READ, PERMISSIONS.FINANCE_APPROVE,
  ],

  [ROLES.MANAGER]: [
    PERMISSIONS.AGENTS_READ, PERMISSIONS.AGENTS_EXECUTE, PERMISSIONS.AGENTS_STOP,
    PERMISSIONS.TASKS_READ, PERMISSIONS.TASKS_SUBMIT, PERMISSIONS.TASKS_CANCEL,
    PERMISSIONS.WORKFLOWS_READ, PERMISSIONS.WORKFLOWS_START, PERMISSIONS.WORKFLOWS_SIGNAL,
    PERMISSIONS.HITL_READ, PERMISSIONS.HITL_APPROVE, PERMISSIONS.HITL_REJECT,
    PERMISSIONS.SYSTEM_READ,
    PERMISSIONS.USERS_READ,
    PERMISSIONS.AUDIT_READ,
    PERMISSIONS.FINANCE_READ,
    PERMISSIONS.EVOLUTION_READ,
  ],

  // OPERATOR — the default day-to-day runner (the role the local auto-token
  // issues). Can run agents/tasks/workflows + RPA/browser sandbox, approve HITL,
  // but not manage users/secrets/tenants. Aligns Node RBAC with the role the
  // Python auth layer actually issues (was previously undefined → zero perms).
  [ROLES.OPERATOR]: [
    PERMISSIONS.AGENTS_READ, PERMISSIONS.AGENTS_EXECUTE, PERMISSIONS.AGENTS_STOP,
    PERMISSIONS.TASKS_READ, PERMISSIONS.TASKS_SUBMIT, PERMISSIONS.TASKS_CANCEL,
    PERMISSIONS.WORKFLOWS_READ, PERMISSIONS.WORKFLOWS_START, PERMISSIONS.WORKFLOWS_SIGNAL,
    PERMISSIONS.HITL_READ, PERMISSIONS.HITL_APPROVE, PERMISSIONS.HITL_REJECT,
    PERMISSIONS.SANDBOX_EXECUTE,
    PERMISSIONS.SYSTEM_READ,
    PERMISSIONS.AUDIT_READ,
    PERMISSIONS.FINANCE_READ,
    PERMISSIONS.EVOLUTION_READ,
  ],

  [ROLES.EMPLOYEE]: [
    PERMISSIONS.AGENTS_READ, PERMISSIONS.AGENTS_EXECUTE,
    PERMISSIONS.TASKS_READ, PERMISSIONS.TASKS_SUBMIT,
    PERMISSIONS.WORKFLOWS_READ, PERMISSIONS.WORKFLOWS_START,
    PERMISSIONS.HITL_READ,
    PERMISSIONS.SYSTEM_READ,
    PERMISSIONS.FINANCE_READ,
  ],

  [ROLES.AUDITOR]: [
    PERMISSIONS.AGENTS_READ,
    PERMISSIONS.TASKS_READ,
    PERMISSIONS.WORKFLOWS_READ,
    PERMISSIONS.HITL_READ,
    PERMISSIONS.SYSTEM_READ,
    PERMISSIONS.USERS_READ,
    PERMISSIONS.AUDIT_READ, PERMISSIONS.AUDIT_EXPORT,
    PERMISSIONS.EVOLUTION_READ,
    PERMISSIONS.FINANCE_READ,
  ],

  [ROLES.SECURITY_OFFICER]: [
    PERMISSIONS.AGENTS_READ, PERMISSIONS.AGENTS_STOP,
    PERMISSIONS.SECRETS_READ, PERMISSIONS.SECRETS_ROTATE, PERMISSIONS.SECRETS_DELETE,
    PERMISSIONS.SYSTEM_READ,
    PERMISSIONS.AUDIT_READ, PERMISSIONS.AUDIT_EXPORT,
    PERMISSIONS.USERS_READ,
    PERMISSIONS.EVOLUTION_READ,
    PERMISSIONS.SANDBOX_CONFIGURE,
  ],
};

/**
 * Get all permissions granted to a role (flattened set).
 */
function getRolePermissions(role) {
  return new Set(ROLE_PERMISSIONS[role] || []);
}

/**
 * Check if role has permission (supports wildcard e.g. tasks:*)
 */
function roleHasPermission(role, permission) {
  // Fail closed on a malformed/undefined permission rather than crashing the
  // request pipeline (a missing PERMISSIONS.* constant must deny, not 500).
  if (typeof permission !== 'string' || !permission) return false;
  const grants = getRolePermissions(role);
  if (grants.has(permission)) return true;
  // Wildcard check: if role has 'tasks:*', all 'tasks:X' granted
  const [resource] = permission.split(':');
  return grants.has(`${resource}:*`);
}

module.exports = { ROLES, PERMISSIONS, ROLE_PERMISSIONS, getRolePermissions, roleHasPermission };

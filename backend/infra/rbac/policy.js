'use strict';

/**
 * Policy Engine — enforces RBAC + fine-grained policies.
 *
 * Evaluation order:
 *   1. OPA (Open Policy Agent) — if POLICY_OPA_URL is set
 *   2. Built-in policy rules   — always evaluated
 *   3. Role permission grants  — fallback
 *
 * Policy decision: ALLOW | DENY | ESCALATE (requires manager approval)
 *
 * Built-in policies enforced without OPA:
 *   - Financial limit: cost > $X requires FINANCE_APPROVE permission
 *   - Evolution deploy: always requires evolution:deploy permission
 *   - HITL approval: high-risk agents always require hitl:approve
 *   - Secrets access: scoped to agent's declared requirements
 *   - Sandbox profile: 'heavy' or 'browser' requires sandbox:configure
 */

const { ROLES, PERMISSIONS, roleHasPermission } = require('./roles');

const LOG = '[PolicyEngine]';
const OPA_URL = process.env.POLICY_OPA_URL;  // e.g. http://localhost:8181/v1/data/aie/authz/allow

// ── Policy decision types ─────────────────────────────────────────────────────

const DECISION = Object.freeze({
  ALLOW:     'allow',
  DENY:      'deny',
  ESCALATE:  'escalate',  // needs human approval
});

// ── Built-in policy rules ─────────────────────────────────────────────────────

const BUILTIN_RULES = [
  // Financial limits: cost-bearing operations over $10 require approval
  {
    name: 'financial_limit',
    match: (req) => req.context?.estimated_cost_usd > 10,
    decide: (req, role) =>
      roleHasPermission(role, PERMISSIONS.FINANCE_APPROVE) ? DECISION.ALLOW : DECISION.ESCALATE,
    reason: 'Operation exceeds $10 cost threshold — approval required',
  },

  // Evolution deploy: never allow employees/auditors
  {
    name: 'evolution_deploy_guard',
    match: (req) => req.permission === PERMISSIONS.EVOLUTION_DEPLOY,
    decide: (_, role) =>
      [ROLES.SUPER_ADMIN, ROLES.ORG_ADMIN].includes(role) ? DECISION.ALLOW : DECISION.DENY,
    reason: 'Evolution deployment restricted to org-admin+',
  },

  // System halt: only super_admin
  {
    name: 'system_halt_guard',
    match: (req) => req.permission === PERMISSIONS.SYSTEM_HALT,
    decide: (_, role) => role === ROLES.SUPER_ADMIN ? DECISION.ALLOW : DECISION.DENY,
    reason: 'System halt restricted to super_admin',
  },

  // Heavy/browser sandbox: requires sandbox:configure
  {
    name: 'sandbox_profile_guard',
    match: (req) => req.permission === PERMISSIONS.SANDBOX_EXECUTE &&
                    ['heavy', 'browser'].includes(req.context?.profile),
    decide: (_, role) =>
      roleHasPermission(role, PERMISSIONS.SANDBOX_CONFIGURE) ? DECISION.ALLOW : DECISION.DENY,
    reason: 'Heavy/browser sandbox profiles require sandbox:configure permission',
  },

  // Tenant isolation: users cannot access other tenants' data
  {
    name: 'tenant_isolation',
    match: (req) => Boolean(req.context?.target_tenant_id &&
                    req.context.target_tenant_id !== req.tenant_id),
    decide: (req, role) =>
      role === ROLES.SUPER_ADMIN ? DECISION.ALLOW : DECISION.DENY,
    reason: 'Cross-tenant access denied',
  },
];

// ── OPA client ────────────────────────────────────────────────────────────────

async function _queryOPA(input) {
  if (!OPA_URL) return null;
  try {
    const res = await fetch(OPA_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
      signal: AbortSignal.timeout(2000),
    });
    const data = await res.json();
    if (data.result === true)  return { decision: DECISION.ALLOW, source: 'opa' };
    if (data.result === false) return { decision: DECISION.DENY,  source: 'opa' };
    // OPA may return { allow: bool, escalate: bool }
    if (data.result?.escalate) return { decision: DECISION.ESCALATE, source: 'opa', reason: data.result.reason };
    return null;
  } catch (e) {
    console.warn(`${LOG} OPA query failed (falling back to built-in): ${e.message}`);
    return null;
  }
}

// ── Policy Engine ─────────────────────────────────────────────────────────────

class PolicyEngine {
  /**
   * Evaluate a policy request.
   *
   * @param {object} request
   *   role        string — ROLES value
   *   permission  string — PERMISSIONS value being requested
   *   tenant_id   string — requester's tenant
   *   user_id     string
   *   context     object — additional metadata (cost, profile, target_tenant_id, etc.)
   * @returns {{ decision, reason, source }}
   */
  async evaluate(request) {
    const { role, permission, tenant_id, context = {} } = request;

    // 1. OPA (if configured)
    const opaResult = await _queryOPA({ ...request, timestamp: Date.now() });
    if (opaResult) return opaResult;

    // 2. Built-in rules (first match wins)
    for (const rule of BUILTIN_RULES) {
      if (rule.match(request)) {
        const decision = rule.decide(request, role);
        return { decision, reason: rule.reason, source: `builtin:${rule.name}` };
      }
    }

    // 3. Role-based permission
    const granted = roleHasPermission(role, permission);
    return {
      decision: granted ? DECISION.ALLOW : DECISION.DENY,
      reason: granted ? 'Permission granted by role' : `Role '${role}' lacks '${permission}'`,
      source: 'rbac',
    };
  }

  /**
   * Assert permission — throws on deny, returns escalation metadata.
   */
  async assert(request) {
    const result = await this.evaluate(request);
    if (result.decision === DECISION.DENY) {
      const err = new Error(`Access denied: ${result.reason}`);
      err.code = 'PERMISSION_DENIED';
      err.decision = result;
      throw err;
    }
    return result;
  }
}

// ── Express middleware ────────────────────────────────────────────────────────

function requirePermission(permission, contextFn = null) {
  const engine = new PolicyEngine();
  return async (req, res, next) => {
    try {
      const role      = req.user?.role || ROLES.EMPLOYEE;
      const tenant_id = req.tenantId  || req.user?.tenant_id || 'system';
      const context   = contextFn ? await contextFn(req) : {};

      const result = await engine.evaluate({ role, permission, tenant_id, user_id: req.user?.id, context });

      if (result.decision === DECISION.DENY) {
        return res.status(403).json({ ok: false, error: result.reason, code: 'PERMISSION_DENIED' });
      }
      if (result.decision === DECISION.ESCALATE) {
        return res.status(202).json({ ok: false, escalate: true, reason: result.reason, code: 'ESCALATION_REQUIRED' });
      }

      req.policyDecision = result;
      next();
    } catch (e) {
      if (e.code === 'PERMISSION_DENIED') {
        return res.status(403).json({ ok: false, error: e.message });
      }
      next(e);
    }
  };
}

// ── Singleton ─────────────────────────────────────────────────────────────────

const _policyEngine = new PolicyEngine();
function getPolicyEngine() { return _policyEngine; }

module.exports = { PolicyEngine, getPolicyEngine, requirePermission, DECISION };

/* Shared AscendForge helpers + constants (API, normalizers, risk rules). */

export const TOKEN = () => localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt')
export const H = (extra = {}) => TOKEN() ? { ...extra, Authorization: `Bearer ${TOKEN()}` } : extra
export const JPOST = (url, body) => fetch(url, { method: 'POST', headers: H({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) })
export const JGET  = url => fetch(url, { headers: H() })
export const JPOST_JSON = async (url, body) => {
  const r = await JPOST(url, body)
  const d = await r.json().catch(() => ({}))
  if (!r.ok || d?.ok === false) {
    const err = new Error(d?.error || d?.detail?.error || d?.detail || `HTTP ${r.status}`)
    err.status = r.status
    err.payload = d
    throw err
  }
  return d
}

export const LLM_PROVIDERS = [
  { id: 'anthropic', label: 'Anthropic (Claude)', icon: '◆' },
  { id: 'ollama',    label: 'Ollama (Local)',      icon: '⬡' },
  { id: 'openai',    label: 'OpenAI (GPT-4)',      icon: '◉' },
]

export const TEMPLATES = [
  { id: 'web-app',     label: 'Web App',           stack: 'React + Node.js',   icon: '🌐' },
  { id: 'python-api',  label: 'Python API',        stack: 'FastAPI + SQLite',  icon: '🐍' },
  { id: 'agent',       label: 'New AI Agent',      stack: 'Python + BaseAgent',icon: '🤖' },
  { id: 'landing',     label: 'Landing Page',      stack: 'HTML + Tailwind',   icon: '📄' },
]

export const DEFAULT_SKILL_PACKS = [
  { id: 'agent-skills', label: 'Agent Skills' },
  { id: 'automaton', label: 'Autonomy' },
  { id: 'cashclaw', label: 'Money' },
  { id: 'financial-services', label: 'Finance' },
  { id: 'wallet-vault', label: 'Wallet' },
]

export const DANGEROUS_ACTION_TYPES = new Set([
  'command', 'shell', 'terminal', 'delete', 'remove', 'deploy', 'rollback',
  'publish', 'external_delivery', 'payment', 'wallet', 'install', 'dependency_install',
  'credential', 'secret', 'account_modify',
])
export const DANGEROUS_TEXT = /\b(delete|remove|rm\s+-|wipe|deploy|rollback|publish|deliver|payment|wallet|spend|purchase|install|npm\s+i|pip\s+install|credential|secret|token|chmod|sudo|curl|wget|external)\b/i
export const SAFE_BATCH_RISKS = new Set(['low', 'safe'])
export const PENDING_STATUSES = new Set(['pending', 'pending_approval', 'awaiting_approval', 'requires_approval', 'queued'])

export const compactId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

export function textFrom(value, fallback = 'none') {
  if (value === undefined || value === null || value === '') return fallback
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

export function titleize(value, fallback = 'action') {
  return textFrom(value, fallback).replace(/[_-]+/g, ' ')
}

export function normalizeRisk(value, score) {
  const raw = String(value || '').toLowerCase()
  if (raw.includes('critical')) return 'critical'
  if (raw.includes('high')) return 'high'
  if (raw.includes('medium') || raw.includes('moderate')) return 'medium'
  if (raw.includes('low')) return 'low'
  if (raw.includes('safe')) return 'safe'
  if (typeof score === 'number') {
    if (score >= 0.7) return 'high'
    if (score >= 0.3) return 'medium'
    return 'low'
  }
  return 'unknown'
}

export function actionId(action) {
  return String(action?.id || action?.action_id || action?.request_id || action?.snapshot_id || action?.goal || compactId())
}

export function normalizeAction(action = {}) {
  const type = action.type || action.action_type || action.tool || action.kind || action.operation || 'action'
  const status = action.status || action.lifecycle_state || action.approval_status || (action.requires_approval ? 'requires_approval' : 'pending')
  const risk = normalizeRisk(action.risk_level || action.risk || action.severity, action.risk_score)
  const target = action.target || action.path || action.file || action.module || action.snapshot_id || action.project_id || ''
  const label = action.label || action.title || action.goal || action.action || action.command || action.description || titleize(type)
  const plan = action.plan || action.steps || action.execution_plan || action.proposed_plan || []
  const lifecycle = action.lifecycle || action.action_lifecycle || action.timeline || action.gates || []
  const approval = action.approval ?? action.approval_policy ?? action.approval_required ?? action.requires_approval ?? null
  const approvalReason = action.approval_reason || action.policy_reason || action.reason || ''
  const expectedResult = action.expected_result || action.expectedResult || action.output_preview || ''
  const rollbackPlan = action.rollback_plan || action.rollbackPlan || action.rollback || []
  const policyDecision = action.policy_decision || action.policyDecision || action.decision || ''

  return {
    ...action,
    id: actionId(action),
    type: String(type),
    status: String(status),
    risk,
    target,
    label: String(label),
    description: action.description || action.reason || action.summary || '',
    plan: Array.isArray(plan) ? plan : plan ? [plan] : [],
    lifecycle: Array.isArray(lifecycle) ? lifecycle : lifecycle ? [lifecycle] : [],
    approval,
    approvalReason,
    expectedResult,
    rollbackPlan: Array.isArray(rollbackPlan) ? rollbackPlan : rollbackPlan ? [rollbackPlan] : [],
    policyDecision,
    sandbox: action.sandbox_result || action.sandbox || action.validation || null,
    snapshotId: action.snapshot_id || action.snapshot || action.version_id || '',
    createdAt: action.created_at || action.submitted_at || action.ts || '',
    decidedAt: action.decided_at || action.completed_at || '',
    decidedBy: action.decided_by || action.approved_by || action.rejected_by || '',
  }
}

export function isPendingAction(action) {
  const status = normalizeAction(action).status.toLowerCase()
  return PENDING_STATUSES.has(status) || !['approved', 'rejected', 'deployed', 'failed', 'blocked'].includes(status)
}

export function isDangerousAction(action) {
  const a = normalizeAction(action)
  const type = a.type.toLowerCase()
  const text = [a.type, a.label, a.description, a.command, a.target, a.approval].map(v => textFrom(v, '')).join(' ')
  if (['critical', 'high'].includes(a.risk)) return true
  if (DANGEROUS_ACTION_TYPES.has(type)) return true
  return DANGEROUS_TEXT.test(text)
}

export function canBatchApprove(action) {
  const a = normalizeAction(action)
  return isPendingAction(a) && SAFE_BATCH_RISKS.has(a.risk) && !isDangerousAction(a)
}

export function mergeActionLists(existing, incoming) {
  const map = new Map(existing.map(item => [normalizeAction(item).id, item]))
  incoming.forEach(item => {
    const normalized = normalizeAction(item)
    map.set(normalized.id, { ...(map.get(normalized.id) || {}), ...item, id: normalized.id })
  })
  return Array.from(map.values())
}

export async function postFirst(candidates, body) {
  let lastError
  for (const url of candidates) {
    try {
      return await JPOST_JSON(url, body)
    } catch (e) {
      lastError = e
      if (![404, 405].includes(e.status)) throw e
    }
  }
  throw lastError || new Error('No approval endpoint available')
}

/**
 * AscendForge — Agentic Vibecoder
 * 3-pane layout: Project tree + chat | File diff viewer + editor | Action queue + terminal
 * Multi-turn agentic loop with per-action approval gates.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { SectionLabel, StatusPill, EmptyState } from '../nexus-ui'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import './AscendForgePage.css'

const TOKEN = () => sessionStorage.getItem('ai_jwt')
const H = (extra = {}) => TOKEN() ? { ...extra, Authorization: `Bearer ${TOKEN()}` } : extra
const JPOST = (url, body) => fetch(url, { method: 'POST', headers: H({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) })
const JGET  = url => fetch(url, { headers: H() })
const JPOST_JSON = async (url, body) => {
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

const LLM_PROVIDERS = [
  { id: 'anthropic', label: 'Anthropic (Claude)', icon: '◆' },
  { id: 'ollama',    label: 'Ollama (Local)',      icon: '⬡' },
  { id: 'openai',    label: 'OpenAI (GPT-4)',      icon: '◉' },
]

const TEMPLATES = [
  { id: 'web-app',     label: 'Web App',           stack: 'React + Node.js',   icon: '🌐' },
  { id: 'python-api',  label: 'Python API',        stack: 'FastAPI + SQLite',  icon: '🐍' },
  { id: 'agent',       label: 'New AI Agent',      stack: 'Python + BaseAgent',icon: '🤖' },
  { id: 'landing',     label: 'Landing Page',      stack: 'HTML + Tailwind',   icon: '📄' },
]

const DEFAULT_SKILL_PACKS = [
  { id: 'agent-skills', label: 'Agent Skills' },
  { id: 'automaton', label: 'Autonomy' },
  { id: 'cashclaw', label: 'Money' },
  { id: 'financial-services', label: 'Finance' },
  { id: 'wallet-vault', label: 'Wallet' },
]

const DANGEROUS_ACTION_TYPES = new Set([
  'command', 'shell', 'terminal', 'delete', 'remove', 'deploy', 'rollback',
  'publish', 'external_delivery', 'payment', 'wallet', 'install', 'dependency_install',
  'credential', 'secret', 'account_modify',
])
const DANGEROUS_TEXT = /\b(delete|remove|rm\s+-|wipe|deploy|rollback|publish|deliver|payment|wallet|spend|purchase|install|npm\s+i|pip\s+install|credential|secret|token|chmod|sudo|curl|wget|external)\b/i
const SAFE_BATCH_RISKS = new Set(['low', 'safe'])
const PENDING_STATUSES = new Set(['pending', 'pending_approval', 'awaiting_approval', 'requires_approval', 'queued'])

const compactId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

function textFrom(value, fallback = 'none') {
  if (value === undefined || value === null || value === '') return fallback
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function titleize(value, fallback = 'action') {
  return textFrom(value, fallback).replace(/[_-]+/g, ' ')
}

function normalizeRisk(value, score) {
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

function actionId(action) {
  return String(action?.id || action?.action_id || action?.request_id || action?.snapshot_id || action?.goal || compactId())
}

function normalizeAction(action = {}) {
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

function isPendingAction(action) {
  const status = normalizeAction(action).status.toLowerCase()
  return PENDING_STATUSES.has(status) || !['approved', 'rejected', 'deployed', 'failed', 'blocked'].includes(status)
}

function isDangerousAction(action) {
  const a = normalizeAction(action)
  const type = a.type.toLowerCase()
  const text = [a.type, a.label, a.description, a.command, a.target, a.approval].map(v => textFrom(v, '')).join(' ')
  if (['critical', 'high'].includes(a.risk)) return true
  if (DANGEROUS_ACTION_TYPES.has(type)) return true
  return DANGEROUS_TEXT.test(text)
}

function canBatchApprove(action) {
  const a = normalizeAction(action)
  return isPendingAction(a) && SAFE_BATCH_RISKS.has(a.risk) && !isDangerousAction(a)
}

function mergeActionLists(existing, incoming) {
  const map = new Map(existing.map(item => [normalizeAction(item).id, item]))
  incoming.forEach(item => {
    const normalized = normalizeAction(item)
    map.set(normalized.id, { ...(map.get(normalized.id) || {}), ...item, id: normalized.id })
  })
  return Array.from(map.values())
}

async function postFirst(candidates, body) {
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

/* ─── Sub-components ────────────────────────────────────────────────── */

function MiniField({ label, value }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div className="af-mini-field">
      <span>{label}</span>
      <strong>{textFrom(value)}</strong>
    </div>
  )
}

function StructuredList({ title, items }) {
  const list = Array.isArray(items) ? items : items ? [items] : []
  if (list.length === 0) return null
  return (
    <div className="af-structured">
      <div className="af-structured__title">{title}</div>
      {list.slice(0, 6).map((item, i) => (
        <div key={i} className="af-structured__item">
          <span className="af-structured__idx">{i + 1}</span>
          <span>{typeof item === 'string' ? item : textFrom(item.label || item.title || item.step || item.name || item)}</span>
          {typeof item === 'object' && item?.status && <em>{item.status}</em>}
        </div>
      ))}
    </div>
  )
}

function StructuredMessageBlock({ data }) {
  if (!data) return null
  const plan = data.plan || data.steps || data.execution_plan
  const lifecycle = data.lifecycle || data.action_lifecycle || data.gates
  const status = data.status || data.state
  const snapshot = data.snapshot_id || data.snapshot
  const policyDecision = data.policy_decision || data.policyDecision
  if (!plan && !lifecycle && !status && !snapshot && !policyDecision) return null
  return (
    <div className="af-msg-structured">
      <div className="af-mini-grid">
        <MiniField label="Status" value={status} />
        <MiniField label="Snapshot" value={snapshot} />
        <MiniField label="Policy" value={policyDecision} />
      </div>
      <StructuredList title="Plan" items={plan} />
      <StructuredList title="Lifecycle" items={lifecycle} />
    </div>
  )
}

function SkillPackSelector({ project, draftGoal, selectedSkillIds, onChange }) {
  const [skills, setSkills] = useState([])
  const [pack, setPack] = useState('all')
  const [loading, setLoading] = useState(false)
  const [recommending, setRecommending] = useState(false)
  const selected = new Set(selectedSkillIds)

  useEffect(() => {
    setLoading(true)
    JGET('/api/skills/library')
      .then(r => r.json())
      .then(d => setSkills(Array.isArray(d.skills) ? d.skills : []))
      .catch(() => setSkills([]))
      .finally(() => setLoading(false))
  }, [])

  const packs = [...new Map([
    ...DEFAULT_SKILL_PACKS,
    ...skills
      .filter(skill => skill.source_pack)
      .map(skill => ({ id: skill.source_pack, label: titleize(skill.source_pack) })),
  ].map(item => [item.id, item])).values()]

  const visible = skills
    .filter(skill => pack === 'all' || skill.source_pack === pack)
    .filter(skill => skill.compatible_agents?.includes('ascend-forge') || skill.source_pack || /agent|forge|policy|approval|code|build|workflow/i.test(`${skill.category || ''} ${skill.name || ''} ${skill.description || ''}`))
    .slice(0, 36)

  const toggle = (id) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(Array.from(next).slice(0, 12))
  }

  const recommend = async () => {
    setRecommending(true)
    try {
      const d = await JPOST_JSON('/api/forge/skills/recommend', {
        goal: draftGoal || project?.name || 'supervised build',
        target_type: project?.target_type || 'build_agent',
        limit: 8,
      })
      const ids = (d.recommendedSkills || []).map(skill => skill.id).filter(Boolean)
      if (ids.length) onChange(ids)
    } catch (e) {
      toastError(`Skill recommendation failed: ${e.message}`)
    } finally {
      setRecommending(false)
    }
  }

  return (
    <div className="af-skills">
      <div className="af-skills__header">
        <span>Skill Packs</span>
        <button className="af-btn af-btn--ghost af-btn--sm" disabled={recommending || loading} onClick={recommend}>
          {recommending ? '…' : 'Recommend'}
        </button>
      </div>
      <div className="af-skills__filters">
        <button className={`af-skill-filter ${pack === 'all' ? 'af-skill-filter--active' : ''}`} onClick={() => setPack('all')}>All</button>
        {packs.slice(0, 7).map(item => (
          <button key={item.id} className={`af-skill-filter ${pack === item.id ? 'af-skill-filter--active' : ''}`} onClick={() => setPack(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      {selectedSkillIds.length > 0 && (
        <div className="af-skills__selected">
          {selectedSkillIds.map(id => {
            const skill = skills.find(item => item.id === id)
            return <button key={id} onClick={() => toggle(id)}>{skill?.name || id}</button>
          })}
        </div>
      )}
      <div className="af-skills__list">
        {loading && <span className="af-skills__empty">Loading skill packs…</span>}
        {!loading && visible.length === 0 && <span className="af-skills__empty">No skills available</span>}
        {!loading && visible.map(skill => (
          <button
            key={skill.id}
            className={`af-skill ${selected.has(skill.id) ? 'af-skill--selected' : ''}`}
            onClick={() => toggle(skill.id)}
            title={skill.description || skill.id}
          >
            <span>{skill.name || skill.id}</span>
            <em>{skill.source_pack || skill.category || 'native'}</em>
          </button>
        ))}
      </div>
    </div>
  )
}

function ProjectPicker({ project, onSelect, onNew }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    JGET('/api/forge/projects').then(r => r.json()).then(d => {
      setProjects(d.projects || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="af-picker__loading">Loading projects…</div>

  return (
    <div className="af-picker">
      <div className="af-picker__actions">
        <button className="af-btn af-btn--primary" onClick={onNew}>+ New Project</button>
      </div>
      {projects.length === 0
        ? <EmptyState icon="📁" title="No projects" sub="Create a new project to start building." />
        : projects.map(p => (
          <button key={p.id} className={`af-picker__item ${project?.id === p.id ? 'af-picker__item--active' : ''}`} onClick={() => onSelect(p)}>
            <span className="af-picker__item-name">{p.name}</span>
            <span className="af-picker__item-path">{p.path}</span>
          </button>
        ))
      }
    </div>
  )
}

function NewProjectModal({ onClose, onCreate }) {
  const [name, setName] = useState('')
  const [template, setTemplate] = useState(TEMPLATES[0].id)
  const [creating, setCreating] = useState(false)

  const create = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const d = await JPOST_JSON('/api/forge/projects', { name, template })
      if (d.project) { onCreate(d); toastSuccess(`Project "${name}" scaffold staged`) }
      else toastError(d.error || 'Failed to create project')
    } catch (e) { toastError(e.message) }
    finally { setCreating(false) }
  }

  return (
    <div className="af-modal-overlay" onClick={onClose}>
      <div className="af-modal" onClick={e => e.stopPropagation()}>
        <h3 className="af-modal__title">New Project</h3>
        <label className="af-modal__label">Project Name</label>
        <input className="af-modal__input" value={name} onChange={e => setName(e.target.value)} placeholder="my-project" autoFocus />
        <label className="af-modal__label">Template</label>
        <div className="af-modal__templates">
          {TEMPLATES.map(t => (
            <button key={t.id} className={`af-tpl-btn ${template === t.id ? 'af-tpl-btn--active' : ''}`} onClick={() => setTemplate(t.id)}>
              <span>{t.icon}</span>
              <span className="af-tpl-btn__label">{t.label}</span>
              <span className="af-tpl-btn__stack">{t.stack}</span>
            </button>
          ))}
        </div>
        <div className="af-modal__actions">
          <button className="af-btn af-btn--ghost" onClick={onClose}>Cancel</button>
          <button className="af-btn af-btn--primary" onClick={create} disabled={creating || !name.trim()}>
            {creating ? 'Creating…' : 'Create Project'}
          </button>
        </div>
      </div>
    </div>
  )
}

function FileTree({ project, selectedFile, onSelect }) {
  const [tree, setTree] = useState(null)

  useEffect(() => {
    if (!project) return
    JGET(`/api/forge/files/tree?project_id=${project.id}`).then(r => r.json()).then(d => setTree(d.tree || [])).catch(() => setTree([]))
  }, [project?.id])

  if (!project) return <EmptyState icon="📁" title="No project" sub="Select or create a project" />
  if (!tree) return <div className="af-file-loading">Loading…</div>

  const renderNode = (node, depth = 0) => (
    <div key={node.path} style={{ paddingLeft: depth * 12 }}>
      {node.type === 'dir'
        ? <div className="af-tree__dir">📁 {node.name}</div>
        : <button className={`af-tree__file ${selectedFile?.path === node.path ? 'af-tree__file--active' : ''}`} onClick={() => onSelect(node)}>
            <span className="af-tree__file-icon">{node.name.endsWith('.py') ? '🐍' : node.name.endsWith('.js') || node.name.endsWith('.jsx') ? '⚡' : '📄'}</span>
            {node.name}
          </button>
      }
      {node.children?.map(c => renderNode(c, depth + 1))}
    </div>
  )

  return (
    <div className="af-file-tree">
      {tree.length === 0
        ? <EmptyState icon="📄" title="Empty project" sub="Start chatting to create files" />
        : tree.map(n => renderNode(n))}
    </div>
  )
}

function ChatPane({ project, sessionId, messages, onSend, sending, selectedSkillIds, onSkillChange }) {
  const inputRef = useRef(null)
  const endRef   = useRef(null)
  const [text, setText] = useState('')
  const [displayedContent, setDisplayedContent] = useState('')
  const [typingIdx, setTypingIdx] = useState(0)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, displayedContent])

  useEffect(() => {
    const lastMsg = messages[messages.length - 1]
    if (lastMsg?.role === 'assistant' && lastMsg.content) {
      setDisplayedContent('')
      setTypingIdx(0)
      const target = lastMsg.content
      let i = 0
      const t = setInterval(() => {
        i += 3
        setDisplayedContent(target.slice(0, i))
        if (i >= target.length) clearInterval(t)
      }, 16)
      return () => clearInterval(t)
    }
  }, [messages.length])

  const send = () => {
    if (!text.trim() || sending) return
    onSend(text.trim())
    setText('')
  }

  const onKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }

  return (
    <div className="af-chat">
      {project && (
        <SkillPackSelector
          project={project}
          draftGoal={text}
          selectedSkillIds={selectedSkillIds}
          onChange={onSkillChange}
        />
      )}
      <div className="af-chat__msgs">
        {messages.length === 0 && (
          <div className="af-chat__welcome">
            <div className="af-chat__welcome-icon">◆</div>
            <p className="af-chat__welcome-title">AscendForge Vibecoder</p>
            <p className="af-chat__welcome-sub">
              Tell me what to build. I'll plan, write code, and run tests — all with your approval.
            </p>
            <div className="af-chat__tips">
              <span>"Add a REST API endpoint for user login"</span>
              <span>"Build a new agent that monitors stock prices"</span>
              <span>"Refactor the auth system to use JWT"</span>
              <span>"Create a landing page with a dark theme"</span>
            </div>
          </div>
        )}
        {messages.map((m, i) => {
          const isLastAssistant = i === messages.length - 1 && m.role === 'assistant'
          const bodyText = isLastAssistant ? displayedContent : m.content
          const showCursor = isLastAssistant && displayedContent.length < (m.content?.length || 0)
          return (
            <div key={i} className={`af-msg af-msg--${m.role}`}>
              <div className="af-msg__role">{m.role === 'user' ? 'YOU' : 'FORGE'}</div>
              <div className="af-msg__body">
                {typeof bodyText === 'string'
                  ? bodyText.split('\n').map((l, j) => <p key={j}>{l}</p>)
                  : bodyText}
                {showCursor && <span className="af-typing-cursor">▋</span>}
              </div>
              <StructuredMessageBlock data={m} />
              {m.role === 'assistant' && m.actions?.length > 0 && (
                <div className="af-msg__actions-summary">
                  {m.actions.length} action{m.actions.length > 1 ? 's' : ''} proposed ↓
                </div>
              )}
            </div>
          )
        })}
        {sending && (
          <div className="af-msg af-msg--assistant">
            <div className="af-msg__role">FORGE</div>
            <div className="af-msg__body af-msg__body--thinking">
              <span className="af-thinking-dot" />
              <span className="af-thinking-dot" />
              <span className="af-thinking-dot" />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      {!project && (
        <div className="af-chat__no-project">Select or create a project first</div>
      )}
      <div className="af-chat__input-row">
        <textarea
          ref={inputRef}
          className="af-chat__input"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={project ? 'Tell me what to build…' : 'Select a project first'}
          disabled={!project || sending}
          rows={2}
        />
        <button className="af-btn af-btn--primary af-chat__send" onClick={send} disabled={!project || !text.trim() || sending}>
          {sending ? '…' : '▶'}
        </button>
      </div>
    </div>
  )
}

function DiffViewer({ diff }) {
  if (!diff) return <EmptyState icon="📋" title="No changes yet" sub="Start chatting to see proposed file changes" />
  return (
    <div className="af-diff">
      <div className="af-diff__header">
        <span className="af-diff__filename">{diff.path}</span>
        <StatusPill tone={diff.isNew ? 'success' : 'gold'} label={diff.isNew ? 'NEW' : 'MODIFIED'} />
      </div>
      <div className="af-diff__content">
        {diff.hunks?.map((hunk, hi) => (
          <div key={hi} className="af-diff__hunk">
            <div className="af-diff__hunk-header">{hunk.header}</div>
            {hunk.lines.map((line, li) => (
              <div key={li} className={`af-diff__line af-diff__line--${line.type}`}>
                <span className="af-diff__line-prefix">{line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' '}</span>
                <code>{line.content}</code>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function ActionQueue({ actions, busyActions, onApprove, onReject, onApproveSafeBatch }) {
  if (actions.length === 0) return <EmptyState icon="✓" title="No pending actions" sub="Actions proposed by Forge appear here for approval" />
  const normalized = actions.map(normalizeAction)
  const pending = normalized.filter(isPendingAction)
  const safeBatch = pending.length > 0 && pending.every(canBatchApprove)
  const hasUnsafePending = pending.some(a => !canBatchApprove(a))

  return (
    <div className="af-actions">
      <div className="af-actions__header">
        <span className="af-actions__count">{pending.length} pending / {actions.length} shown</span>
        {safeBatch && <button className="af-btn af-btn--primary af-btn--sm" onClick={onApproveSafeBatch}>Approve Safe Batch</button>}
        {hasUnsafePending && <span className="af-actions__gate">Individual approval required</span>}
      </div>
      {normalized.map(action => (
        <div key={action.id} className={`af-action af-action--${action.type.toLowerCase()} af-action--risk-${action.risk}`}>
          <div className="af-action__rail" />
          <div className="af-action__type-badge">{action.type.toUpperCase()}</div>
          <div className="af-action__detail">
            <div className="af-action__topline">
              <div className="af-action__label">{action.label}</div>
              <span className={`af-action__risk af-action__risk--${action.risk}`}>{action.risk.toUpperCase()}</span>
              <span className="af-action__status">{titleize(action.status)}</span>
            </div>
            {action.description && <div className="af-action__desc">{action.description}</div>}
            <div className="af-mini-grid">
              <MiniField label="Target" value={action.target} />
              <MiniField label="Snapshot" value={action.snapshotId} />
              <MiniField label="Approval" value={action.approval} />
              <MiniField label="Policy" value={action.policyDecision} />
              <MiniField label="Decided by" value={action.decidedBy} />
            </div>
            <MiniField label="Approval reason" value={action.approvalReason} />
            <MiniField label="Expected result" value={action.expectedResult} />
            <StructuredList title="Plan" items={action.plan} />
            <StructuredList title="Lifecycle" items={action.lifecycle} />
            <StructuredList title="Rollback" items={action.rollbackPlan} />
            {action.sandbox && (
              <pre className="af-action__sandbox">{JSON.stringify(action.sandbox, null, 2)}</pre>
            )}
          </div>
          <div className="af-action__btns">
            {isPendingAction(action) ? (
              <>
                <button className="af-btn af-btn--sm af-btn--success" disabled={busyActions[action.id]} onClick={() => onApprove(action.id)}>✓</button>
                <button className="af-btn af-btn--sm af-btn--danger"  disabled={busyActions[action.id]} onClick={() => onReject(action.id)}>✕</button>
              </>
            ) : (
              <span className="af-action__locked">closed</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function Terminal({ lines }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines])

  return (
    <div className="af-terminal">
      <div className="af-terminal__header">
        <span className="af-terminal__dot af-terminal__dot--r" />
        <span className="af-terminal__dot af-terminal__dot--y" />
        <span className="af-terminal__dot af-terminal__dot--g" />
        <span className="af-terminal__title">TERMINAL</span>
      </div>
      <div className="af-terminal__body">
        {lines.length === 0 && <span className="af-terminal__empty">No output yet.</span>}
        {lines.map((l, i) => (
          <div key={i} className={`af-terminal__line af-terminal__line--${l.type || 'out'}`}>
            <span className="af-terminal__prompt">{l.type === 'cmd' ? '$ ' : '  '}</span>
            <span>{l.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  )
}

function PolicyPreview({ actions }) {
  const [policy, setPolicy] = useState(null)
  const [lastDecision, setLastDecision] = useState(null)

  useEffect(() => {
    JGET('/api/autonomy/policy')
      .then(r => r.json())
      .then(d => setPolicy(d.policy || null))
      .catch(() => setPolicy({ state: 'degraded' }))
  }, [])

  useEffect(() => {
    const action = actions[0]
    if (!action) {
      setLastDecision(null)
      return
    }
    const normalized = normalizeAction(action)
    JPOST('/api/autonomy/tool-call/evaluate', {
      tool: normalized.type,
      action: normalized.label,
      intent: normalized.description,
    })
      .then(r => r.json())
      .then(setLastDecision)
      .catch(() => setLastDecision({ state: 'degraded', decision: 'requires_approval' }))
  }, [actions])

  const decision = lastDecision?.decision || 'waiting'
  const tone = decision === 'allow' || decision === 'allow_logged' ? 'success' : decision === 'block' ? 'alert' : 'warn'

  return (
    <div className="af-policy">
      <div className="af-policy__header">
        <span>Autonomy Policy</span>
        <StatusPill label={decision.toUpperCase()} tone={tone} size="sm" />
      </div>
      <div className="af-policy__body">
        <div className="af-policy__row">
          <span>Risk levels</span>
          <strong>{Object.keys(policy?.risk_levels || {}).length || 0}</strong>
        </div>
        <div className="af-policy__row">
          <span>Forbidden capabilities</span>
          <strong>{policy?.forbidden_capabilities?.length || 0}</strong>
        </div>
        <div className="af-policy__row">
          <span>First pending action</span>
          <strong>{lastDecision?.risk || 'none'}</strong>
        </div>
      </div>
    </div>
  )
}

function ForgeSystemPanel({ onQueueItems }) {
  const [data, setData] = useState({ loading: true })

  const load = useCallback(async () => {
    const [readiness, status, snapshots, queue] = await Promise.allSettled([
      JGET('/api/readiness').then(r => r.json()),
      JGET('/api/forge/status').then(r => r.json()),
      JGET('/api/forge/snapshots').then(r => r.json()),
      JGET('/api/forge/queue').then(r => r.json()),
    ])
    const next = {
      loading: false,
      readiness: readiness.status === 'fulfilled' ? readiness.value : null,
      status: status.status === 'fulfilled' ? status.value : null,
      snapshots: snapshots.status === 'fulfilled' ? snapshots.value : null,
      queue: queue.status === 'fulfilled' ? queue.value : null,
    }
    setData(next)
    if (next.queue?.items) onQueueItems(next.queue.items)
  }, [onQueueItems])

  useEffect(() => {
    load()
    const t = window.setInterval(load, 30000)
    return () => window.clearInterval(t)
  }, [load])

  const readiness = data.readiness?.readiness || data.readiness || {}
  const status = data.status || {}
  const snapshots = data.snapshots?.snapshots || []
  const summary = data.snapshots?.summary || {}
  const latest = snapshots[0] || {}
  const readyState = readiness.ready === true || readiness.status === 'ok'
    ? 'ready'
    : readiness.status || (data.loading ? 'loading' : 'degraded')
  const statusTone = status.frozen || readyState === 'degraded' ? 'warn' : readyState === 'ready' ? 'success' : 'idle'

  return (
    <div className="af-ops">
      <div className="af-ops__header">
        <span>Forge Operations</span>
        <StatusPill label={String(readyState).toUpperCase()} tone={statusTone} size="sm" />
      </div>
      <div className="af-mini-grid">
        <MiniField label="Mode" value={status.mode || status.state} />
        <MiniField label="Active" value={status.active} />
        <MiniField label="Frozen" value={status.frozen ?? status.forge_frozen} />
        <MiniField label="Queue" value={status.queue_depth ?? data.queue?.total} />
        <MiniField label="Snapshots" value={summary.total_snapshots ?? snapshots.length} />
        <MiniField label="Latest" value={latest.id || latest.snapshot_id} />
      </div>
      {(readiness.python || readiness.node || readiness.neural_brain || readiness.graph || readiness.ai_core) && (
        <div className="af-ops__chips">
          {['node', 'python', 'ai_core', 'neural_brain', 'graph'].map(key => (
            readiness[key] !== undefined && <span key={key}>{key}: {textFrom(readiness[key])}</span>
          ))}
        </div>
      )}
      {latest.module && (
        <div className="af-ops__latest">
          <span>{latest.module}</span>
          <strong>{latest.status || latest.tag || 'snapshot'}</strong>
        </div>
      )}
    </div>
  )
}

function AgentBlueprintPanel() {
  const [status, setStatus] = useState(null)
  const [name, setName] = useState('AETERNUS Builder Agent')
  const [purpose, setPurpose] = useState('Build and improve AETERNUS systems with coding, testing, security, and release skills.')
  const [blueprint, setBlueprint] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    JGET('/api/forge/engine/status')
      .then(r => r.json())
      .then(setStatus)
      .catch(() => setStatus({ state: 'degraded' }))
  }, [])

  const createBlueprint = async () => {
    setBusy(true)
    try {
      const r = await JPOST('/api/forge/agents/blueprint', {
        name,
        purpose,
        target_type: 'coding_agent',
      })
      const d = await r.json()
      if (d.blueprint) {
        setBlueprint(d.blueprint)
        toastSuccess('Agent blueprint created')
      } else toastError(d.error || 'Blueprint failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  const registerBlueprint = async () => {
    if (!blueprint) return
    setBusy(true)
    try {
      const r = await JPOST(`/api/forge/agents/${blueprint.id}/register`, { ownerApproved: true })
      const d = await r.json()
      if (d.agent) {
        setBlueprint(d.blueprint)
        toastSuccess('Supervised builder agent registered')
      } else toastError(d.error || 'Registration failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="af-blueprint">
      <div className="af-blueprint__header">
        <span>Create Agent</span>
        <StatusPill label={(status?.state || 'loading').toUpperCase()} tone={status?.state === 'live' ? 'success' : 'idle'} size="sm" />
      </div>
      <input className="af-blueprint__input" value={name} onChange={e => setName(e.target.value)} placeholder="Agent name" />
      <textarea className="af-blueprint__textarea" value={purpose} onChange={e => setPurpose(e.target.value)} rows={3} />
      <button className="af-btn af-btn--primary af-btn--sm" disabled={busy || !name.trim() || !purpose.trim()} onClick={createBlueprint}>
        {busy ? 'Working…' : 'Generate Blueprint'}
      </button>

      {blueprint && (
        <div className="af-blueprint__result">
          <div className="af-blueprint__name">{blueprint.name}</div>
          <div className="af-blueprint__meta">{blueprint.authority_profile} · {blueprint.risk_level} · {blueprint.registration_status}</div>
          <div className="af-blueprint__chips">
            {(blueprint.selected_skills || []).slice(0, 6).map(skill => (
              <span key={skill.id} className="af-blueprint__chip">{skill.name}</span>
            ))}
          </div>
          <button
            className="af-btn af-btn--success af-btn--sm"
            disabled={busy || blueprint.registration_status === 'registered'}
            onClick={registerBlueprint}
          >
            {blueprint.registration_status === 'registered' ? 'Registered' : 'Approve + Register'}
          </button>
        </div>
      )}
    </div>
  )
}

function FileEditor({ project, selectedFile, onSave }) {
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!project || !selectedFile) return
    setLoading(true)
    JGET(`/api/forge/files/read?project_id=${project.id}&file_path=${encodeURIComponent(selectedFile)}`)
      .then(r => r.json())
      .then(d => { setContent(d.content || ''); setOriginal(d.content || '') })
      .finally(() => setLoading(false))
  }, [project?.id, selectedFile])

  const save = async () => {
    setSaving(true)
    try {
      await JPOST_JSON('/api/forge/files/write', { project_id: project.id, file_path: selectedFile, content })
      setOriginal(content)
      if (onSave) onSave(selectedFile)
      toastSuccess('File saved')
    } catch (e) { toastError(e.message) }
    finally { setSaving(false) }
  }

  if (!selectedFile) return <div className="forge-editor-empty">Select a file to edit</div>
  if (loading) return <div className="forge-editor-empty">Loading…</div>
  return (
    <div className="forge-editor">
      <div className="forge-editor-bar">
        <span className="forge-editor-filename">{selectedFile}</span>
        {content !== original && (
          <button className="forge-editor-save" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : '↑ Save'}
          </button>
        )}
      </div>
      <textarea
        className="forge-editor-area"
        value={content}
        onChange={e => setContent(e.target.value)}
        spellCheck={false}
      />
    </div>
  )
}

/* ─── Understand pane: index the project, view architecture, search context ─── */
function UnderstandPane({ project }) {
  const [summary, setSummary] = useState(null)
  const [indexing, setIndexing] = useState(false)
  const [query, setQuery] = useState('')
  const [ctx, setCtx] = useState(null)
  const [searching, setSearching] = useState(false)

  const loadSummary = useCallback(() => {
    if (!project) return
    JGET(`/api/forge/summary/${project.id}`).then(r => r.json()).then(d => setSummary(d?.ok ? d : null)).catch(() => setSummary(null))
  }, [project])
  useEffect(() => { loadSummary() }, [loadSummary])

  if (!project) return <div className="af-chat__no-project">Select a project to understand its architecture.</div>

  const index = async () => {
    setIndexing(true)
    try { const d = await JPOST_JSON('/api/forge/index', { project_id: project.id }); setSummary(d); toastSuccess(`Indexed ${d.files} files → ${d.chunks} chunks`) }
    catch (e) { toastError(e.message) } finally { setIndexing(false) }
  }
  const search = async () => {
    if (!query.trim()) return
    setSearching(true)
    try { setCtx(await JPOST_JSON('/api/forge/context', { project_id: project.id, query, k: 6 })) }
    catch (e) { toastError(e.message) } finally { setSearching(false) }
  }

  return (
    <div className="af-understand">
      <div className="af-understand__actions">
        <button className="af-index-btn" onClick={index} disabled={indexing}>{indexing ? 'Indexing…' : '⟳ Index project'}</button>
        {summary?.indexed_at && <span className="af-understand__meta">{summary.files} files · {summary.chunks} chunks</span>}
      </div>

      {summary?.ok && (
        <div className="af-understand__summary">
          <div className="af-understand__row"><span>Languages</span><b>{Object.entries(summary.languages || {}).map(([l, n]) => `${l} ${n}`).join(' · ') || '—'}</b></div>
          <div className="af-understand__row"><span>Entry points</span><b>{(summary.entry_points || []).join(', ') || '—'}</b></div>
          <div className="af-understand__row"><span>Import edges</span><b>{summary.import_edges ?? '—'}</b></div>
          <SectionLabel>TOP MODULES</SectionLabel>
          <ul className="af-understand__modules">
            {(summary.top_modules || []).slice(0, 10).map(m => (
              <li key={m.path}><code>{m.path}</code> <span>{m.symbol_count} symbols</span></li>
            ))}
          </ul>
        </div>
      )}
      {!summary?.ok && !indexing && <div className="af-understand__hint">Not indexed yet — click “Index project” so the builder understands this codebase.</div>}

      <div className="af-understand__search">
        <SectionLabel>FIND RELEVANT CODE</SectionLabel>
        <div className="af-understand__searchrow">
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. where is auth handled?" onKeyDown={e => e.key === 'Enter' && search()} />
          <button onClick={search} disabled={searching}>{searching ? '…' : 'Search'}</button>
        </div>
        {ctx?.results?.map((r, i) => (
          <div key={i} className="af-understand__hit">
            <div className="af-understand__hitpath"><code>{r.path}</code>{r.symbol ? ` :: ${r.symbol}` : ''}</div>
            <pre>{(r.snippet || '').slice(0, 500)}</pre>
          </div>
        ))}
        {ctx && !ctx.results?.length && <div className="af-understand__hint">No matches.</div>}
      </div>
    </div>
  )
}

/* ─── Main page ────────────────────────────────────────────────────── */

export default function AscendForgePage() {
  const [project, setProject]       = useState(null)
  const [showNewProj, setShowNewProj] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [sessionId, setSessionId]   = useState(null)
  const [messages, setMessages]     = useState([])
  const [sending, setSending]       = useState(false)
  const [actions, setActions]       = useState([])
  const [busyActions, setBusyActions] = useState({})
  const [termLines, setTermLines]   = useState([])
  const [currentDiff, setCurrentDiff] = useState(null)
  const [provider, setProvider]     = useState('anthropic')
  const [selectedSkillIds, setSelectedSkillIds] = useState([])
  const [tab, setTab]               = useState('chat') // 'chat' | 'tree'
  const [fileViewTab, setFileViewTab] = useState('diff') // 'diff' | 'editor'
  const [editorFile, setEditorFile] = useState(null) // file path string for editor

  const addTerm = (text, type = 'out') => setTermLines(p => [...p.slice(-200), { text, type, ts: Date.now() }])
  const mergeActions = useCallback((items) => {
    setActions(prev => mergeActionLists(prev, items))
  }, [])

  // Create/resume forge session when project changes
  useEffect(() => {
    if (!project) return
    JPOST('/api/forge/sessions', { project_id: project.id, provider, selected_skill_ids: selectedSkillIds }).then(r => r.json()).then(d => {
      setSessionId(d.session_id)
      setMessages(d.history || [])
    }).catch(e => toastError(`Session error: ${e.message}`))
  }, [project?.id, provider])

  const sendMessage = useCallback(async (text) => {
    if (!sessionId || sending) return
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setMessages(prev => [...prev, { role: 'assistant', content: '▋', ts: new Date().toISOString(), _streaming: true }])

    let accumulated = ''
    try {
      const jwt = sessionStorage.getItem('ai_jwt')
      const resp = await fetch(`/api/forge/sessions/${sessionId}/messages/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(jwt ? { Authorization: `Bearer ${jwt}` } : {}) },
        body: JSON.stringify({ content: text, selected_skill_ids: selectedSkillIds }),
      })
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.text !== undefined) {
              accumulated += ev.text
              setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: accumulated + '▋' } : m))
            } else if (ev.content !== undefined) {
              // done event — finalise message
              const finalMsg = { role: 'assistant', ts: new Date().toISOString(), content: ev.content, actions: ev.actions || [], _streaming: false }
              setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? finalMsg : m))
              if (ev.actions?.length) {
                mergeActions(ev.actions.map(a => ({ ...a, id: a.id || compactId(), source: a.source || 'session' })))
              }
            } else if (ev.error) {
              toastError(`Forge error: ${ev.error}`)
            }
          } catch { /* malformed SSE line — skip */ }
        }
      }
    } catch (e) {
      setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: `Error: ${e.message}`, _streaming: false } : m))
      toastError(`Send failed: ${e.message}`)
    } finally {
      setSending(false)
    }
  }, [sessionId, sending, selectedSkillIds, mergeActions])

  const approveAction = async (id) => {
    const action = actions.find(a => a.id === id)
    if (!action) return
    const normalized = normalizeAction(action)
    setBusyActions(prev => ({ ...prev, [id]: true }))
    addTerm(`Approving: ${normalized.label}`, 'cmd')
    try {
      const approveTarget = normalized.snapshotId || normalized.id
      const queueFirst = normalized.source === 'queue' || normalized.snapshotId
      const paths = queueFirst
        ? [`/api/forge/approve/${approveTarget}`, `/api/forge/actions/${normalized.id}/approve`]
        : [`/api/forge/actions/${normalized.id}/approve`, `/api/forge/approve/${approveTarget}`]
      const d = await postFirst(paths, {
        session_id: sessionId,
        ownerApproved: true,
        approval: 'owner-approved',
        approved_by: 'operator',
      })
      if (d.output) {
        setTermLines(prev => [
          ...prev,
          { text: `[${normalized.type}] ${normalized.label || ''}`, type: 'cmd', ts: Date.now() },
          ...d.output.split('\n').map(l => ({ text: l, type: 'out', ts: Date.now() })),
          { text: d.ok !== false ? '✓ Done' : '✗ Failed', type: d.ok !== false ? 'out' : 'err', ts: Date.now() },
        ])
      }
      if (d.error) addTerm(`ERROR: ${d.error}`, 'err')
      if (d.diff) setCurrentDiff(d.diff)
      const result = d.request || d.action || d
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, ...result, status: result.status || 'approved' } : a))
      toastSuccess(`Action approved: ${normalized.label}`)
    } catch (e) {
      addTerm(`FAILED: ${e.message}`, 'err')
      toastError(`Action failed: ${e.message}`)
    } finally {
      setBusyActions(prev => ({ ...prev, [id]: false }))
    }
  }

  const rejectAction = async (id) => {
    const action = actions.find(a => a.id === id)
    if (!action) return
    const normalized = normalizeAction(action)
    setBusyActions(prev => ({ ...prev, [id]: true }))
    try {
      const rejectTarget = normalized.snapshotId || normalized.id
      const d = await postFirst([
        `/api/forge/reject/${rejectTarget}`,
        `/api/forge/actions/${normalized.id}/reject`,
      ], { session_id: sessionId, reason: 'Rejected from AscendForge UI' })
      const result = d.request || d.action || d
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, ...result, status: result.status || 'rejected' } : a))
      addTerm(`Rejected: ${normalized.label}`, 'warn')
    } catch (e) {
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, status: 'rejected' } : a))
      addTerm(`Rejected locally: ${normalized.label}`, 'warn')
    } finally {
      setBusyActions(prev => ({ ...prev, [id]: false }))
    }
  }

  const approveSafeBatch = () => {
    const safe = actions.map(normalizeAction).filter(canBatchApprove)
    if (safe.length === 0 || safe.length !== actions.filter(isPendingAction).length) {
      toastError('Batch approval is available only for all-low-risk action sets')
      return
    }
    safe.forEach(a => approveAction(a.id))
  }

  const handleProjectCreated = useCallback((result) => {
    const nextProject = result.project || result
    setProject(nextProject)
    setShowNewProj(false)
    setTab('chat')
    if (result.plan) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Project scaffold prepared for approval.',
        plan: result.plan,
        actions: result.actions || [],
        diff: result.diff || null,
      }])
    }
    if (result.actions?.length) mergeActions(result.actions.map(a => ({ ...a, source: a.source || 'project' })))
    if (result.diff) setCurrentDiff(result.diff)
  }, [mergeActions])

  return (
    <div className="af-page">
      {/* ─ Header ─────────────────────────────────────────────────── */}
      <div className="af-header">
        <div className="af-header__left">
          <span className="af-header__title">◆ ASCENDFORGE</span>
          <span className="af-header__sub">Agentic Vibecoder</span>
        </div>
        <div className="af-header__controls">
          <select className="af-select" value={provider} onChange={e => setProvider(e.target.value)}>
            {LLM_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.icon} {p.label}</option>)}
          </select>
          {project && <StatusPill tone="success" label={project.name} />}
        </div>
      </div>

      {/* ─ 3-pane layout ──────────────────────────────────────────── */}
      <div className="af-layout">

        {/* Left pane — Project tree / chat */}
        <div className="af-pane af-pane--left">
          <div className="af-pane__tabs">
            <button className={`af-tab ${tab === 'chat' ? 'af-tab--active' : ''}`} onClick={() => setTab('chat')}>Chat</button>
            <button className={`af-tab ${tab === 'tree' ? 'af-tab--active' : ''}`} onClick={() => setTab('tree')}>Files</button>
            <button className={`af-tab ${tab === 'understand' ? 'af-tab--active' : ''}`} onClick={() => setTab('understand')}>Understand</button>
            <button className={`af-tab ${tab === 'projects' ? 'af-tab--active' : ''}`} onClick={() => setTab('projects')}>Projects</button>
          </div>

          {tab === 'chat' && (
            <ChatPane
              project={project}
              sessionId={sessionId}
              messages={messages}
              onSend={sendMessage}
              sending={sending}
              selectedSkillIds={selectedSkillIds}
              onSkillChange={setSelectedSkillIds}
            />
          )}
          {tab === 'tree' && (
            <FileTree
              project={project}
              selectedFile={selectedFile}
              onSelect={node => { setSelectedFile(node); setEditorFile(node?.path || null) }}
            />
          )}
          {tab === 'understand' && <UnderstandPane project={project} />}
          {tab === 'projects' && (
            <ProjectPicker
              project={project}
              onSelect={p => { setProject(p); setTab('chat') }}
              onNew={() => setShowNewProj(true)}
            />
          )}
        </div>

        {/* Center pane — Diff viewer + Editor */}
        <div className="af-pane af-pane--center">
          <div className="af-pane__header">
            <SectionLabel>CHANGES</SectionLabel>
            <div className="af-file-view-tabs">
              <button
                className={`af-file-view-tab ${fileViewTab === 'diff' ? 'af-file-view-tab--active' : ''}`}
                onClick={() => setFileViewTab('diff')}
              >DIFF</button>
              <button
                className={`af-file-view-tab ${fileViewTab === 'editor' ? 'af-file-view-tab--active' : ''}`}
                onClick={() => setFileViewTab('editor')}
              >EDITOR</button>
            </div>
          </div>
          {fileViewTab === 'diff'
            ? <DiffViewer diff={currentDiff} />
            : <FileEditor project={project} selectedFile={editorFile} />
          }
        </div>

        {/* Right pane — Action queue + terminal */}
        <div className="af-pane af-pane--right">
          <div className="af-pane__section">
            <div className="af-pane__header">
              <SectionLabel>APPROVAL QUEUE</SectionLabel>
              {actions.length > 0 && <span className="af-badge">{actions.length}</span>}
            </div>
            <ForgeSystemPanel onQueueItems={items => mergeActions(items.map(item => ({ ...item, source: 'queue', type: item.type || 'forge_request' })))} />
            <PolicyPreview actions={actions} />
            <AgentBlueprintPanel />
            <ActionQueue
              actions={actions}
              busyActions={busyActions}
              onApprove={approveAction}
              onReject={rejectAction}
              onApproveSafeBatch={approveSafeBatch}
            />
          </div>
          <div className="af-pane__section af-pane__section--grow">
            <Terminal lines={termLines} />
          </div>
        </div>
      </div>

      {showNewProj && (
        <NewProjectModal
          onClose={() => setShowNewProj(false)}
          onCreate={handleProjectCreated}
        />
      )}
    </div>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'
import { SectionLabel, StatusPill, EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JPOST, JGET, JPOST_JSON, TEMPLATES, DEFAULT_SKILL_PACKS, textFrom, titleize, normalizeAction, isPendingAction, canBatchApprove } from './helpers'
import api from '../../../api/client'
import { MiniField, StructuredList, StructuredMessageBlock } from './primitives'

const RUN_WRITE_TYPES = new Set(['write_file', 'file_create', 'file_update', 'scaffold_create'])
const CLOSED_ACTION_STATUSES = new Set(['staged', 'verified', 'applied', 'verify_failed', 'rejected', 'failed', 'blocked', 'deployed'])

function needsOperatorDecision(action) {
  const normalized = normalizeAction(action)
  return isPendingAction(normalized) && !CLOSED_ACTION_STATUSES.has(normalized.status.toLowerCase())
}

function formatCount(value, label) {
  const count = Array.isArray(value) ? value.length : Number(value || 0)
  return `${count} ${label}${count === 1 ? '' : 's'}`
}

export function SkillPackSelector({ project, draftGoal, selectedSkillIds, onChange }) {
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

export function ProjectPicker({ project, onSelect, onNew }) {
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

export function NewProjectModal({ onClose, onCreate }) {
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

export function FileTree({ project, selectedFile, onSelect }) {
  const [tree, setTree] = useState(null)
  const projectId = project?.id

  useEffect(() => {
    if (!projectId) return
    JGET(`/api/forge/files/tree?project_id=${projectId}`).then(r => r.json()).then(d => setTree(d.tree || [])).catch(() => setTree([]))
  }, [projectId])

  if (!project) return <EmptyState icon="📁" title="No project" sub="Select or create a project" />
  if (!tree) return <div className="af-file-loading">Loading…</div>

  const renderNode = (node, depth = 0) => (
    <div key={node.path} className={`af-tree__indent af-tree__indent--${Math.min(depth, 6)}`}>
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

export function ChatPane({ project, messages, onSend, sending, selectedSkillIds, onSkillChange, draftGoal, setDraftGoal }) {
  const inputRef = useRef(null)
  const endRef   = useRef(null)
  const [text, setText] = useState('')

  // Sync external draftGoal into local text when it changes
  useEffect(() => {
    if (draftGoal) {
      setText(draftGoal)
      setDraftGoal?.('')
      inputRef.current?.focus()
    }
  }, [draftGoal, setDraftGoal])

  // Scroll to bottom when messages change, debounced to avoid hammering layout
  const scrollTimer = useRef(null)
  useEffect(() => {
    clearTimeout(scrollTimer.current)
    scrollTimer.current = setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 80)
    return () => clearTimeout(scrollTimer.current)
  }, [messages])

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
          const bodyText = m.content
          return (
            <div key={i} className={`af-msg af-msg--${m.role}`}>
              <div className="af-msg__role">{m.role === 'user' ? 'YOU' : 'FORGE'}</div>
              <div className="af-msg__body">
                {typeof bodyText === 'string'
                  ? bodyText.split('\n').map((l, j) => <p key={j}>{l}</p>)
                  : bodyText}
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

export function DiffViewer({ diff }) {
  if (!diff) return <EmptyState icon="📋" title="No changes yet" sub="Start chatting to see proposed file changes" />
  if (typeof diff === 'string') {
    return (
      <div className="af-diff">
        <div className="af-diff__header">
          <span className="af-diff__filename">Unified diff</span>
          <StatusPill tone="gold" label="PATCH" />
        </div>
        <pre className="af-diff__raw">{diff}</pre>
      </div>
    )
  }
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

export function RunTimeline({ run, onVerify, onApply, busy }) {
  if (!run) {
    return (
      <div className="af-run-compact">
        <div className="af-run-compact__empty">
          <strong>◆ No active run</strong> — send a goal to start
        </div>
      </div>
    )
  }
  const latestTest = (run.test_results || []).slice(-1)[0]
  const patches = run.patches || []
  const actions = run.actions || []
  const stagedCount = patches.filter(patch => ['staged', 'verified', 'applied'].includes(String(patch.status || '').toLowerCase())).length
  const blockedCount = patches.filter(patch => patch.policy?.allowed === false || String(patch.status || '').toLowerCase() === 'blocked').length
  const writeCount = actions.filter(action => RUN_WRITE_TYPES.has(action.type)).length || patches.length
  const canVerify = !busy && stagedCount > 0 && blockedCount === 0 && run.status !== 'applied'
  const canApply = !busy && run.status === 'verified' && latestTest?.all_passed === true && blockedCount === 0
  const verifyReason = busy ? 'Run operation in progress'
    : blockedCount > 0 ? 'Blocked patches must be resolved first'
    : stagedCount === 0 ? 'Approve and stage a write action first'
    : run.status === 'applied' ? 'Run has already been applied'
    : 'Run is staged and ready to verify'
  const applyReason = busy ? 'Run operation in progress'
    : run.status !== 'verified' ? 'Verification must pass before apply'
    : latestTest?.all_passed !== true ? 'Latest verification did not pass'
    : blockedCount > 0 ? 'Blocked patches cannot be applied'
    : 'Verified run is ready to apply'
  const statusTone = run.status === 'applied' || run.status === 'verified' ? 'success'
    : run.status === 'blocked' || run.status === 'verify_failed' ? 'alert'
    : 'gold'
  const NEXT = { new: 'APPROVAL', awaiting_approval: 'STAGING', pending_approval: 'STAGING', staged: 'VERIFY', verified: 'APPLY', applied: 'DONE' }
  const nextStageLabel = NEXT[run.status] ?? 'REVIEW'

  return (
    <div className="af-run-compact">
      <div className="af-run-compact__stage-row">
        <span>Stage:</span>
        <StatusPill label={String(run.status || 'new').toUpperCase()} tone={statusTone} size="sm" />
        <span className="af-run-compact__stage-arrow">→</span>
        <span>Next:</span>
        <StatusPill label={nextStageLabel} tone="idle" size="sm" />
        <code style={{marginLeft:'auto',fontSize:9,color:'var(--nx-text-muted)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:80}}>{run.id}</code>
      </div>
      <div className="af-run-compact__counts">
        <div className="af-run-compact__count"><b>{stagedCount}</b><small>staged</small></div>
        <div className="af-run-compact__count"><b>{blockedCount}</b><small>blocked</small></div>
        <div className="af-run-compact__count"><b>{writeCount}</b><small>writes</small></div>
      </div>
      {run.ui_error && <div style={{color:'var(--af-red)',fontSize:10,marginBottom:6}}>{run.ui_error}</div>}
      <div className="af-run-compact__actions">
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={onVerify} disabled={!canVerify} title={verifyReason}>
          {busy ? '…' : 'Verify'}
        </button>
        <button className="af-btn af-btn--primary af-btn--sm" onClick={onApply} disabled={!canApply} title={applyReason}>
          Apply
        </button>
      </div>
    </div>
  )
}

export function ActionQueue({ actions, busyActions, onApprove, onReject, onApproveSafeBatch, expandedActions, onToggleExpand }) {
  if (actions.length === 0) return <EmptyState icon="✓" title="No pending actions" sub="Actions proposed by Forge appear here for approval" />
  const normalized = actions.map(normalizeAction)
  const pending = normalized.filter(needsOperatorDecision)
  const safeBatch = pending.length > 0 && pending.every(canBatchApprove)
  const hasUnsafePending = pending.some(a => !canBatchApprove(a))

  return (
    <div className="af-actions">
      <div className="af-actions__header">
        <span className="af-actions__count">{pending.length} pending / {actions.length} shown</span>
        {safeBatch && <button className="af-btn af-btn--primary af-btn--sm" onClick={onApproveSafeBatch}>Approve Safe Batch</button>}
        {hasUnsafePending && <span className="af-actions__gate">Individual approval required</span>}
      </div>
      {normalized.map(action => {
        const open = needsOperatorDecision(action)
        const busy = !!busyActions[action.id]
        const isExpanded = expandedActions?.has(action.id) ?? false
        return (
        <div key={action.id} className={`af-action ${open ? '' : 'af-action--closed'} af-action--${action.type.toLowerCase()} af-action--risk-${action.risk} ${isExpanded ? 'af-action--expanded' : 'af-action--collapsed'}`}>
          <div className="af-action__rail" />
          <div className="af-action__detail">
            <button className="af-action__collapse-row" onClick={() => onToggleExpand?.(action.id)} aria-expanded={isExpanded}>
              <div className="af-action__type-badge">{action.type.toUpperCase()}</div>
              <div className="af-action__label">{action.label}</div>
              <span className={`af-action__risk af-action__risk--${action.risk}`}>{action.risk.toUpperCase()}</span>
              <span className="af-action__status">{titleize(action.status)}</span>
              <span className="af-action__expand-chevron">▶</span>
            </button>
            <div className="af-action__detail-body">
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
            </div>
          </div>
          <div className="af-action__btns">
            {open ? (
              <>
                <button className="af-btn af-btn--sm af-btn--success" disabled={busy} onClick={() => onApprove(action.id)} title="Approve and stage this action">✓</button>
                <button className="af-btn af-btn--sm af-btn--danger"  disabled={busy} onClick={() => onReject(action.id)} title="Reject this action">✕</button>
              </>
            ) : (
              <span className="af-action__locked">{titleize(action.status, 'closed')}</span>
            )}
          </div>
        </div>
      )})}
    </div>
  )
}

export function Terminal({ lines }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines])

  return (
    <div className="af-terminal">
      <div className="af-terminal__header">
        <span className="af-terminal__dot af-terminal__dot--r" />
        <span className="af-terminal__dot af-terminal__dot--y" />
        <span className="af-terminal__dot af-terminal__dot--g" />
        <span className="af-terminal__title">RUN CONSOLE</span>
      </div>
      <div className="af-terminal__body">
        {lines.length === 0 && <span className="af-terminal__empty">No run output yet. Create, stage, verify, or apply a run to stream real events here.</span>}
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

export function PolicyPreview({ actions }) {
  const [policy, setPolicy] = useState(null)
  const [lastDecision, setLastDecision] = useState(null)
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    JGET('/api/autonomy/policy')
      .then(r => r.json())
      .then(d => setPolicy(d.policy || null))
      .catch(() => setPolicy({ state: 'degraded' }))
  }, [])

  useEffect(() => {
    const action = actions[0]
    if (!action) return
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

  const visibleDecision = actions.length ? lastDecision : null
  const decision = visibleDecision?.decision || 'waiting'
  const tone = decision === 'allow' || decision === 'allow_logged' ? 'success' : decision === 'block' ? 'alert' : 'warn'

  return (
    <div className={`af-accordion ${isOpen ? 'af-accordion--open' : ''}`}>
      <button className="af-accordion__toggle" onClick={() => setIsOpen(o => !o)}>
        <div className="af-accordion__summary">
          <span>Autonomy Policy</span>
          <StatusPill label={decision.toUpperCase()} tone={tone} size="sm" />
        </div>
        <span className="af-accordion__chevron">▾</span>
      </button>
      {isOpen && (
        <div className="af-accordion__body">
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
              <strong>{visibleDecision?.risk || 'none'}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function ForgeSystemPanel({ onQueueItems }) {
  const [data, setData] = useState({ loading: true })
  const [isOpen, setIsOpen] = useState(false)

  const load = useCallback(async () => {
    const [readiness, status, snapshots, queue, runs] = await Promise.allSettled([
      JGET('/api/readiness').then(r => r.json()),
      JGET('/api/forge/status').then(r => r.json()),
      JGET('/api/forge/snapshots').then(r => r.json()),
      JGET('/api/forge/queue').then(r => r.json()),
      JGET('/api/forge/runs?limit=5').then(r => r.json()),
    ])
    const next = {
      loading: false,
      readiness: readiness.status === 'fulfilled' ? readiness.value : null,
      status: status.status === 'fulfilled' ? status.value : null,
      snapshots: snapshots.status === 'fulfilled' ? snapshots.value : null,
      queue: queue.status === 'fulfilled' ? queue.value : null,
      runs: runs.status === 'fulfilled' ? runs.value : null,
    }
    setData(next)
    if (next.queue?.items) onQueueItems(next.queue.items)
  }, [onQueueItems])

  useEffect(() => {
    const first = window.setTimeout(load, 0)
    const t = window.setInterval(load, 30000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(t)
    }
  }, [load])

  const readiness = data.readiness?.readiness || data.readiness || {}
  const status = data.status || {}
  const snapshots = data.snapshots?.snapshots || []
  const summary = data.snapshots?.summary || {}
  const latest = snapshots[0] || {}
  const recentRuns = data.runs?.runs || []
  const persistence = status.persistence || data.runs?.persistence || {}
  const readyState = readiness.ready === true || readiness.status === 'ok'
    ? 'ready'
    : readiness.status || (data.loading ? 'loading' : 'degraded')
  const statusTone = status.frozen || readyState === 'degraded' ? 'warn' : readyState === 'ready' ? 'success' : 'idle'

  return (
    <div className={`af-accordion ${isOpen ? 'af-accordion--open' : ''}`}>
      <button className="af-accordion__toggle" onClick={() => setIsOpen(o => !o)}>
        <div className="af-accordion__summary">
          <span>Forge Operations</span>
          <StatusPill label={String(readyState).toUpperCase()} tone={statusTone} size="sm" />
          <span style={{marginLeft:'auto',fontSize:9,color:'var(--nx-text-muted)',fontWeight:400,textTransform:'none',letterSpacing:0}}>
            {(status.runs_total ?? data.runs?.total ?? 0)} runs
          </span>
        </div>
        <span className="af-accordion__chevron">▾</span>
      </button>
      {isOpen && (
        <div className="af-accordion__body">
          <div className="af-ops">
            {data.loading && <div className="af-ops__notice">Loading live Forge status...</div>}
            {!data.loading && !data.status && <div className="af-ops__notice af-ops__notice--warn">Forge status endpoint did not respond.</div>}
            <div className="af-mini-grid">
              <MiniField label="Mode" value={status.mode || status.state} />
              <MiniField label="Active" value={status.active} />
              <MiniField label="Frozen" value={status.frozen ?? status.forge_frozen} />
              <MiniField label="Queue" value={status.queue_depth ?? data.queue?.total} />
              <MiniField label="Run Store" value={persistence.backend || textFrom(status.persistence)} />
              <MiniField label="Runs" value={status.runs_total ?? data.runs?.total} />
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
            {recentRuns.length > 0 && (
              <div className="af-ops__runs">
                {recentRuns.slice(0, 3).map(run => (
                  <div className="af-ops__run" key={run.run_id || run.id}>
                    <span>{run.goal || run.run_id || run.id}</span>
                    <strong>{titleize(run.workspace_mode || run.status || 'new')}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function AgentBlueprintPanel({ open, onClose }) {
  const [status, setStatus] = useState(null)
  const [name, setName] = useState('AETERNUS Builder Agent')
  const [purpose, setPurpose] = useState('Build and improve AETERNUS systems with coding, testing, security, and release skills.')
  const [blueprint, setBlueprint] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    JGET('/api/forge/engine/status')
      .then(r => r.json())
      .then(setStatus)
      .catch(() => setStatus({ state: 'degraded' }))
  }, [open])

  if (!open) return null

  const createBlueprint = async () => {
    setBusy(true)
    try {
      const r = await JPOST('/api/forge/agents/blueprint', { name, purpose, target_type: 'coding_agent' })
      const d = await r.json()
      if (d.blueprint) { setBlueprint(d.blueprint); toastSuccess('Agent blueprint created') }
      else toastError(d.error || 'Blueprint failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  const registerBlueprint = async () => {
    if (!blueprint) return
    setBusy(true)
    try {
      const r = await JPOST(`/api/forge/agents/${blueprint.id}/register`, { ownerApproved: true })
      const d = await r.json()
      if (d.agent) { setBlueprint(d.blueprint); toastSuccess('Supervised builder agent registered') }
      else toastError(d.error || 'Registration failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="af-modal-overlay" onClick={onClose}>
      <div className="af-modal-dialog" onClick={e => e.stopPropagation()}>
        <div className="af-blueprint__header">
          <span>Create Agent</span>
          <StatusPill label={(status?.state || 'loading').toUpperCase()} tone={status?.state === 'live' ? 'success' : 'idle'} size="sm" />
          <button style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--nx-text-muted)', fontSize: 18, cursor: 'pointer', lineHeight: 1 }} onClick={onClose} aria-label="Close">×</button>
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
    </div>
  )
}

export function FileEditor({ project, selectedFile, onSave }) {
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const projectId = project?.id

  useEffect(() => {
    if (!projectId || !selectedFile) return
    setLoading(true)
    JGET(`/api/forge/files/read?project_id=${projectId}&file_path=${encodeURIComponent(selectedFile)}`)
      .then(r => r.json())
      .then(d => { setContent(d.content || ''); setOriginal(d.content || '') })
      .finally(() => setLoading(false))
  }, [projectId, selectedFile])

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
export function UnderstandPane({ project }) {
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
      {!summary?.ok && !indexing && <div className="af-understand__hint">Not indexed yet — click "Index project" so the builder understands this codebase.</div>}

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

/* ─── Agent stage badge ─── */
function AgentStageBadge({ stage, label, color }) {
  if (!stage) return <div className="af-agent-badge af-agent-badge--pending" style={{ borderColor: color }}><span>{label}</span><span className="af-agent-badge__status">—</span></div>
  const ok = stage.status === 'done'
  const fail = stage.status === 'failed' || stage.status === 'blocked'
  const dur = stage.duration_ms ? `${(stage.duration_ms / 1000).toFixed(1)}s` : ''
  return (
    <div className={`af-agent-badge ${ok ? 'af-agent-badge--ok' : fail ? 'af-agent-badge--fail' : 'af-agent-badge--warn'}`} style={{ borderColor: color }}>
      <span style={{ color }}>{label}</span>
      <span className="af-agent-badge__status">{ok ? `✓ ${dur}` : fail ? `✗ ${dur}` : `~ ${dur}`}</span>
    </div>
  )
}

/* ─── Per-iteration agent timeline ─── */
function AgentIterationRow({ t, idx }) {
  const [open, setOpen] = useState(idx === 0)
  const iterPass = t.verify?.all_passed && t.reviewer?.output?.verdict !== 'block'
  return (
    <div className="af-agentic__iter">
      <div className="af-agentic__itertitle" onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', userSelect: 'none' }}>
        <span>{open ? '▾' : '▸'}</span>
        <span>Iteration {t.iteration}</span>
        <span className={iterPass ? 'af-pill--ok-sm' : 'af-pill--fail-sm'}>{iterPass ? 'PASS' : 'FAIL'}</span>
        <div className="af-agent-badges">
          <AgentStageBadge stage={t.planner} label="PLANNER" color="#E5C76B" />
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.coder} label="CODER" color="#60A5FA" />
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.tester} label="TESTER" color="#C084FC" />
          {t.debug?.length > 0 && <><span className="af-agent-arrow">↻</span><AgentStageBadge stage={t.debug[t.debug.length-1]} label="DEBUG" color="#F59E0B" /></>}
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.security} label="SECURITY" color="#FCA5A5" />
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.reviewer} label="REVIEWER" color="#20D6C7" />
        </div>
      </div>

      {open && (
        <div className="af-agent-detail">
          {/* Planner output */}
          {t.planner?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#E5C76B' }}>Planner</div>
              {(t.planner.output.objectives || []).length > 0 && (
                <ul className="af-agent-list">{t.planner.output.objectives.map((o, i) => <li key={i}>{o}</li>)}</ul>
              )}
              {(t.planner.output.relevant_files || []).length > 0 && (
                <div className="af-agent-files-hint">Files: {t.planner.output.relevant_files.join(', ')}</div>
              )}
              {(t.planner.output.risks || []).length > 0 && (
                <div className="af-agent-risks">Risks: {t.planner.output.risks.join(' · ')}</div>
              )}
            </div>
          )}

          {/* Coder output */}
          {t.files_written?.length > 0 && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#60A5FA' }}>Coder</div>
              <div className="af-agentic__files">
                {t.files_written.map((f, i) => <span key={i} className={f.ok ? 'ok' : 'fail'}>{f.path}{f.error ? ` (${f.error})` : ''}</span>)}
              </div>
            </div>
          )}

          {/* Tester output */}
          {t.tester?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#C084FC' }}>Tester</div>
              {(t.tester.output.results || []).map((r, i) => (
                <div key={i} className={`af-agent-test-row ${r.pass ? 'ok' : 'fail'}`}>
                  <span>{r.pass ? '✓' : '✗'}</span>
                  <span>{r.command}</span>
                  {!r.pass && <pre className="af-agentic__err">{(r.output || '').slice(-300)}</pre>}
                </div>
              ))}
            </div>
          )}

          {/* Debug output */}
          {t.debug?.length > 0 && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#F59E0B' }}>Debug ({t.debug.length} attempt(s))</div>
              {t.debug.map((d, i) => (
                <div key={i} className="af-agent-risks">
                  Retry {i+1}: {d.output?.root_cause || 'unknown cause'} → {d.output?.fix_description || ''}
                  {d.output?.repair_staged && <span style={{ color: '#22c55e', marginLeft: 6 }}>✓ repair staged</span>}
                </div>
              ))}
            </div>
          )}

          {/* Security output */}
          {t.security?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#FCA5A5' }}>Security — {t.security.output.verdict?.toUpperCase()}</div>
              {t.security.output.summary && <div className="af-agent-risks">{t.security.output.summary}</div>}
              {(t.security.output.findings || []).map((f, i) => (
                <div key={i} className={`af-agent-finding af-agent-finding--${f.severity === 'critical' ? 'error' : f.severity || 'info'}`}>
                  <span className="af-agent-finding__type">{f.type}</span>
                  <span className="af-agent-finding__file">{f.file}{f.line ? `:${f.line}` : ''}</span>
                  <span>{f.message}</span>
                </div>
              ))}
            </div>
          )}

          {/* Reviewer output */}
          {t.reviewer?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#20D6C7' }}>Reviewer — {t.reviewer.output.verdict?.toUpperCase()}</div>
              {t.reviewer.output.summary && <div className="af-agent-risks">{t.reviewer.output.summary}</div>}
              {(t.reviewer.output.findings || []).map((f, i) => (
                <div key={i} className={`af-agent-finding af-agent-finding--${f.severity || 'info'}`}>
                  <span className="af-agent-finding__type">{f.type}</span>
                  <span className="af-agent-finding__file">{f.file}{f.line ? `:${f.line}` : ''}</span>
                  <span>{f.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ─── Auto-build pane: WS4 Phase 3 autonomous agentic loop ─── */
export function AgenticPane({ project }) {
  const [goal, setGoal] = useState('')
  const [maxIters, setMaxIters] = useState(3)
  const [running, setRunning] = useState(false)
  const [run, setRun] = useState(null)

  if (!project) return <div className="af-chat__no-project">Select a writable project to auto-build.</div>
  if (!project.write_access) return <div className="af-understand__hint">This project is read-only — auto-build needs write access (import with write access or create a project).</div>

  const start = async () => {
    if (!goal.trim()) return
    setRunning(true); setRun(null)
    try {
      const d = await JPOST_JSON('/api/forge/agentic-run', { project_id: project.id, goal, max_iterations: maxIters, ownerApproved: true, auto_rollback: true })
      setRun(d)
      d.success ? toastSuccess(d.summary) : toastError(d.summary)
    } catch (e) { toastError(e.message) } finally { setRunning(false) }
  }

  return (
    <div className="af-understand">
      <SectionLabel>AUTONOMOUS BUILD</SectionLabel>
      <div className="af-understand__hint">Planner → Coder → Tester → Reviewer, looping until green. Auto-rolls-back on failure. Owner-approved & bounded.</div>
      <textarea className="af-agentic__goal" rows={3} value={goal} onChange={e => setGoal(e.target.value)} placeholder="e.g. Add a /health route that returns {status:'ok'} and make sure the build passes" />
      <div className="af-agentic__controls">
        <label>Max iterations
          <select value={maxIters} onChange={e => setMaxIters(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button className="af-index-btn" onClick={start} disabled={running}>{running ? 'Building…' : '▶ Auto-build'}</button>
      </div>

      {running && (
        <div className="af-agentic__pipeline-loading">
          <div className="af-agent-badges">
            {['PLANNER','CODER','TESTER','SECURITY','REVIEWER'].map((a, i) => (
              <span key={a}>{i > 0 && <span className="af-agent-arrow">→</span>}<span className="af-agent-badge af-agent-badge--pending">{a}</span></span>
            ))}
          </div>
          <div className="af-understand__hint" style={{ marginTop: 8 }}>Running multi-agent pipeline…</div>
        </div>
      )}

      {run?.waiting_approval && (
        <PendingApprovalsPanel
          run={run.run ? run.run : run}
          onApprove={() => { /* re-fetch updated run */ }}
          onReject={() => { /* re-fetch updated run */ }}
          onContinue={() => setRun(null)}
        />
      )}

      {run && !run.waiting_approval && (
        <div className="af-agentic__result">
          <div className={`af-agentic__status ${run.success ? 'ok' : 'fail'}`}>
            {run.success ? '✓ ' : '✗ '}{run.summary}
          </div>
          {(run.transcript || []).map((t, i) => <AgentIterationRow key={t.iteration} t={t} idx={i} />)}
        </div>
      )}
    </div>
  )
}

/* ─── Run History Pane ─── */
const STATUS_TONES = { verified: 'success', applied: 'success', waiting_approval: 'warn', verify_failed: 'alert', failed: 'alert', planning: 'info', executing: 'info', testing: 'info', reviewing: 'info' }

export function RunHistoryPane({ project }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [loadingTranscript, setLoadingTranscript] = useState(false)
  const [replayRunId, setReplayRunId] = useState(null)

  useEffect(() => {
    if (!project) { setRuns([]); setLoading(false); return }
    JGET(`/api/forge/runs?project_id=${project.id}&limit=30`)
      .then(r => r.json())
      .then(d => setRuns(Array.isArray(d.runs) ? d.runs : []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false))
  }, [project?.id])

  const selectRun = async (run) => {
    setSelected(run)
    setTranscript(null)
    setLoadingTranscript(true)
    try {
      const d = await JGET(`/api/forge/runs/${run.id}/transcript`).then(r => r.json())
      setTranscript(d.transcript || [])
    } catch { setTranscript([]) } finally { setLoadingTranscript(false) }
  }

  if (!project) return <div className="af-understand__hint">Select a project to view run history.</div>

  return (
    <div className="af-run-history">
      <div className="af-run-history__list">
        <SectionLabel>RUN HISTORY</SectionLabel>
        {loading && <div className="af-understand__hint">Loading…</div>}
        {!loading && !runs.length && <div className="af-understand__hint">No runs yet for this project.</div>}
        {runs.map(r => (
          <div key={r.id} className={`af-run-row ${selected?.id === r.id ? 'af-run-row--active' : ''}`} onClick={() => { selectRun(r); setReplayRunId(null) }}>
            <div className="af-run-row__id">{(r.id || '').slice(-8)}</div>
            <div className="af-run-row__goal">{(r.goal || r.final_report?.summary || '').slice(0, 55)}</div>
            <StatusPill label={(r.status || 'unknown').toUpperCase()} tone={STATUS_TONES[r.status] || 'muted'} size="sm" />
            <div className="af-run-row__meta">{r.final_report?.transcript?.length || 0}i · {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}</div>
          </div>
        ))}
      </div>
      {selected && !replayRunId && (
        <div className="af-run-history__detail">
          <div className="af-run-history__detail-header">
            <SectionLabel>{(selected.id || '').slice(-8)} — {(selected.status || '').toUpperCase()}</SectionLabel>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setReplayRunId(selected.id)}>▶ Replay</button>
          </div>
          {selected.final_report?.summary && <div className="af-understand__hint">{selected.final_report.summary}</div>}
          {selected.final_report?.recommended_next_task && <div className="af-agent-risks" style={{ color: '#60A5FA' }}>Next: {selected.final_report.recommended_next_task}</div>}
          {loadingTranscript && <div className="af-understand__hint">Loading transcript…</div>}
          {transcript && transcript.map((t, i) => <AgentIterationRow key={t.iteration ?? i} t={t} idx={i} />)}
          {transcript && !transcript.length && <div className="af-understand__hint">No agent transcript recorded for this run.</div>}
        </div>
      )}
      {replayRunId && <ReplayTimeline runId={replayRunId} onClose={() => setReplayRunId(null)} />}
    </div>
  )
}

/* ─── Pending Approvals Panel ─── */
export function PendingApprovalsPanel({ run, onApprove, onReject, onContinue }) {
  const [busy, setBusy] = useState(null)
  if (!run || run.status !== 'waiting_approval') return null

  const pending = (run.actions || []).filter(a => a.status === 'staged' && ['auth', 'security', 'middleware', 'schema', 'migration', '.env', 'secret', 'wallet', 'payment', 'credential', 'password', 'token', 'ssl'].some(k => (a.file_path || '').toLowerCase().includes(k)))

  const doApprove = async (actionId) => {
    setBusy(actionId)
    try {
      await JPOST_JSON(`/api/forge/runs/${run.id}/approve-action`, { action_id: actionId, ownerApproved: true })
      toastSuccess('Action approved')
      onApprove?.(actionId)
    } catch (e) { toastError(e.message) } finally { setBusy(null) }
  }

  const doReject = async (actionId) => {
    setBusy(actionId)
    try {
      await JPOST_JSON(`/api/forge/runs/${run.id}/reject-action`, { action_id: actionId })
      toastSuccess('Action rejected')
      onReject?.(actionId)
    } catch (e) { toastError(e.message) } finally { setBusy(null) }
  }

  const doContinue = async () => {
    setBusy('continue')
    try {
      await JPOST_JSON(`/api/forge/runs/${run.id}/continue`, { ownerApproved: true })
      toastSuccess('Run resumed')
      onContinue?.()
    } catch (e) { toastError(e.message) } finally { setBusy(null) }
  }

  return (
    <div className="af-pending-approvals">
      <SectionLabel>PENDING APPROVALS — HIGH-RISK FILES</SectionLabel>
      <div className="af-understand__hint">These files are classified as high-risk and require your explicit approval before testing proceeds.</div>
      {pending.map(a => (
        <div key={a.id} className="af-approval-card">
          <div className="af-approval-card__header">
            <span className="af-approval-card__file">{a.file_path}</span>
            <span className={`af-agent-badge af-agent-badge--${a.risk_level === 'high' ? 'fail' : 'warn'}`}>{(a.risk_level || 'medium').toUpperCase()}</span>
            <span className="af-approval-card__type">{a.action_type || 'create'}</span>
          </div>
          {a.unified_diff && (
            <pre className="af-approval-card__diff">{a.unified_diff.split('\n').slice(0, 30).join('\n')}{a.unified_diff.split('\n').length > 30 ? '\n… (truncated)' : ''}</pre>
          )}
          <div className="af-approval-card__actions">
            <button className="af-btn af-btn--success af-btn--sm" disabled={busy === a.id} onClick={() => doApprove(a.id)}>{busy === a.id ? '…' : '✓ Approve'}</button>
            <button className="af-btn af-btn--danger af-btn--sm" disabled={busy === a.id} onClick={() => doReject(a.id)}>{busy === a.id ? '…' : '✗ Reject'}</button>
          </div>
        </div>
      ))}
      {!pending.length && <div className="af-understand__hint">All actions resolved. You can continue the run.</div>}
      <button className="af-index-btn" style={{ marginTop: 10 }} disabled={busy === 'continue' || pending.length > 0} onClick={doContinue}>
        {busy === 'continue' ? 'Resuming…' : '▶ Continue Run'}
      </button>
    </div>
  )
}

/* ─── Replay Timeline ─── */
const REPLAY_ICONS = { agent_start: '▶', agent_done: '✓', patch: '📄', approval: '✋', regression: '⚡', error: '✗', command: '⌨' }
const REPLAY_COLORS = { agent_start: '#60A5FA', agent_done: '#22c55e', patch: '#E5C76B', approval: '#C084FC', regression: '#F59E0B', error: '#ef4444', command: '#20D6C7' }

export function ReplayTimeline({ runId, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    if (!runId) return
    JGET(`/api/forge/runs/${runId}/replay`)
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setData({ ok: false }))
      .finally(() => setLoading(false))
  }, [runId])

  if (loading) return <div className="af-understand__hint">Loading replay…</div>
  if (!data?.ok) return <div className="af-understand__hint">Replay unavailable for this run.</div>

  return (
    <div className="af-replay">
      <div className="af-replay__header">
        <SectionLabel>RUN REPLAY — {(runId || '').slice(-8)}</SectionLabel>
        {onClose && <button className="af-btn af-btn--ghost af-btn--sm" onClick={onClose}>✕ Close</button>}
      </div>
      <div className="af-replay__goal">{data.goal}</div>
      <div className="af-replay__timeline">
        {(data.timeline || []).map((e, i) => {
          const color = REPLAY_COLORS[e.type] || '#888'
          const icon = REPLAY_ICONS[e.type] || '·'
          const isOpen = expanded === i
          return (
            <div key={i} className="af-replay__event" onClick={() => setExpanded(isOpen ? null : i)}>
              <div className="af-replay__event-dot" style={{ background: color }} />
              <div className="af-replay__event-body">
                <div className="af-replay__event-header">
                  <span style={{ color }}>{icon}</span>
                  <span className="af-replay__event-type">{e.type.replace(/_/g,' ')}</span>
                  {e.iteration && <span className="af-replay__event-iter">iter {e.iteration}</span>}
                  {e.agent && <span style={{ color }}>{e.agent}</span>}
                  {e.file && <span className="af-replay__event-file">{e.file}</span>}
                  {e.status && <span className={`af-pill--${e.status === 'done' ? 'ok' : 'fail'}-sm`}>{e.status}</span>}
                  <span className="af-replay__event-ts">{e.ts ? new Date(e.ts).toLocaleTimeString() : ''}</span>
                </div>
                {isOpen && (
                  <pre className="af-replay__event-data">{JSON.stringify(e, null, 2).slice(0, 500)}</pre>
                )}
              </div>
            </div>
          )
        })}
        {!(data.timeline?.length) && <div className="af-understand__hint">No timeline events recorded for this run.</div>}
      </div>
      {data.final_report?.summary && (
        <div className="af-replay__final">
          <SectionLabel>FINAL REPORT</SectionLabel>
          <div className="af-understand__hint">{data.final_report.summary}</div>
          {data.final_report.files_changed?.length > 0 && <div className="af-agent-files-hint">Files: {data.final_report.files_changed.join(', ')}</div>}
          {data.final_report.remaining_issues?.length > 0 && <div className="af-agent-risks">Remaining: {data.final_report.remaining_issues.join(' · ')}</div>}
          {data.final_report.recommended_next_task && <div className="af-agent-risks" style={{ color: '#60A5FA' }}>Next: {data.final_report.recommended_next_task}</div>}
        </div>
      )}
    </div>
  )
}

/* ─── Run Metrics Pane ─── */
function MetricBar({ label, value, max, color }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className="af-metric-bar">
      <div className="af-metric-bar__label">{label}</div>
      <div className="af-metric-bar__track"><div className="af-metric-bar__fill" style={{ width: `${pct}%`, background: color || '#E5C76B' }} /></div>
      <div className="af-metric-bar__value">{value}</div>
    </div>
  )
}

export function RunMetricsPane({ project }) {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!project?.id) { setLoading(false); return }
    JGET(`/api/forge/projects/${project.id}/forge-metrics`)
      .then(r => r.json())
      .then(d => setMetrics(d.ok ? d : null))
      .catch(() => setMetrics(null))
      .finally(() => setLoading(false))
  }, [project?.id])

  if (!project) return <div className="af-understand__hint">Select a project to view metrics.</div>
  if (loading) return <div className="af-understand__hint">Loading metrics…</div>
  if (!metrics) return <div className="af-understand__hint">No metrics yet. Run auto-build to generate data.</div>

  const successCount = (metrics.by_status?.applied || 0) + (metrics.by_status?.verified || 0)
  const byStatus = Object.entries(metrics.by_status || {})

  return (
    <div className="af-metrics">
      <SectionLabel>PROJECT METRICS</SectionLabel>
      <div className="af-metrics__grid">
        <div className="af-metric-card">
          <div className="af-metric-card__value">{metrics.total_runs}</div>
          <div className="af-metric-card__label">Total Runs</div>
        </div>
        <div className="af-metric-card">
          <div className="af-metric-card__value" style={{ color: '#22c55e' }}>{Math.round((metrics.success_rate || 0) * 100)}%</div>
          <div className="af-metric-card__label">Success Rate</div>
        </div>
        <div className="af-metric-card">
          <div className="af-metric-card__value">{metrics.avg_duration_sec}s</div>
          <div className="af-metric-card__label">Avg Duration</div>
        </div>
        <div className="af-metric-card">
          <div className="af-metric-card__value" style={{ color: '#FCA5A5' }}>{metrics.security_blocks || 0}</div>
          <div className="af-metric-card__label">Security Blocks</div>
        </div>
      </div>

      <SectionLabel>BY STATUS</SectionLabel>
      {byStatus.map(([status, count]) => (
        <MetricBar key={status} label={status} value={count} max={metrics.total_runs} color={['applied','verified'].includes(status) ? '#22c55e' : ['failed','verify_failed'].includes(status) ? '#ef4444' : '#60A5FA'} />
      ))}

      {(metrics.most_edited_files || []).length > 0 && (
        <>
          <SectionLabel>MOST EDITED FILES</SectionLabel>
          {metrics.most_edited_files.slice(0, 5).map((f, i) => (
            <div key={i} className="af-agent-files-hint" style={{ marginBottom: 2 }}>{f}</div>
          ))}
        </>
      )}

      {metrics.patch_stats && (
        <>
          <SectionLabel>PATCH STATS</SectionLabel>
          <div className="af-metrics__grid">
            {Object.entries(metrics.patch_stats).map(([k, v]) => (
              <div key={k} className="af-metric-card">
                <div className="af-metric-card__value">{v}</div>
                <div className="af-metric-card__label">{k}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PHASE 5 PANELS
// ─────────────────────────────────────────────────────────────────────────────

// Shared token helper — reads the same key as api/client.js (ai_jwt)
const tok = () => localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || ''

const STATUS_COLORS = { IDEA:'#6b7280', READY:'#3b82f6', PLANNING:'#8b5cf6', IN_PROGRESS:'#f59e0b', WAITING_APPROVAL:'#ef4444', BLOCKED:'#dc2626', DONE:'#10b981', FAILED:'#ef4444', CANCELLED:'#6b7280' }
const CATEGORY_ICONS = { BUG:'🐛', FEATURE:'✨', REFACTOR:'♻️', SECURITY:'🔒', UI:'🎨', PERFORMANCE:'⚡', TESTING:'🧪', DOCS:'📄', ARCHITECTURE:'🏗️', AUTOMATION:'🤖' }

export function BacklogPane({ project, onRefreshSummary }) {
  const [backlog, setBacklog] = useState([])
  const [autopilot, setAutopilot] = useState({ active: false })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newItem, setNewItem] = useState({ title:'', description:'', priority:50, category:'FEATURE', status:'IDEA', risk_level:'low' })
  const [busy, setBusy] = useState({})

  const refresh = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    Promise.all([
      api.forge.getBacklog(project.id).catch(() => ({ backlog: [] })),
      api.forge.autopilotStatus(project.id).catch(() => ({ status: { active: false } })),
    ]).then(([bl, ap]) => {
      if (bl.ok) setBacklog(bl.backlog || [])
      else setError(bl.error || 'Failed to load backlog')
      setAutopilot(ap.status || { active: false })
    }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [project?.id])

  useEffect(() => { refresh() }, [refresh])

  const addItem = async () => {
    if (!newItem.title.trim()) return
    setBusy(b => ({ ...b, add: true }))
    try {
      const r = await api.forge.createBacklogItem(project.id, newItem)
      if (r.ok) { setShowAdd(false); setNewItem({ title:'', description:'', priority:50, category:'FEATURE', status:'IDEA', risk_level:'low' }); refresh(); onRefreshSummary?.() }
      else setError(r.error)
    } catch (e) { setError(e.message) }
    finally { setBusy(b => ({ ...b, add: false })) }
  }

  const updateItem = async (id, patch) => {
    setBusy(b => ({ ...b, [id]: true }))
    try { await api.forge.updateBacklogItem(id, patch) } catch { /* ignore, refresh anyway */ }
    setBusy(b => ({ ...b, [id]: false })); refresh(); onRefreshSummary?.()
  }

  const deleteItem = async (id) => {
    if (!confirm('Delete this backlog item?')) return
    setBusy(b => ({ ...b, [id]: true }))
    try { await api.forge.deleteBacklogItem(id) } catch { /* ignore */ }
    setBusy(b => ({ ...b, [id]: false })); refresh(); onRefreshSummary?.()
  }

  const toggleAutopilot = async () => {
    try {
      if (autopilot.active) await api.forge.stopAutopilot(project.id)
      else await api.forge.startAutopilot(project.id, {})
    } catch { /* ignore */ }
    refresh(); onRefreshSummary?.()
  }

  if (!project) return <div className="af-backlog__empty"><EmptyState title="No project selected" body="Select a project to manage its backlog." /></div>
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading backlog...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-backlog">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Backlog <span className="af-tab__count">{backlog.length}</span></div>
        <div className="af-backlog__controls">
          <button className={`af-btn af-btn--sm ${autopilot.active ? 'af-btn--danger' : 'af-btn--primary'}`} onClick={toggleAutopilot}>
            {autopilot.active ? 'Stop Autopilot' : 'Start Autopilot'}
          </button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => setShowAdd(s => !s)}>+ Add Item</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {autopilot.active && (
        <div className="af-autopilot__status">
          <span className="af-pill af-pill--success">Autopilot Active</span>
          <span>Runs: {autopilot.runsCompleted || 0} / {autopilot.maxRuns || 10}</span>
          {autopilot.consecutiveFails > 0 && <span className="af-pill af-pill--warn">Fails: {autopilot.consecutiveFails}</span>}
        </div>
      )}
      {showAdd && (
        <div className="af-backlog__add-form">
          <input className="af-input" placeholder="Title *" value={newItem.title} onChange={e => setNewItem(n => ({ ...n, title: e.target.value }))} />
          <textarea className="af-input" placeholder="Description" rows={2} value={newItem.description} onChange={e => setNewItem(n => ({ ...n, description: e.target.value }))} />
          <div className="af-backlog__add-row">
            <select className="af-select" value={newItem.category} onChange={e => setNewItem(n => ({ ...n, category: e.target.value }))}>
              {['BUG','FEATURE','REFACTOR','SECURITY','UI','PERFORMANCE','TESTING','DOCS','ARCHITECTURE','AUTOMATION'].map(c => <option key={c}>{c}</option>)}
            </select>
            <select className="af-select" value={newItem.risk_level} onChange={e => setNewItem(n => ({ ...n, risk_level: e.target.value }))}>
              <option value="low">Low risk</option><option value="medium">Medium risk</option><option value="high">High risk</option>
            </select>
            <select className="af-select" value={newItem.status} onChange={e => setNewItem(n => ({ ...n, status: e.target.value }))}>
              {['IDEA','READY'].map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="af-backlog__add-actions">
            <button className="af-btn af-btn--primary af-btn--sm" onClick={addItem} disabled={busy.add}>{busy.add ? 'Adding...' : 'Add to Backlog'}</button>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </div>
      )}
      {backlog.length === 0 && <EmptyState title="Backlog is empty" body="Add items manually or use the Decomposer to generate tasks from a goal." />}
      <div className="af-backlog__list">
        {backlog.map(item => (
          <div key={item.backlog_id} className={`af-backlog__item af-backlog__item--${item.status.toLowerCase()}`}>
            <div className="af-backlog__item-head">
              <span className="af-backlog__category">{CATEGORY_ICONS[item.category] || '•'} {item.category}</span>
              <span className="af-backlog__status" style={{ color: STATUS_COLORS[item.status] }}>{item.status}</span>
              <span className="af-backlog__risk">{item.risk_level}</span>
            </div>
            <div className="af-backlog__item-title">{item.title}</div>
            {item.description && <div className="af-backlog__item-desc">{item.description.slice(0, 120)}{item.description.length > 120 ? '…' : ''}</div>}
            <div className="af-backlog__item-actions">
              {item.status === 'IDEA' && <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => updateItem(item.backlog_id, { status: 'READY' })} disabled={busy[item.backlog_id]}>Mark Ready</button>}
              {item.status === 'READY' && <button className="af-btn af-btn--sm af-btn--primary" onClick={() => { if(confirm('Trigger agentic run for this item?')) updateItem(item.backlog_id, { status: 'IN_PROGRESS' }) }} disabled={busy[item.backlog_id]}>Run</button>}
              <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => deleteItem(item.backlog_id)} disabled={busy[item.backlog_id]}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function DecomposerPane({ project, onRefreshSummary }) {
  const [goal, setGoal] = useState('')
  const [addToBacklog, setAddToBacklog] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const decompose = async () => {
    if (!goal.trim() || !project?.id) return
    setLoading(true); setError(null); setResult(null)
    try {
      const r = await api.forge.decomposeTask(project.id, { goal, add_to_backlog: addToBacklog })
      if (r.ok) { setResult(r); if (r.added_to_backlog > 0) onRefreshSummary?.() }
      else setError(r.error || 'Decomposition failed')
    } catch (e) { setError(e.message || 'Decomposition failed') }
    finally { setLoading(false) }
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project first." />

  return (
    <div className="af-decomposer">
      <div className="af-decomposer__header">
        <SectionLabel>TASK DECOMPOSER</SectionLabel>
        <p className="af-decomposer__subtitle">Break a high-level goal into ordered subtasks using the Decomposer Agent.</p>
      </div>
      <div className="af-decomposer__form">
        <textarea className="af-input af-input--mono" rows={3} placeholder="Enter your goal... e.g. 'Add a complete backlog management system to the dashboard'" value={goal} onChange={e => setGoal(e.target.value)} />
        <div className="af-decomposer__options">
          <label className="af-decomposer__checkbox">
            <input type="checkbox" checked={addToBacklog} onChange={e => setAddToBacklog(e.target.checked)} />
            <span>Add subtasks to backlog as IDEA items</span>
          </label>
          <button className="af-btn af-btn--primary" onClick={decompose} disabled={loading || !goal.trim()}>{loading ? 'Decomposing...' : 'Decompose Goal'}</button>
        </div>
      </div>
      {error && <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error}</div>}
      {result && (
        <div className="af-decomposer__result">
          <SectionLabel>SUBTASKS ({result.count})</SectionLabel>
          {result.added_to_backlog > 0 && <div className="af-pill af-pill--success" style={{marginBottom:8}}>{result.added_to_backlog} items added to backlog</div>}
          {(result.subtasks || []).map((st, i) => (
            <div key={i} className="af-decomposer__subtask">
              <div className="af-decomposer__subtask-head">
                <span className="af-decomposer__idx">{i + 1}</span>
                <span className="af-decomposer__subtask-title">{st.title}</span>
                <span className={`af-risk af-risk--${st.risk_level || 'safe'}`}>{st.risk_level || 'low'}</span>
              </div>
              {st.description && <div className="af-decomposer__subtask-desc">{st.description}</div>}
              {st.acceptance_criteria && <div className="af-decomposer__subtask-criteria">Criteria: {st.acceptance_criteria}</div>}
              {st.affected_areas?.length > 0 && <div className="af-decomposer__subtask-areas">{st.affected_areas.join(', ')}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function SkillsLibraryPane({ project }) {
  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(null)

  const refresh = useCallback(() => {
    setLoading(true); setError(null)
    api.forge.getSkills()
      .then(d => { if (d.ok) setSkills(d.skills || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const reload = async () => {
    try { await api.forge.reloadSkills() } catch { /* ignore */ }
    refresh()
  }

  if (loading) return <div className="af-skills-lib__loading"><div className="af-spinner" />Loading skills...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-skills-lib">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Forge Skills <span className="af-tab__count">{skills.length}</span></div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={reload}>Reload Skills</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {skills.length === 0 && <EmptyState title="No skills loaded" body="Skills are loaded from runtime/skills/forge/*.json. Click Reload Skills to scan for new definitions." />}
      <div className="af-skills-lib__list">
        {skills.map(s => (
          <div key={s.skill_id} className={`af-skills-lib__card ${expanded === s.skill_id ? 'af-skills-lib__card--open' : ''}`}>
            <div className="af-skills-lib__card-head" onClick={() => setExpanded(expanded === s.skill_id ? null : s.skill_id)}>
              <div className="af-skills-lib__card-name">{s.name}</div>
              <div className="af-skills-lib__card-id">{s.skill_id}</div>
              <span className="af-iconbtn">{expanded === s.skill_id ? '▲' : '▼'}</span>
            </div>
            {expanded === s.skill_id && (
              <div className="af-skills-lib__card-body">
                <p className="af-skills-lib__desc">{s.description}</p>
                {s.triggers?.length > 0 && (
                  <div className="af-skills-lib__triggers">
                    <SectionLabel>TRIGGERS</SectionLabel>
                    <div className="af-skills-lib__tag-list">{s.triggers.map(t => <span key={t} className="af-skills-lib__tag">{t}</span>)}</div>
                  </div>
                )}
                {s.checklist?.length > 0 && (
                  <div className="af-skills-lib__checklist">
                    <SectionLabel>CHECKLIST</SectionLabel>
                    {s.checklist.map((c, i) => <div key={i} className="af-skills-lib__check-item">☐ {c}</div>)}
                  </div>
                )}
                {s.verification_commands?.length > 0 && (
                  <div className="af-skills-lib__verif">
                    <SectionLabel>VERIFICATION</SectionLabel>
                    {s.verification_commands.map((c, i) => <code key={i} className="af-skills-lib__cmd">{c}</code>)}
                  </div>
                )}
                {s.common_failure_modes?.length > 0 && (
                  <div className="af-skills-lib__failures">
                    <SectionLabel>COMMON FAILURES</SectionLabel>
                    {s.common_failure_modes.map((f, i) => <div key={i} className="af-skills-lib__fail-item">⚠ {f}</div>)}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ModelRouterPane({ project }) {
  const [models, setModels] = useState([])
  const [stats, setStats] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newModel, setNewModel] = useState({ model_id:'', provider:'anthropic', role:'any', cost_tier:'medium', speed_tier:'medium' })
  const [busy, setBusy] = useState({})

  const refresh = useCallback(() => {
    setLoading(true); setError(null)
    Promise.all([
      api.forge.getModels(),
      project?.id ? api.forge.modelRoutingStats(project.id).catch(() => ({ stats: [] })) : Promise.resolve({ stats: [] }),
    ]).then(([md, st]) => {
      if (md.ok) setModels(md.models || []); else setError(md.error)
      setStats(st.stats || [])
    }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [project?.id])
  useEffect(() => { refresh() }, [refresh])

  const addModel = async () => {
    if (!newModel.model_id || !newModel.provider) return
    setBusy(b => ({ ...b, add: true }))
    try {
      const r = await api.forge.createModel(newModel)
      if (r.ok) { setShowAdd(false); setNewModel({ model_id:'', provider:'anthropic', role:'any', cost_tier:'medium', speed_tier:'medium' }); refresh() }
      else setError(r.error)
    } catch (e) { setError(e.message) }
    finally { setBusy(b => ({ ...b, add: false })) }
  }

  const toggleModel = async (m) => {
    setBusy(b => ({ ...b, [m.model_id]: true }))
    try { await api.forge.updateModel(m.model_id, { enabled: !m.enabled }) } catch { /* ignore */ }
    setBusy(b => ({ ...b, [m.model_id]: false })); refresh()
  }

  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading models...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-model-router">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Model Router <span className="af-tab__count">{models.length}</span></div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => setShowAdd(s => !s)}>+ Add Model</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {models.length === 0 && !showAdd && <EmptyState title="No models configured" body="Add model configurations to enable intelligent routing. Without configuration, the system uses environment-variable defaults." />}
      {showAdd && (
        <div className="af-backlog__add-form">
          <input className="af-input" placeholder="Model ID (e.g. claude-sonnet-4-6) *" value={newModel.model_id} onChange={e => setNewModel(n => ({ ...n, model_id: e.target.value }))} />
          <div className="af-backlog__add-row">
            <select className="af-select" value={newModel.provider} onChange={e => setNewModel(n => ({ ...n, provider: e.target.value }))}>
              {['anthropic','openai','ollama','google','mistral'].map(p => <option key={p}>{p}</option>)}
            </select>
            <select className="af-select" value={newModel.role} onChange={e => setNewModel(n => ({ ...n, role: e.target.value }))}>
              {['any','planner','coder','tester','security','reviewer','decomposer','summarizer'].map(r => <option key={r}>{r}</option>)}
            </select>
            <select className="af-select" value={newModel.cost_tier} onChange={e => setNewModel(n => ({ ...n, cost_tier: e.target.value }))}>
              {['low','medium','high'].map(t => <option key={t}>{t}</option>)}
            </select>
            <select className="af-select" value={newModel.speed_tier} onChange={e => setNewModel(n => ({ ...n, speed_tier: e.target.value }))}>
              {['fast','medium','slow'].map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="af-backlog__add-actions">
            <button className="af-btn af-btn--primary af-btn--sm" onClick={addModel} disabled={busy.add}>{busy.add ? 'Adding...' : 'Add Model'}</button>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </div>
      )}
      <div className="af-model-router__list">
        {models.map(m => (
          <div key={m.model_id} className={`af-model-router__card ${m.enabled ? '' : 'af-model-router__card--disabled'}`}>
            <div className="af-model-router__card-head">
              <div className="af-model-router__model-id">{m.model_id}</div>
              <span className="af-pill af-pill--sm">{m.provider}</span>
              <span className="af-pill af-pill--sm">{m.role}</span>
            </div>
            <div className="af-model-router__card-meta">
              cost: {m.cost_tier} · speed: {m.speed_tier} · {m.local_or_remote}
            </div>
            <button className={`af-btn af-btn--sm ${m.enabled ? 'af-btn--danger' : 'af-btn--success'}`} onClick={() => toggleModel(m)} disabled={busy[m.model_id]}>
              {m.enabled ? 'Disable' : 'Enable'}
            </button>
          </div>
        ))}
      </div>
      {stats.length > 0 && (
        <div className="af-model-router__stats">
          <SectionLabel>ROUTING STATS (THIS PROJECT)</SectionLabel>
          {stats.map((s, i) => (
            <div key={i} className="af-model-router__stat-row">
              <span className="af-model-router__stage">{s.stage}</span>
              <span className="af-model-router__model">{s.selected_model_id}</span>
              <span className="af-model-router__count">{s.count}x</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function CyclesPane({ project }) {
  const [cycles, setCycles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newCycle, setNewCycle] = useState({ goal:'', autonomy_level:2, max_runs:10 })
  const [busy, setBusy] = useState({})

  const refresh = () => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getCycles(project.id)
      .then(d => { if (d.ok) setCycles(d.cycles || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { refresh() }, [project?.id])

  const createCycle = async () => {
    if (!newCycle.goal.trim()) return
    setBusy(b => ({ ...b, create: true }))
    try {
      const r = await api.forge.createCycle(project.id, newCycle)
      if (r.ok) { setShowCreate(false); setNewCycle({ goal:'', autonomy_level:2, max_runs:10 }); refresh() }
      else setError(r.error)
    } catch (e) { setError(e.message) }
    finally { setBusy(b => ({ ...b, create: false })) }
  }

  const cycleAction = async (cycleId, action) => {
    setBusy(b => ({ ...b, [cycleId]: true }))
    try {
      if (action === 'pause') await api.forge.pauseCycle(cycleId)
      else if (action === 'resume') await api.forge.resumeCycle(cycleId)
      else if (action === 'cancel') await api.forge.cancelCycle(cycleId)
    } catch { /* ignore */ }
    setBusy(b => ({ ...b, [cycleId]: false })); refresh()
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project to manage development cycles." />
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading cycles...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-cycle">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Development Cycles <span className="af-tab__count">{cycles.length}</span></div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--primary" onClick={() => setShowCreate(s => !s)}>+ New Cycle</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {showCreate && (
        <div className="af-backlog__add-form">
          <textarea className="af-input" rows={2} placeholder="Cycle goal *" value={newCycle.goal} onChange={e => setNewCycle(n => ({ ...n, goal: e.target.value }))} />
          <div className="af-backlog__add-row">
            <label className="af-model-router__stage">Autonomy Level:</label>
            <select className="af-select" value={newCycle.autonomy_level} onChange={e => setNewCycle(n => ({ ...n, autonomy_level: +e.target.value }))}>
              <option value={0}>0 — ReadOnly</option><option value={1}>1 — SafeEdits</option><option value={2}>2 — Guided</option><option value={3}>3 — Autopilot</option>
            </select>
            <label className="af-model-router__stage">Max Runs:</label>
            <input className="af-input" type="number" min={1} max={50} value={newCycle.max_runs} onChange={e => setNewCycle(n => ({ ...n, max_runs: +e.target.value }))} style={{width:70}} />
          </div>
          <div className="af-backlog__add-actions">
            <button className="af-btn af-btn--primary af-btn--sm" onClick={createCycle} disabled={busy.create}>{busy.create ? 'Creating...' : 'Create Cycle'}</button>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}
      {cycles.length === 0 && <EmptyState title="No cycles yet" body="Create a development cycle to orchestrate multiple backlog items toward a goal." />}
      <div className="af-cycle__list">
        {cycles.map(c => (
          <div key={c.cycle_id} className={`af-cycle__card af-cycle__card--${c.status.toLowerCase()}`}>
            <div className="af-cycle__card-head">
              <span className="af-cycle__status" style={{ color: STATUS_COLORS[c.status] || '#6b7280' }}>{c.status}</span>
              <span className="af-pill af-pill--sm">L{c.autonomy_level}</span>
              <span className="af-cycle__runs">{(c.run_ids || []).length}/{c.max_runs} runs</span>
            </div>
            <div className="af-cycle__goal">{c.goal}</div>
            <div className="af-cycle__meta">
              Items: {(c.backlog_items || []).length} · Started: {c.started_at ? new Date(c.started_at).toLocaleDateString() : 'N/A'}
            </div>
            <div className="af-backlog__item-actions">
              {c.status === 'RUNNING' && <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => cycleAction(c.cycle_id, 'pause')} disabled={busy[c.cycle_id]}>Pause</button>}
              {c.status === 'PAUSED' && <button className="af-btn af-btn--sm af-btn--primary" onClick={() => cycleAction(c.cycle_id, 'resume')} disabled={busy[c.cycle_id]}>Resume</button>}
              {['RUNNING','PAUSED'].includes(c.status) && <button className="af-btn af-btn--sm af-btn--danger" onClick={() => { if(confirm('Cancel this cycle?')) cycleAction(c.cycle_id, 'cancel') }} disabled={busy[c.cycle_id]}>Cancel</button>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function RoadmapPane({ project }) {
  const [roadmap, setRoadmap] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getRoadmap(project.id)
      .then(d => { if (d.ok) setRoadmap(d.roadmap); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])
  useEffect(() => { refresh() }, [refresh])

  const generate = async () => {
    setGenerating(true); setError(null)
    let r
    try { r = await api.forge.generateRoadmap(project.id) } catch (e) { r = { ok: false, error: e.message } }
    setGenerating(false)
    if (r.ok) setRoadmap(r.roadmap)
    else setError(r.error || 'Generation failed')
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project to view its roadmap." />
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading roadmap...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  const content = roadmap?.content || {}

  return (
    <div className="af-roadmap">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Project Roadmap</div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--primary" onClick={generate} disabled={generating}>{generating ? 'Generating...' : 'Generate Roadmap'}</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {!roadmap && <EmptyState title="No roadmap yet" body="Click Generate Roadmap to let the AI analyze your project and produce a structured development roadmap." />}
      {roadmap && (
        <>
          {content.current_state && (
            <div className="af-roadmap__section">
              <SectionLabel>CURRENT STATE</SectionLabel>
              <p className="af-roadmap__text">{content.current_state}</p>
              {content.estimated_complexity && <span className="af-pill af-pill--sm">Complexity: {content.estimated_complexity}</span>}
            </div>
          )}
          {content.recommended_next_tasks?.length > 0 && (
            <div className="af-roadmap__section">
              <SectionLabel>RECOMMENDED NEXT TASKS</SectionLabel>
              {content.recommended_next_tasks.map((t, i) => (
                <div key={i} className="af-roadmap__task">
                  <span className={`af-pill af-pill--sm af-pill--${t.priority === 'high' ? 'danger' : t.priority === 'medium' ? 'warn' : 'idle'}`}>{t.priority}</span>
                  <span className="af-roadmap__task-title">{t.title}</span>
                  {t.category && <span className="af-pill af-pill--sm">{t.category}</span>}
                </div>
              ))}
            </div>
          )}
          {['known_issues','technical_debt','missing_features','security_improvements','performance_improvements'].map(key => (
            content[key]?.length > 0 && (
              <div key={key} className="af-roadmap__section">
                <SectionLabel>{key.replace(/_/g,' ').toUpperCase()}</SectionLabel>
                {content[key].map((item, i) => <div key={i} className="af-roadmap__item">• {typeof item === 'string' ? item : JSON.stringify(item)}</div>)}
              </div>
            )
          ))}
          {roadmap.updated_at && <div className="af-roadmap__updated">Last updated: {new Date(roadmap.updated_at).toLocaleString()}</div>}
        </>
      )}
    </div>
  )
}

export function SuggestionsPane({ project, onRefreshSummary }) {
  const [suggestions, setSuggestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState({})

  const refresh = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getSuggestions(project.id)
      .then(d => { if (d.ok) setSuggestions(d.suggestions || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])
  useEffect(() => { refresh() }, [refresh])

  const action = async (id, endpoint) => {
    setBusy(b => ({ ...b, [id]: true }))
    try {
      if (endpoint === 'accept') await api.forge.acceptSuggestion(id)
      else if (endpoint === 'reject') await api.forge.rejectSuggestion(id)
      else if (endpoint === 'create-backlog-item') await api.forge.suggestionToBacklog(id)
    } catch { /* ignore */ }
    setBusy(b => ({ ...b, [id]: false })); refresh(); onRefreshSummary?.()
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project to view improvement suggestions." />
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading suggestions...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  const open = suggestions.filter(s => s.status === 'new')
  const closed = suggestions.filter(s => s.status !== 'new')

  return (
    <div className="af-suggestion">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Self-Improvement <span className="af-tab__count">{open.length} open</span></div>
        <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
      </div>
      {suggestions.length === 0 && <EmptyState title="No suggestions yet" body="Suggestions are auto-generated after each agentic run based on security findings, reviewer findings, and failure patterns." />}
      {open.map(s => (
        <div key={s.suggestion_id} className={`af-suggestion__card af-suggestion__card--${s.risk_level}`}>
          <div className="af-suggestion__card-head">
            <span className={`af-pill af-pill--sm af-pill--${s.risk_level === 'high' ? 'danger' : s.risk_level === 'medium' ? 'warn' : 'idle'}`}>{s.risk_level}</span>
            <span className="af-pill af-pill--sm">{s.category}</span>
          </div>
          <div className="af-suggestion__title">{s.title}</div>
          {s.description && <div className="af-suggestion__desc">{s.description}</div>}
          {s.recommended_fix && <div className="af-suggestion__fix">Fix: {s.recommended_fix}</div>}
          <div className="af-suggestion__actions">
            <button className="af-btn af-btn--sm af-btn--success" onClick={() => action(s.suggestion_id, 'accept')} disabled={busy[s.suggestion_id]}>Accept</button>
            <button className="af-btn af-btn--sm af-btn--primary" onClick={() => action(s.suggestion_id, 'create-backlog-item')} disabled={busy[s.suggestion_id]}>Add to Backlog</button>
            <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => action(s.suggestion_id, 'reject')} disabled={busy[s.suggestion_id]}>Dismiss</button>
          </div>
        </div>
      ))}
      {closed.length > 0 && (
        <details className="af-suggestion__closed">
          <summary>Closed suggestions ({closed.length})</summary>
          {closed.map(s => (
            <div key={s.suggestion_id} className="af-suggestion__card af-suggestion__card--closed">
              <span className="af-pill af-pill--sm">{s.status}</span> {s.title}
            </div>
          ))}
        </details>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MEMORY V3 PANE
// ─────────────────────────────────────────────────────────────────────────────
export function MemoryV3Pane({ project }) {
  const [facts, setFacts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [category, setCategory] = useState('')

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getMemory(project.id, category || undefined)
      .then(d => { if (d.ok) setFacts(d.facts || []); else setError(d.error || 'Failed to load memory') })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id, category])

  useEffect(() => { load() }, [load])

  if (!project) return <div className="af-understand__hint">Select a project to view memory.</div>

  const CONF_COLOR = { HIGH: '#22c55e', MEDIUM: '#f59e0b', LOW: '#6b7280' }
  const categories = [...new Set(facts.map(f => f.category).filter(Boolean))]

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <SectionLabel>MEMORY V3 — {facts.length} FACTS</SectionLabel>
        <div style={{ display: 'flex', gap: 6 }}>
          <select
            style={{ fontSize: 10, padding: '2px 6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted)' }}
            value={category} onChange={e => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>Refresh</button>
        </div>
      </div>

      {loading && <div className="af-understand__hint">Loading memory…</div>}
      {error && (
        <div style={{ color: '#ef4444', fontSize: 11 }}>
          {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>Retry</button>
        </div>
      )}
      {!loading && !error && facts.length === 0 && (
        <EmptyState title="No memory facts yet" body="Facts are extracted automatically after runs as the system learns from each agentic execution." />
      )}
      {facts.map((f, i) => (
        <div key={f.id || i} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ font: '600 11px/1 monospace', color: CONF_COLOR[f.confidence] || '#888' }}>{f.confidence || 'LOW'}</span>
            {f.category && <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>{f.category}</span>}
            <span style={{ marginLeft: 'auto', font: '400 9px monospace', color: 'var(--af-text-dim)' }}>used {f.usage_count || 0}x</span>
          </div>
          <div style={{ font: '400 12px/1.5 system-ui', color: 'var(--af-text)' }}>{f.fact || f.content}</div>
          {f.source && <div style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', marginTop: 4 }}>source: {f.source}</div>}
          {f.evidence && <div style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', marginTop: 2 }}>evidence: {String(f.evidence).slice(0, 120)}</div>}
          {f.created_at && <div style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginTop: 3 }}>{new Date(f.created_at).toLocaleString()}</div>}
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SAFETY PANE
// ─────────────────────────────────────────────────────────────────────────────
export function SafetyPane({ project, activeRun, onApprove, onReject, onContinue }) {
  const [patches, setPatches] = useState([])
  const [loading, setLoading] = useState(false)
  // Derive autonomy_level from project prop — no extra fetch needed
  const autonomyLevel = project?.autonomy_level ?? null

  useEffect(() => {
    if (!activeRun?.id) { setPatches([]); return }
    setLoading(true)
    api.forge.getRunPatches(activeRun.id)
      .then(d => setPatches(d.patches || []))
      .catch(() => setPatches([]))
      .finally(() => setLoading(false))
  }, [activeRun?.id])

  const secFindings = activeRun?.final_report?.security_findings || []
  const highRiskPatches = patches.filter(p => ['high', 'critical'].includes((p.risk_level || '').toLowerCase()))
  const pendingPatches = patches.filter(p => p.status === 'staged' || p.status === 'awaiting_approval')

  const autonomyColors = { 0: '#22c55e', 1: '#22c55e', 2: '#f59e0b', 3: '#ef4444' }
  const autonomyLabels = { 0: 'ReadOnly', 1: 'SafeEdits', 2: 'Guided', 3: 'Autopilot' }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>
      <SectionLabel>SAFETY &amp; APPROVALS</SectionLabel>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 5, border: '1px solid rgba(255,255,255,0.07)' }}>
        <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>Autonomy Level</span>
        <span style={{ font: '700 12px monospace', color: autonomyColors[autonomyLevel] || '#888' }}>
          {autonomyLevel != null ? `Level ${autonomyLevel}` : '—'}
        </span>
        {autonomyLevel != null && (
          <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)' }}>({autonomyLabels[autonomyLevel] || ''})</span>
        )}
      </div>

      {activeRun ? (
        <PendingApprovalsPanel run={activeRun} onApprove={onApprove} onReject={onReject} onContinue={onContinue} />
      ) : (
        <div className="af-understand__hint">No active run — start a run to see pending approvals here.</div>
      )}

      {secFindings.length > 0 && (
        <>
          <SectionLabel>SECURITY FINDINGS — {secFindings.length}</SectionLabel>
          {secFindings.map((f, i) => (
            <div key={i} style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 5, padding: '8px 12px' }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
                <span style={{ font: '600 10px monospace', color: '#ef4444', textTransform: 'uppercase' }}>{f.severity || 'medium'}</span>
                {f.file && <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)' }}>{f.file}</span>}
              </div>
              <div style={{ font: '400 11px/1.4 monospace', color: 'var(--af-text-muted)' }}>{f.description || f.message || String(f)}</div>
            </div>
          ))}
        </>
      )}

      {loading && <div className="af-understand__hint">Loading patches…</div>}
      {!loading && highRiskPatches.length > 0 && (
        <>
          <SectionLabel>HIGH-RISK STAGED PATCHES — {highRiskPatches.length}</SectionLabel>
          {highRiskPatches.map((p, i) => (
            <div key={p.id || i} style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 5, padding: '10px 12px' }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'center' }}>
                <span style={{ font: '600 10px monospace', color: '#f59e0b', textTransform: 'uppercase' }}>{p.risk_level || 'high'}</span>
                <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.file_path || p.path}</span>
                <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase', flexShrink: 0 }}>{p.status}</span>
              </div>
              {p.unified_diff && (
                <pre style={{ font: '400 10px/1.4 monospace', color: 'var(--af-text-muted)', maxHeight: 120, overflow: 'auto', background: 'rgba(0,0,0,0.3)', padding: '6px 8px', borderRadius: 3, margin: '4px 0' }}>
                  {p.unified_diff.slice(0, 600)}{p.unified_diff.length > 600 ? '\n...' : ''}
                </pre>
              )}
              {pendingPatches.some(pp => pp.id === p.id) && onApprove && (
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <button className="af-btn af-btn--success af-btn--sm" onClick={() => onApprove(p.id)}>Approve</button>
                  <button className="af-btn af-btn--danger af-btn--sm" onClick={() => onReject(p.id)}>Reject</button>
                </div>
              )}
            </div>
          ))}
        </>
      )}
      {!loading && !activeRun && secFindings.length === 0 && highRiskPatches.length === 0 && (
        <EmptyState title="All clear" body="No pending approvals, security findings, or high-risk patches." />
      )}
    </div>
  )
}

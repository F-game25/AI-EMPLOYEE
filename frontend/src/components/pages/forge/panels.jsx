import { useState, useEffect, useRef, useCallback } from 'react'
import { SectionLabel, StatusPill, EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JPOST, JGET, JPOST_JSON, TEMPLATES, DEFAULT_SKILL_PACKS, textFrom, titleize, normalizeAction, isPendingAction, canBatchApprove } from './helpers'
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

export function ChatPane({ project, messages, onSend, sending, selectedSkillIds, onSkillChange }) {
  const inputRef = useRef(null)
  const endRef   = useRef(null)
  const [text, setText] = useState('')
  const [displayedContent, setDisplayedContent] = useState('')
  const lastMessage = messages[messages.length - 1]
  const lastAssistantContent = lastMessage?.role === 'assistant' ? lastMessage.content || '' : ''

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, displayedContent])

  useEffect(() => {
    if (!lastAssistantContent) return undefined
    let i = 0
    const t = setInterval(() => {
      i += 3
      setDisplayedContent(lastAssistantContent.slice(0, i))
      if (i >= lastAssistantContent.length) clearInterval(t)
    }, 16)
    return () => clearInterval(t)
  }, [lastAssistantContent])

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
          const bodyText = isLastAssistant ? (m.content ? displayedContent : '') : m.content
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
      <div className="af-run af-run--empty">
        <div className="af-run__empty">
          <span className="af-run__empty-mark">◆</span>
          <strong>No active run</strong>
          <p>Create a run from chat to see the real context pack, policy decisions, verification results, and apply state.</p>
        </div>
      </div>
    )
  }
  const latestTest = (run.test_results || []).slice(-1)[0]
  const report = run.final_report || {}
  const patches = run.patches || []
  const actions = run.actions || []
  const stagedCount = patches.filter(patch => ['staged', 'verified', 'applied'].includes(String(patch.status || '').toLowerCase())).length
  const blockedCount = patches.filter(patch => patch.policy?.allowed === false || String(patch.status || '').toLowerCase() === 'blocked').length
  const writeCount = actions.filter(action => RUN_WRITE_TYPES.has(action.type)).length || patches.length
  const canVerify = !busy && stagedCount > 0 && blockedCount === 0 && run.status !== 'applied'
  const canApply = !busy && run.status === 'verified' && latestTest?.all_passed === true && blockedCount === 0
  const verifyReason = busy
    ? 'Run operation in progress'
    : blockedCount > 0
      ? 'Blocked patches must be resolved first'
      : stagedCount === 0
        ? 'Approve and stage a write action first'
        : run.status === 'applied'
          ? 'Run has already been applied'
          : 'Run is staged and ready to verify'
  const applyReason = busy
    ? 'Run operation in progress'
    : run.status !== 'verified'
      ? 'Verification must pass before apply'
      : latestTest?.all_passed !== true
        ? 'Latest verification did not pass'
        : blockedCount > 0
          ? 'Blocked patches cannot be applied'
          : 'Verified run is ready to apply'
  const stages = [
    ['intake', 'Intake', true],
    ['context', 'Context', !!run.context_pack],
    ['plan', 'Plan', !!run.plan],
    ['patch', 'Patch', (run.patches || []).length > 0],
    ['approval', 'Approval', stagedCount > 0],
    ['verify', 'Verify', !!latestTest?.all_passed],
    ['apply', 'Apply', run.status === 'applied'],
    ['report', 'Report', !!run.final_report],
  ]
  return (
    <div className="af-run">
      <div className="af-run__head">
        <div>
          <span className="af-run__eyebrow">Active Run</span>
          <strong>{run.id}</strong>
          <p>{run.goal}</p>
        </div>
        <StatusPill label={String(run.status || 'new').toUpperCase()} tone={run.status === 'applied' || run.status === 'verified' ? 'success' : run.status === 'blocked' || run.status === 'verify_failed' ? 'alert' : 'gold'} size="sm" />
      </div>
      <div className="af-run__console">
        <div className="af-run__console-title">
          <span>Run Console</span>
          <em>{run.mode || 'supervised'} / {run.provider || 'local-first'}</em>
        </div>
        <div className="af-run__console-grid">
          <span><b>{formatCount(writeCount, 'write')}</b><small>proposed</small></span>
          <span><b>{formatCount(stagedCount, 'patch')}</b><small>staged</small></span>
          <span><b>{formatCount(blockedCount || run.review?.blocked, 'block')}</b><small>policy</small></span>
        </div>
      </div>
      <div className="af-run__timeline">
        {stages.map(([id, label, done]) => (
          <div key={id} className={`af-run__step ${done ? 'af-run__step--done' : ''}`}>
            <span />
            <em>{label}</em>
          </div>
        ))}
      </div>
      <div className="af-run__grid">
        <MiniField label="Goal" value={run.goal} />
        <MiniField label="Files found" value={run.context_pack?.relevant_files?.length || 0} />
        <MiniField label="Tree paths" value={run.context_pack?.tree_paths?.length || 0} />
        <MiniField label="Patches" value={run.patches?.length || 0} />
        <MiniField label="Blocked" value={run.review?.blocked || 0} />
        <MiniField label="Last verify" value={latestTest ? (latestTest.all_passed ? 'passed' : 'failed') : 'not run'} />
        <MiniField label="Applied files" value={report.applied_files?.length || 0} />
      </div>
      {run.ui_error && <div className="af-run__error">{run.ui_error}</div>}
      {run.review?.summary && <div className="af-run__review">{run.review.summary}</div>}
      {run.context_pack?.verification_commands?.length > 0 && (
        <StructuredList title="Verification" items={run.context_pack.verification_commands.map(command => ({ label: command }))} />
      )}
      {latestTest?.results?.length > 0 && (
        <div className="af-run__tests">
          {latestTest.results.map((result, index) => (
            <div key={index} className={`af-run__test ${result.pass ? 'ok' : 'fail'}`}>
              <span>{result.pass ? 'PASS' : 'FAIL'}</span>
              <code>{result.command || 'verification'}</code>
            </div>
          ))}
        </div>
      )}
      <div className="af-run__actions">
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={onVerify} disabled={!canVerify} title={verifyReason}>
          {busy ? 'Working...' : 'Verify Staged'}
        </button>
        <button className="af-btn af-btn--primary af-btn--sm" onClick={onApply} disabled={!canApply} title={applyReason}>
          Apply Verified
        </button>
      </div>
      <div className="af-run__gate">{canApply ? applyReason : verifyReason}</div>
    </div>
  )
}

export function ActionQueue({ actions, busyActions, onApprove, onReject, onApproveSafeBatch }) {
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
        return (
        <div key={action.id} className={`af-action ${open ? '' : 'af-action--closed'} af-action--${action.type.toLowerCase()} af-action--risk-${action.risk}`}>
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
          <strong>{visibleDecision?.risk || 'none'}</strong>
        </div>
      </div>
    </div>
  )
}

export function ForgeSystemPanel({ onQueueItems }) {
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
      {data.loading && <div className="af-ops__notice">Loading live Forge status...</div>}
      {!data.loading && !data.status && <div className="af-ops__notice af-ops__notice--warn">Forge status endpoint did not respond.</div>}
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

export function AgentBlueprintPanel() {
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
      <div className="af-understand__hint">One goal → generate → apply → verify → fix, looping until green. Auto-rolls-back if it can’t pass. Owner-approved & bounded.</div>
      <textarea className="af-agentic__goal" rows={3} value={goal} onChange={e => setGoal(e.target.value)} placeholder="e.g. Add a /health route that returns {status:'ok'} and make sure the build passes" />
      <div className="af-agentic__controls">
        <label>Max iterations
          <select value={maxIters} onChange={e => setMaxIters(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button className="af-index-btn" onClick={start} disabled={running}>{running ? 'Building…' : '▶ Auto-build'}</button>
      </div>

      {run && (
        <div className="af-agentic__result">
          <div className={`af-agentic__status ${run.success ? 'ok' : 'fail'}`}>
            {run.success ? '✓ ' : '✗ '}{run.summary}
          </div>
          {(run.transcript || []).map(t => (
            <div key={t.iteration} className="af-agentic__iter">
              <div className="af-agentic__itertitle">Iteration {t.iteration} — {t.verify?.all_passed ? 'PASS' : 'FAIL'}</div>
              <div className="af-agentic__files">{(t.files_written || []).map((f, i) => <span key={i} className={f.ok ? 'ok' : 'fail'}>{f.path}</span>)}</div>
              {(t.verify?.results || []).filter(r => !r.pass).map((r, i) => (
                <pre key={i} className="af-agentic__err">{r.command}: {(r.output || '').slice(-400)}</pre>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

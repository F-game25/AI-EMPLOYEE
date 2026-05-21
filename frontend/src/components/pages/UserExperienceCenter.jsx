import { useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
import { useAppStore } from '../../store/appStore'
import './UserExperienceCenter.css'

const PERSPECTIVES = [
  {
    id: 'technical_admin',
    label: 'Technical Admin',
    purpose: 'Install, configure, verify, and keep the system honest about live versus degraded state.',
    primary: ['setup', 'system', 'integrations', 'models', 'api-catalog'],
    checks: ['node_backend', 'python_backend', 'llm_provider_routing', 'tool_registry', 'event_bus', 'artifact_storage', 'memory_vector_store'],
    workflows: [
      { label: 'Run setup check', target: 'setup', why: 'Confirm runtime, LLM, tools, memory, artifacts, and event bus.' },
      { label: 'Inspect system health', target: 'system', why: 'Review live process, port, storage, warning, and uptime status.' },
      { label: 'Review API catalog', target: 'api-catalog', why: 'See route ownership, auth, contracts, legacy status, and smoke results.' },
    ],
    proof: ['Capability check timestamp', 'doctor/setup result', 'route smoke status', 'runtime warning state'],
    safety: ['Never mark fallback/mock as live', 'Do not run destructive maintenance without typed confirmation'],
    done: ['Critical capabilities are live or explicitly labeled', 'No silent mock data remains in admin-critical pages'],
  },
  {
    id: 'owner',
    label: 'Owner / Founder',
    purpose: 'See outcomes, risk, revenue movement, and what needs approval.',
    primary: ['economy', 'approvals', 'proof', 'operations'],
    checks: ['money_mode', 'approval_inbox', 'artifact_storage', 'llm_provider_routing'],
    workflows: [
      { label: 'Review approvals', target: 'approvals', why: 'Approve or reject external, money, publishing, or account-impacting actions.' },
      { label: 'Open Money Mode', target: 'economy', why: 'Inspect revenue pipelines, ledger, wallet status, and approval gates.' },
      { label: 'Check proof', target: 'proof', why: 'Verify outputs before relying on business results.' },
    ],
    proof: ['Approval decisions', 'ledger records', 'dry-run previews', 'provider response IDs'],
    safety: ['Spending, outreach, publishing, wallet, and paid-task acceptance require approval'],
    done: ['Pending approvals are clear', 'Money activity has proof or is explicitly dry-run'],
  },
  {
    id: 'operator',
    label: 'Daily Operator',
    purpose: 'Run work, watch execution, clear blockers, and deliver outputs.',
    primary: ['tasks', 'workflows', 'approvals', 'proof'],
    checks: ['python_backend', 'real_execution_engine', 'event_bus', 'tool_registry'],
    workflows: [
      { label: 'Run task', target: 'tasks', why: 'Submit work through the canonical task/turn path.' },
      { label: 'Open workflows', target: 'workflows', why: 'Draft or run supervised multi-step work.' },
      { label: 'View proof', target: 'proof', why: 'Confirm artifacts, traces, and action results.' },
    ],
    proof: ['turn_id and task_id', 'action trace', 'artifact links', 'error or blocker details'],
    safety: ['Failed or fallback actions must be labeled before delivery'],
    done: ['Task reaches completed/blocked state', 'Output has usable proof or a clear blocker'],
  },
  {
    id: 'analyst',
    label: 'Analyst / Researcher',
    purpose: 'Inspect evidence, citations, memory, research, and data quality.',
    primary: ['research', 'knowledge', 'memory', 'proof'],
    checks: ['memory_vector_store', 'artifact_storage', 'python_backend', 'llm_provider_routing'],
    workflows: [
      { label: 'Start research', target: 'research', why: 'Discover sources and run evidence-producing research.' },
      { label: 'Open knowledge', target: 'knowledge', why: 'Review vault notes, standing topics, and broken links.' },
      { label: 'Inspect memory', target: 'memory', why: 'Search facts, conversations, semantic store, and graph state.' },
    ],
    proof: ['citations', 'source list', 'memory query result', 'research trace'],
    safety: ['Research should show source quality and not hide empty/fallback paths'],
    done: ['Claims have citations or explicit uncertainty', 'Memory/vector store state is visible'],
  },
  {
    id: 'teammate',
    label: 'AI Teammate User',
    purpose: 'Ask for work in plain language and receive visible action plus proof.',
    primary: ['nexus', 'tasks', 'proof', 'setup'],
    checks: ['python_backend', 'llm_provider_routing', 'event_bus', 'artifact_storage'],
    workflows: [
      { label: 'Open chat', target: 'nexus', why: 'Ask naturally and get teammate-style response, actions, and proof.' },
      { label: 'Track task', target: 'tasks', why: 'See live status, action rows, blockers, and final result.' },
      { label: 'Open proof', target: 'proof', why: 'Use the output or inspect why it was blocked.' },
    ],
    proof: ['assistant summary', 'visible actions', 'artifact/output link', 'degraded/fallback flag'],
    safety: ['The assistant must not pretend success when tools or providers are unavailable'],
    done: ['One clear answer, one visible action trail, and one usable output/proof state'],
  },
  {
    id: 'reviewer',
    label: 'Reviewer / Client',
    purpose: 'Inspect delivered outputs without needing system internals.',
    primary: ['proof', 'workspace', 'approvals', 'knowledge'],
    checks: ['artifact_storage', 'approval_inbox', 'event_bus'],
    workflows: [
      { label: 'Open proof', target: 'proof', why: 'Review generated files, dry-runs, citations, and traces.' },
      { label: 'Open workspace', target: 'workspace', why: 'Preview files and generated deliverables.' },
      { label: 'Check approvals', target: 'approvals', why: 'Confirm any risky delivery was approved or rejected.' },
    ],
    proof: ['file path or URL', 'approval record', 'trace summary', 'citation list'],
    safety: ['Reviewer view should expose results and status without secret/config details'],
    done: ['Deliverable opens cleanly', 'Risky external effects have approval records'],
  },
]

const STATUS_ORDER = ['error', 'unavailable', 'not_configured', 'fallback', 'dry_run', 'mock', 'live']
const STATUS_LABELS = {
  live: 'Live',
  dry_run: 'Dry-run',
  mock: 'Mock',
  fallback: 'Fallback',
  not_configured: 'Needs setup',
  unavailable: 'Unavailable',
  error: 'Error',
}

function statusRank(status) {
  const idx = STATUS_ORDER.indexOf(status)
  return idx === -1 ? 0 : idx
}

function worstStatus(items) {
  if (!items.length) return 'unavailable'
  return items.reduce((worst, item) => statusRank(item.status) < statusRank(worst) ? item.status : worst, 'live')
}

function perspectiveState(perspective, capabilitiesById) {
  const checks = perspective.checks.map(id => capabilitiesById[id]).filter(Boolean)
  const missing = perspective.checks.filter(id => !capabilitiesById[id])
  const status = worstStatus(checks)
  const liveCount = checks.filter(cap => cap.status === 'live').length
  const readyCount = checks.filter(cap => cap.status === 'live' || cap.status === 'dry_run').length
  const total = perspective.checks.length || 1
  const readiness = Math.round((readyCount / total) * 100)
  const blockers = [
    ...checks.filter(cap => ['error', 'unavailable', 'not_configured'].includes(cap.status)),
    ...missing.map(id => ({ id, label: id.replace(/_/g, ' '), status: 'unavailable', details: 'Capability is not reported by backend status registry.' })),
  ]
  return { checks, missing, status, liveCount, readiness, blockers }
}

function RoleCard({ role, capabilitiesById, active, onSelect, onNavigate }) {
  const state = perspectiveState(role, capabilitiesById)

  return (
    <section className={`ux-role-card ux-role-card--${state.status} ${active ? 'ux-role-card--active' : ''}`}>
      <div className="ux-role-head">
        <div>
          <h2>{role.label}</h2>
          <p>{role.purpose}</p>
        </div>
        <span className={`ux-status ux-status--${state.status}`}>{STATUS_LABELS[state.status] || state.status}</span>
      </div>

      <div className="ux-readiness">
        <span>READINESS</span>
        <b>{state.readiness}%</b>
        <div className="ux-readiness__bar"><i style={{ width: `${state.readiness}%` }} /></div>
      </div>

      <div className="ux-checks">
        {state.checks.map(cap => (
          <div key={cap.id} className="ux-check-row">
            <span>{cap.label || cap.id}</span>
            <b className={`ux-status-text ux-status-text--${cap.status}`}>{STATUS_LABELS[cap.status] || cap.status}</b>
          </div>
        ))}
        {state.missing.map(id => (
          <div key={id} className="ux-check-row ux-check-row--missing">
            <span>{id.replace(/_/g, ' ')}</span>
            <b>Not reported</b>
          </div>
        ))}
      </div>

      <div className="ux-actions">
        <button type="button" onClick={onSelect}>Inspect</button>
        {role.primary.map(target => (
          <button key={target} type="button" onClick={() => onNavigate(target)}>
            {target.replace(/-/g, ' ')}
          </button>
        ))}
      </div>

      <div className="ux-role-foot">
        <span>{state.liveCount} live checks</span>
        <span>{state.blockers.length} blocker(s)</span>
      </div>
    </section>
  )
}

function PerspectiveDetail({ perspective, capabilitiesById, onNavigate }) {
  const state = perspectiveState(perspective, capabilitiesById)
  return (
    <section className={`ux-perspective-detail ux-perspective-detail--${state.status}`}>
      <div className="ux-perspective-detail__head">
        <div>
          <span className="ux-eyebrow">ACTIVE PERSPECTIVE</span>
          <h2>{perspective.label}</h2>
          <p>{perspective.purpose}</p>
        </div>
        <div className="ux-perspective-score">
          <b>{state.readiness}%</b>
          <span>{STATUS_LABELS[state.status] || state.status}</span>
        </div>
      </div>

      <div className="ux-detail-grid">
        <div className="ux-detail-panel">
          <h3>Workflow Launches</h3>
          {perspective.workflows.map(item => (
            <button key={item.label} className="ux-workflow-row" type="button" onClick={() => onNavigate(item.target)}>
              <span>{item.label}</span>
              <small>{item.why}</small>
            </button>
          ))}
        </div>

        <div className="ux-detail-panel">
          <h3>Blockers</h3>
          {state.blockers.length ? state.blockers.map(item => (
            <div key={item.id} className="ux-blocker-row">
              <span>{item.label || item.id}</span>
              <b className={`ux-status-text ux-status-text--${item.status}`}>{STATUS_LABELS[item.status] || item.status}</b>
              <small>{item.details || item.docs_hint || item.setup_action || 'Needs admin action.'}</small>
            </div>
          )) : <div className="ux-muted">No hard blockers reported for this perspective.</div>}
        </div>

        <div className="ux-detail-panel">
          <h3>Proof Expected</h3>
          <ul>
            {perspective.proof.map(item => <li key={item}>{item}</li>)}
          </ul>
        </div>

        <div className="ux-detail-panel">
          <h3>Safety And Done Criteria</h3>
          <ul>
            {[...perspective.safety, ...perspective.done].map(item => <li key={item}>{item}</li>)}
          </ul>
        </div>
      </div>
    </section>
  )
}

export default function UserExperienceCenter() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const [selectedPerspective, setSelectedPerspective] = useState(() => {
    try { return localStorage.getItem('nx:selected-perspective') || 'technical_admin' } catch { return 'technical_admin' }
  })
  const [capabilityStatus, setCapabilityStatus] = useState(null)
  const [approvals, setApprovals] = useState(null)
  const [proof, setProof] = useState(null)
  const [readiness, setReadiness] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setError(null)
      try {
        const [caps, approvalData, proofData, ready] = await Promise.all([
          api.get('/api/capabilities/status'),
          api.get('/api/approvals/inbox').catch(() => null),
          api.get('/api/proof/center').catch(() => null),
          api.get('/api/readiness').catch(() => null),
        ])
        if (cancelled) return
        setCapabilityStatus(caps)
        setApprovals(approvalData)
        setProof(proofData)
        setReadiness(ready)
      } catch (e) {
        if (!cancelled) setError(e.message || 'Unable to load user views')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const timer = setInterval(load, 30000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  const capabilities = capabilityStatus?.capabilities || []
  const capabilitiesById = useMemo(() => Object.fromEntries(capabilities.map(c => [c.id, c])), [capabilities])
  const counts = capabilityStatus?.counts || {}
  const approvalCounts = approvals?.counts || {}
  const proofCounts = proof?.counts || {}
  const readyState = readiness?.phase || readiness?.status || 'unknown'
  const activePerspective = PERSPECTIVES.find(role => role.id === selectedPerspective) || PERSPECTIVES[0]

  function selectPerspective(id) {
    setSelectedPerspective(id)
    try { localStorage.setItem('nx:selected-perspective', id) } catch {}
  }

  return (
    <div className="ux-page">
      <header className="ux-header">
        <div>
          <span className="ux-eyebrow">USER READINESS</span>
          <h1>Perspective Center</h1>
        </div>
        <div className="ux-summary">
          <div><b>{readyState}</b><span>runtime</span></div>
          <div><b>{approvalCounts.pending || 0}</b><span>pending approvals</span></div>
          <div><b>{proofCounts.total || proofCounts.items || 0}</b><span>proof items</span></div>
          <div><b>{counts.live || 0}</b><span>live capabilities</span></div>
        </div>
      </header>

      {error && <div className="ux-error" role="alert">{error}</div>}
      {loading && !capabilityStatus && <div className="ux-error" role="status" style={{ background: 'transparent', color: 'var(--nx-text-muted)' }}>Loading user views…</div>}

      <div className="ux-perspective-tabs" role="tablist" aria-label="User perspectives">
        {PERSPECTIVES.map(role => (
          <button
            key={role.id}
            type="button"
            role="tab"
            aria-selected={activePerspective.id === role.id}
            className={activePerspective.id === role.id ? 'is-active' : ''}
            onClick={() => selectPerspective(role.id)}
          >
            {role.label}
          </button>
        ))}
      </div>

      <PerspectiveDetail perspective={activePerspective} capabilitiesById={capabilitiesById} onNavigate={setActiveSection} />

      <div className="ux-grid">
        {PERSPECTIVES.map(role => (
          <RoleCard
            key={role.id}
            role={role}
            capabilitiesById={capabilitiesById}
            active={activePerspective.id === role.id}
            onSelect={() => selectPerspective(role.id)}
            onNavigate={setActiveSection}
          />
        ))}
      </div>

      <section className="ux-guidance">
        <div>
          <h2>Recommended Next Action</h2>
          <p>{capabilityStatus?.next_recommended_action?.details || capabilityStatus?.next_recommended_action?.label || 'Run Setup Center, then complete one safe task and confirm proof appears.'}</p>
        </div>
        <div className="ux-guidance-actions">
          <button type="button" onClick={() => setActiveSection('setup')}>Open Setup</button>
          <button type="button" onClick={() => setActiveSection('tasks')}>Run Task</button>
          <button type="button" onClick={() => setActiveSection('proof')}>View Proof</button>
        </div>
      </section>
    </div>
  )
}

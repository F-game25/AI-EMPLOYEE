import { useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
import { useAppStore } from '../../store/appStore'
import './UserExperienceCenter.css'

const ROLES = [
  {
    id: 'owner',
    label: 'Owner / Founder',
    purpose: 'See outcomes, risk, revenue movement, and what needs approval.',
    primary: ['economy', 'approvals', 'proof', 'operations'],
    checks: ['money_mode', 'approval_inbox', 'artifact_storage', 'llm_provider_routing'],
  },
  {
    id: 'operator',
    label: 'Daily Operator',
    purpose: 'Run work, watch execution, clear blockers, and deliver outputs.',
    primary: ['tasks', 'workflows', 'approvals', 'proof'],
    checks: ['python_backend', 'real_execution_engine', 'event_bus', 'tool_registry'],
  },
  {
    id: 'analyst',
    label: 'Analyst / Researcher',
    purpose: 'Inspect evidence, citations, memory, research, and data quality.',
    primary: ['research', 'knowledge', 'memory', 'proof'],
    checks: ['memory_vector_store', 'artifact_storage', 'python_backend', 'llm_provider_routing'],
  },
  {
    id: 'teammate',
    label: 'AI Teammate User',
    purpose: 'Ask for work in plain language and receive visible action plus proof.',
    primary: ['nexus', 'tasks', 'proof', 'setup'],
    checks: ['python_backend', 'llm_provider_routing', 'event_bus', 'artifact_storage'],
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

function RoleCard({ role, capabilitiesById, counts, onNavigate }) {
  const checks = role.checks.map(id => capabilitiesById[id]).filter(Boolean)
  const missing = role.checks.filter(id => !capabilitiesById[id])
  const status = worstStatus(checks)

  return (
    <section className={`ux-role-card ux-role-card--${status}`}>
      <div className="ux-role-head">
        <div>
          <h2>{role.label}</h2>
          <p>{role.purpose}</p>
        </div>
        <span className={`ux-status ux-status--${status}`}>{STATUS_LABELS[status] || status}</span>
      </div>

      <div className="ux-checks">
        {checks.map(cap => (
          <div key={cap.id} className="ux-check-row">
            <span>{cap.label || cap.id}</span>
            <b className={`ux-status-text ux-status-text--${cap.status}`}>{STATUS_LABELS[cap.status] || cap.status}</b>
          </div>
        ))}
        {missing.map(id => (
          <div key={id} className="ux-check-row ux-check-row--missing">
            <span>{id.replace(/_/g, ' ')}</span>
            <b>Not reported</b>
          </div>
        ))}
      </div>

      <div className="ux-actions">
        {role.primary.map(target => (
          <button key={target} type="button" onClick={() => onNavigate(target)}>
            {target.replace(/-/g, ' ')}
          </button>
        ))}
      </div>

      <div className="ux-role-foot">
        <span>{counts.live || 0} live</span>
        <span>{(counts.not_configured || 0) + (counts.unavailable || 0) + (counts.error || 0)} needs attention</span>
      </div>
    </section>
  )
}

export default function UserExperienceCenter() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const [capabilityStatus, setCapabilityStatus] = useState(null)
  const [approvals, setApprovals] = useState(null)
  const [proof, setProof] = useState(null)
  const [readiness, setReadiness] = useState(null)
  const [error, setError] = useState(null)

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

  return (
    <div className="ux-page">
      <header className="ux-header">
        <div>
          <span className="ux-eyebrow">USER READINESS</span>
          <h1>Role Views</h1>
        </div>
        <div className="ux-summary">
          <div><b>{readyState}</b><span>runtime</span></div>
          <div><b>{approvalCounts.pending || 0}</b><span>pending approvals</span></div>
          <div><b>{proofCounts.total || proofCounts.items || 0}</b><span>proof items</span></div>
          <div><b>{counts.live || 0}</b><span>live capabilities</span></div>
        </div>
      </header>

      {error && <div className="ux-error">{error}</div>}

      <div className="ux-grid">
        {ROLES.map(role => (
          <RoleCard
            key={role.id}
            role={role}
            capabilitiesById={capabilitiesById}
            counts={counts}
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

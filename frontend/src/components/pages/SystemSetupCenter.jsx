import { useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
import { useAppStore } from '../../store/appStore'
import { useSystemStore } from '../../store/systemStore'
import './SystemSetupCenter.css'

const STATUS_LABEL = {
  live: 'Live',
  dry_run: 'Dry-run',
  mock: 'Mock',
  fallback: 'Fallback',
  not_configured: 'Needs setup',
  unavailable: 'Unavailable',
  error: 'Error',
}

const CATEGORY_ORDER = ['runtime', 'llm', 'execution', 'memory', 'integration', 'money', 'security']

const WIZARD_STEPS = [
  { id: 'identity', label: 'Identity', detail: 'Name the system and confirm the technical owner.' },
  { id: 'runtime', label: 'Runtime', detail: 'Check Node, Python, WebSocket, ports, build output, and startup warnings.' },
  { id: 'llm', label: 'LLM', detail: 'Confirm local or provider-backed model access before live task execution.' },
  { id: 'memory', label: 'Memory', detail: 'Confirm memory, vector, artifact, and proof storage are writable.' },
  { id: 'integrations', label: 'Integrations', detail: 'Review missing provider keys and approval-gated connectors.' },
  { id: 'safety', label: 'Money Safety', detail: 'Confirm external effects require approval before execution.' },
  { id: 'smoke', label: 'Smoke Test', detail: 'Run one safe canonical task and display proof/output.' },
]

const USER_READINESS = [
  {
    id: 'technical_admin',
    label: 'Technical Admin',
    needs: ['runtime', 'llm', 'execution', 'memory', 'security'],
    outcome: 'Can install, configure, verify, and troubleshoot the system.',
  },
  {
    id: 'owner',
    label: 'Owner / Founder',
    needs: ['money', 'integration', 'execution'],
    outcome: 'Can see what makes money, what needs approval, and what produced proof.',
  },
  {
    id: 'operator',
    label: 'Daily Operator',
    needs: ['execution', 'memory', 'integration'],
    outcome: 'Can run tasks, inspect blockers, and find usable outputs.',
  },
  {
    id: 'analyst',
    label: 'Analyst',
    needs: ['memory', 'llm', 'execution'],
    outcome: 'Can verify sources, traces, model choices, and degraded results.',
  },
]

function normalizeStatus(status) {
  return STATUS_LABEL[status] ? status : 'error'
}

function statusLabel(status) {
  return STATUS_LABEL[normalizeStatus(status)]
}

function statusSeverity(status) {
  const s = normalizeStatus(status)
  if (s === 'live') return 0
  if (s === 'dry_run' || s === 'fallback') return 1
  if (s === 'mock' || s === 'not_configured') return 2
  return 3
}

function fmtTime(value) {
  if (!value) return 'Not checked'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Not checked'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function capabilityId(capability) {
  return capability?.id || capability?.name || capability?.label || 'capability'
}

function groupCapabilities(capabilities) {
  const groups = new Map()
  for (const capability of capabilities) {
    const category = capability.category || 'runtime'
    if (!groups.has(category)) groups.set(category, [])
    groups.get(category).push(capability)
  }
  return [...groups.entries()].sort(([a], [b]) => {
    const ai = CATEGORY_ORDER.indexOf(a)
    const bi = CATEGORY_ORDER.indexOf(b)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b)
  })
}

function deriveWizardStatus(step, capabilities) {
  if (step.id === 'identity') return 'live'
  if (step.id === 'safety') return capabilities.some(cap => capabilityId(cap) === 'money_mode') ? 'live' : 'fallback'
  if (step.id === 'smoke') return capabilities.some(cap => normalizeStatus(cap.status) === 'live') ? 'fallback' : 'unavailable'

  const category = step.id === 'integrations' ? 'integration' : step.id
  const related = capabilities.filter(cap => cap.category === category)
  if (!related.length) return 'unavailable'
  const worst = Math.max(...related.map(cap => statusSeverity(cap.status)))
  if (worst === 0) return 'live'
  if (worst === 1) return 'fallback'
  if (worst === 2) return 'not_configured'
  return 'unavailable'
}

function deriveUserReadiness(profile, capabilities) {
  const related = capabilities.filter(capability => profile.needs.includes(capability.category))
  if (!related.length) return { status: 'unavailable', blockers: ['No capability data for this profile yet.'] }
  const blockers = related
    .filter(capability => normalizeStatus(capability.status) !== 'live')
    .map(capability => `${capability.label || capabilityId(capability)}: ${statusLabel(capability.status)}`)
  if (!blockers.length) return { status: 'live', blockers: [] }
  const hardBlock = related.some(capability => ['unavailable', 'error', 'not_configured'].includes(normalizeStatus(capability.status)))
  return { status: hardBlock ? 'not_configured' : 'fallback', blockers: blockers.slice(0, 4) }
}

function StatusBadge({ status }) {
  const normalized = normalizeStatus(status)
  return <span className={`setup-status setup-status--${normalized}`}>{statusLabel(normalized)}</span>
}

function CapabilityRow({ capability, onAction }) {
  const missing = Array.isArray(capability.missing_env) ? capability.missing_env : []
  const action = capability.setup_action || 'none'
  return (
    <div className={`setup-cap setup-cap--${normalizeStatus(capability.status)}`}>
      <div className="setup-cap__main">
        <span className="setup-cap__dot" />
        <div>
          <div className="setup-cap__name">{capability.label || capabilityId(capability)}</div>
          <div className="setup-cap__details">{capability.details || capability.docs_hint || 'No details reported.'}</div>
          {missing.length > 0 && (
            <div className="setup-cap__env">Missing: {missing.join(', ')}</div>
          )}
        </div>
      </div>
      <div className="setup-cap__side">
        <StatusBadge status={capability.status} />
        <button type="button" className="setup-btn setup-btn--small" onClick={() => onAction(action, capability)}>
          {action === 'none' ? 'View' : action.replace(/_/g, ' ')}
        </button>
      </div>
    </div>
  )
}

export default function SystemSetupCenter() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const capabilityStatus = useSystemStore(s => s.capabilityStatus)
  const fetchCapabilityStatus = useSystemStore(s => s.fetchCapabilityStatus)
  const [activeStep, setActiveStep] = useState('runtime')
  const [identity, setIdentity] = useState({ systemName: 'Aeternus Nexus', adminName: 'Technical Admin' })
  const [actionResult, setActionResult] = useState(null)
  const [smokeResult, setSmokeResult] = useState(null)
  const [busyAction, setBusyAction] = useState(null)

  useEffect(() => {
    fetchCapabilityStatus()
  }, [fetchCapabilityStatus])

  const capabilities = Array.isArray(capabilityStatus.capabilities) ? capabilityStatus.capabilities : []
  const grouped = useMemo(() => groupCapabilities(capabilities), [capabilities])
  const counts = capabilityStatus.counts || {}
  const total = capabilities.length
  const live = counts.live || capabilities.filter(cap => normalizeStatus(cap.status) === 'live').length
  const needsSetup = capabilities.filter(cap => normalizeStatus(cap.status) !== 'live').length
  const recommended = capabilityStatus.next_recommended_action
  const envList = useMemo(() => {
    return [...new Set(capabilities.flatMap(cap => Array.isArray(cap.missing_env) ? cap.missing_env : []))].sort()
  }, [capabilities])

  const runAction = async (action, capability) => {
    const capLabel = capability?.label || capabilityId(capability)
    if (action === 'configure_env') {
      setActiveSection('settings')
      return
    }
    if (action === 'view_logs') {
      setActiveSection('infrastructure')
      return
    }
    if (action === 'run_build') {
      setActionResult({ type: 'info', message: 'Frontend build is a terminal action: npm --prefix frontend run build.' })
      return
    }
    if (action === 'start_service') {
      setActionResult({ type: 'warning', message: `${capLabel} needs its service started outside the browser.` })
      return
    }
    setBusyAction(`${action}:${capabilityId(capability)}`)
    try {
      if (action === 'run_doctor') {
        const readiness = await api.get('/api/readiness')
        setActionResult({
          type: readiness?.degraded ? 'warning' : 'success',
          message: readiness?.degraded
            ? `Doctor check found: ${(readiness.degradedReasons || []).join(', ') || 'degraded state'}`
            : 'Doctor check completed without readiness degradation.',
        })
      } else {
        await fetchCapabilityStatus()
        setActionResult({ type: 'success', message: `${capLabel} check refreshed.` })
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || `${capLabel} action failed.` })
    } finally {
      setBusyAction(null)
    }
  }

  const copyEnvList = async () => {
    const text = envList.length ? envList.join('\n') : 'No missing env vars reported.'
    try {
      await navigator.clipboard.writeText(text)
      setActionResult({ type: 'success', message: 'Missing env variable list copied.' })
    } catch {
      setActionResult({ type: 'warning', message: text })
    }
  }

  const runSmokeTest = async () => {
    setBusyAction('smoke')
    setSmokeResult(null)
    try {
      const result = await api.post('/api/tasks/run', {
        task: 'Run a safe setup smoke test: summarize current system readiness without external actions.',
        user_id: 'user:technical-admin',
      })
      setSmokeResult(result)
      setActionResult({
        type: result?.degraded ? 'warning' : 'success',
        message: result?.degraded ? 'Smoke test completed with degraded/fallback output.' : 'Smoke test completed.',
      })
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || 'Smoke test failed.' })
    } finally {
      setBusyAction(null)
      fetchCapabilityStatus()
    }
  }

  return (
    <main className="setup-center">
      <section className="setup-hero">
        <div>
          <p className="setup-kicker">SYSTEM SETUP CENTER</p>
          <h1>Technical Admin Readiness</h1>
          <p className="setup-hero__copy">
            Verify what is live, what is degraded, what needs configuration, and what the next admin action should be.
          </p>
        </div>
        <div className="setup-hero__actions">
          <button type="button" className="setup-btn" onClick={fetchCapabilityStatus} disabled={capabilityStatus.loading}>
            {capabilityStatus.loading ? 'Checking' : 'Retry checks'}
          </button>
          <button type="button" className="setup-btn setup-btn--quiet" onClick={copyEnvList}>
            Copy env list
          </button>
        </div>
      </section>

      <section className="setup-overview" aria-label="Setup overview">
        <div className="setup-metric">
          <span>Live</span>
          <b>{live}/{total || 0}</b>
        </div>
        <div className="setup-metric setup-metric--warn">
          <span>Needs action</span>
          <b>{needsSetup}</b>
        </div>
        <div className="setup-metric">
          <span>Last checked</span>
          <b>{fmtTime(capabilityStatus.checked_at || capabilityStatus.lastChecked)}</b>
        </div>
        <div className="setup-next">
          <span>Next admin action</span>
          <b>{recommended?.label || 'No blocker selected'}</b>
          <small>{recommended?.details || 'Run checks to refresh the recommendation.'}</small>
        </div>
      </section>

      {actionResult && (
        <div className={`setup-alert setup-alert--${actionResult.type || 'info'}`}>
          {actionResult.message}
        </div>
      )}

      <section className="setup-grid">
        <div className="setup-panel setup-panel--wizard">
          <div className="setup-panel__head">
            <div>
              <p className="setup-kicker">FIRST-RUN WIZARD</p>
              <h2>Admin setup path</h2>
            </div>
            <button type="button" className="setup-btn setup-btn--small" onClick={() => setActiveStep('identity')}>
              Reopen
            </button>
          </div>
          <div className="setup-wizard">
            <div className="setup-wizard__steps">
              {WIZARD_STEPS.map(step => {
                const status = deriveWizardStatus(step, capabilities)
                return (
                  <button
                    key={step.id}
                    type="button"
                    className={`setup-step ${activeStep === step.id ? 'setup-step--active' : ''}`}
                    onClick={() => setActiveStep(step.id)}
                  >
                    <span>{step.label}</span>
                    <StatusBadge status={status} />
                  </button>
                )
              })}
            </div>
            <div className="setup-wizard__body">
              {WIZARD_STEPS.filter(step => step.id === activeStep).map(step => (
                <div key={step.id}>
                  <p className="setup-kicker">{step.label}</p>
                  <h3>{step.detail}</h3>
                  {step.id === 'identity' && (
                    <div className="setup-fields">
                      <label>
                        <span>System name</span>
                        <input value={identity.systemName} onChange={event => setIdentity({ ...identity, systemName: event.target.value })} />
                      </label>
                      <label>
                        <span>Admin owner</span>
                        <input value={identity.adminName} onChange={event => setIdentity({ ...identity, adminName: event.target.value })} />
                      </label>
                    </div>
                  )}
                  {step.id === 'smoke' && (
                    <button type="button" className="setup-btn" onClick={runSmokeTest} disabled={busyAction === 'smoke'}>
                      {busyAction === 'smoke' ? 'Running smoke test' : 'Run safe smoke test'}
                    </button>
                  )}
                  {step.id !== 'identity' && step.id !== 'smoke' && (
                    <div className="setup-step__hint">
                      Review the capability matrix below. Fallback, dry-run, mock, and unavailable states are not treated as live success.
                    </div>
                  )}
                </div>
              ))}
              {smokeResult && (
                <div className="setup-smoke">
                  <div><b>Status:</b> {smokeResult.status || (smokeResult.ok ? 'completed' : 'failed')}</div>
                  <div><b>Turn:</b> {smokeResult.turn_id || smokeResult.taskId || 'not returned'}</div>
                  <div><b>Source:</b> {smokeResult.source || 'unknown'}</div>
                  <div><b>Proof items:</b> {(smokeResult.proof || []).length + (smokeResult.artifacts || []).length}</div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="setup-panel">
          <div className="setup-panel__head">
            <div>
              <p className="setup-kicker">USER READINESS</p>
              <h2>After technical setup</h2>
            </div>
          </div>
          <div className="setup-users">
            {USER_READINESS.map(profile => {
              const readiness = deriveUserReadiness(profile, capabilities)
              return (
                <div key={profile.id} className="setup-user">
                  <div className="setup-user__head">
                    <b>{profile.label}</b>
                    <StatusBadge status={readiness.status} />
                  </div>
                  <p>{profile.outcome}</p>
                  {readiness.blockers.length > 0 && (
                    <ul>
                      {readiness.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="setup-panel">
        <div className="setup-panel__head">
          <div>
            <p className="setup-kicker">CAPABILITY MATRIX</p>
            <h2>Installed, configured, live, or blocked</h2>
          </div>
          {capabilityStatus.error && <span className="setup-error">{capabilityStatus.error}</span>}
        </div>
        <div className="setup-cap-groups">
          {grouped.map(([category, items]) => (
            <div key={category} className="setup-cap-group">
              <div className="setup-cap-group__title">{category}</div>
              {items
                .sort((a, b) => statusSeverity(b.status) - statusSeverity(a.status) || String(a.label).localeCompare(String(b.label)))
                .map(capability => (
                  <CapabilityRow
                    key={capabilityId(capability)}
                    capability={capability}
                    onAction={runAction}
                    busy={busyAction}
                  />
                ))}
            </div>
          ))}
          {!grouped.length && (
            <div className="setup-empty">
              Capability data is unavailable. Check authentication, then retry setup checks.
            </div>
          )}
        </div>
      </section>
    </main>
  )
}

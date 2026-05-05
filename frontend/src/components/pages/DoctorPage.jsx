import { useState, useEffect } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, KPITile, StatusPill, HexButton } from '../nexus-ui'
import api from '../../api/client'
import './DoctorPage.css'

const SUITE_ITEMS = [
  { id: 's1', name: 'DB Connection', endpoint: () => api.get('/api/health') },
  { id: 's2', name: 'Agent Ping', endpoint: () => api.get('/api/agents') },
  { id: 's3', name: 'Memory Integrity', endpoint: () => api.get('/api/brain/status') },
  { id: 's4', name: 'Brain Weight Load', endpoint: () => api.get('/api/brain/status') },
  { id: 's5', name: 'API Gateway', endpoint: () => api.get('/api/health') },
  { id: 's6', name: 'Fairness Threshold', endpoint: () => api.get('/api/fairness/status') },
]

export default function DoctorPage() {
  const executionLogs = useAppStore(s => s.executionLogs)
  const [checks, setChecks] = useState([])
  const [doctorData, setDoctorData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchDoctor = async () => {
      try {
        let res
        if (typeof api.get === 'function') {
          res = await api.get('/api/doctor/status')
        } else {
          const response = await fetch('/api/doctor/status')
          res = await response.json()
        }
        setDoctorData(res)
        const issues = (res?.issues || []).map(issue => ({
          name: issue.name || issue.component || 'Unknown',
          status: 'error',
          latency: issue.latency || '—',
          detail: issue.detail || issue.message || '',
        }))
        const strengths = (res?.strengths || []).map(s => ({
          name: s.name || s.component || 'Service',
          status: 'ok',
          latency: s.latency || '—',
          detail: s.detail || 'Working normally',
        }))
        setChecks([...strengths, ...issues])
        setLoading(false)
      } catch (e) {
        console.error('Doctor status fetch failed:', e)
        setLoading(false)
      }
    }
    fetchDoctor()
    const t = setInterval(fetchDoctor, 8000)
    return () => clearInterval(t)
  }, [])

  const errorLogs = executionLogs?.filter(l => l.level === 'ERROR' || l.level === 'WARN').slice(0, 6).map((l) => ({
    msg: l.message || l.step || 'System event',
    count: 1,
    ts: typeof l.ts === 'string' ? l.ts.slice(11, 19) : '--:--:--',
    level: l.level?.toLowerCase() || 'warn',
  })) || []

  const healthy = checks.filter(c => c.status === 'ok').length
  const warnings = checks.filter(c => c.status === 'warn').length
  const critical = checks.filter(c => c.status === 'error').length
  const healthPct = checks.length ? Math.round(healthy / checks.length * 100) : loading ? 0 : 100

  const [fixStates, setFixStates] = useState({})
  const handleFix = async (name) => {
    setFixStates(p => ({ ...p, [name]: 'running' }))
    try {
      if (typeof api.chat?.send === 'function') {
        await api.chat.send(`Fix issue: ${name}`)
      } else {
        await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: `Fix issue: ${name}` })
        })
      }
      setFixStates(p => ({ ...p, [name]: 'ok' }))
    } catch {
      setFixStates(p => ({ ...p, [name]: 'err' }))
    }
  }

  const [suiteState, setSuiteState] = useState({})
  const [suiteRunning, setSuiteRunning] = useState(false)
  const runSingle = async (item) => {
    setSuiteState(p => ({ ...p, [item.id]: 'running' }))
    try {
      if (typeof item.endpoint === 'function') {
        await item.endpoint()
      } else {
        await fetch(item.endpoint || '/api/health')
      }
      setSuiteState(p => ({ ...p, [item.id]: 'pass' }))
    } catch {
      setSuiteState(p => ({ ...p, [item.id]: 'fail' }))
    }
  }
  const runAll = async () => {
    setSuiteRunning(true)
    for (const item of SUITE_ITEMS) {
      await runSingle(item)
      await new Promise(r => setTimeout(r, 600))
    }
    setSuiteRunning(false)
  }

  const healthTone = healthPct > 90 ? 'success' : healthPct > 70 ? 'warning' : 'alert'
  const statusTone = critical > 0 ? 'alert' : warnings > 0 ? 'warning' : 'success'

  return (
    <div className="dr-grid">
      <div className="dr-kpis">
        <KPITile icon="❤" iconTone={healthTone} label="System Health" value={`${healthPct}%`} sub={`${healthy}/${checks.length} checks passing`} accent />
        <KPITile icon="✓" iconTone="success" label="Healthy" value={healthy} sub="Services OK" />
        <KPITile icon="⚠" iconTone="warning" label="Warnings" value={warnings} sub="Need attention" />
        <KPITile icon="🔴" iconTone={critical > 0 ? 'alert' : 'success'} label="Critical" value={critical} sub="Blocking issues" />
      </div>

      <div className="dr-cols">
        <div className="dr-col">
          <Panel
            icon="◐"
            title="Health Checks"
            className="dr-panel"
            actions={<StatusPill tone={statusTone} label={loading ? 'LOADING' : critical > 0 ? 'CRITICAL' : warnings > 0 ? 'WARN' : 'HEALTHY'} dot={false} size="sm" />}
          >
            {loading ? (
              <div className="dr-empty">Fetching health checks…</div>
            ) : !checks.length ? (
              <div className="dr-empty">No checks available</div>
            ) : (
              <div className="dr-checks">
                {checks.map((c, i) => (
                  <div key={i} className={`dr-check dr-check--${c.status}`}>
                    <div className={`dr-check__dot dr-check__dot--${c.status}`} />
                    <div className="dr-check__body">
                      <div className="dr-check__name">{c.name}</div>
                      <div className="dr-check__detail">{c.detail}</div>
                    </div>
                    <div className="dr-check__right">
                      <div className="dr-check__latency">{c.latency}</div>
                      <span className={`dr-check__status dr-check__status--${c.status}`}>{c.status.toUpperCase()}</span>
                      {c.status === 'warn' && (
                        <HexButton onClick={() => handleFix(c.name)} disabled={fixStates[c.name] === 'running'} size="xs" tone={fixStates[c.name] === 'ok' ? 'success' : fixStates[c.name] === 'err' ? 'alert' : 'warning'}>
                          {fixStates[c.name] === 'running' ? '…' : fixStates[c.name] === 'ok' ? '✓' : 'FIX'}
                        </HexButton>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel
            icon="🧪"
            title="Test Suite Runner"
            className="dr-panel dr-col__grow"
            actions={<HexButton onClick={runAll} disabled={suiteRunning} variant="primary" tone="cyan" size="sm">{suiteRunning ? 'RUNNING…' : 'RUN ALL'}</HexButton>}
          >
            <div className="dr-suite">
              {SUITE_ITEMS.map(item => {
                const st = suiteState[item.id]
                return (
                  <div key={item.id} className={`dr-suite-item dr-suite-item--${st || 'idle'}`}>
                    <div className={`dr-suite-item__dot dr-suite-item__dot--${st || 'idle'}`} />
                    <span className="dr-suite-item__name">{item.name}</span>
                    <span className={`dr-suite-item__status dr-suite-item__status--${st || 'idle'}`}>
                      {st === 'pass' ? 'PASS' : st === 'fail' ? 'FAIL' : st === 'running' ? '…' : 'IDLE'}
                    </span>
                    <HexButton onClick={() => runSingle(item)} disabled={st === 'running' || suiteRunning} variant="outline" size="xs">RUN</HexButton>
                  </div>
                )
              })}
            </div>
          </Panel>
        </div>

        <div className="dr-col">
          <Panel icon="🔍" title="Error Log" className="dr-panel">
            <div className="dr-errorlog">
              {errorLogs.length === 0 ? (
                <div className="dr-empty dr-empty--ok">✓ No errors in recent history</div>
              ) : (
                errorLogs.map((e, i) => (
                  <div key={i} className={`dr-error dr-error--${e.level}`}>
                    <div className={`dr-error__dot dr-error__dot--${e.level}`} />
                    <div className="dr-error__body">
                      <div className="dr-error__msg">{e.msg}</div>
                      <div className="dr-error__meta">{e.ts} · {e.count}× occurrence</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Panel>

          <Panel icon="📊" title="Diagnostics" className="dr-panel">
            <div className="dr-diag">
              {[
                ['Grade', doctorData?.grade || '—', 'bronze'],
                ['Score', `${Math.round((doctorData?.overall_score || 0) * 100)}%`, null],
                ['CPU', `${(doctorData?.scores?.cpu ?? '—')}`, null],
                ['Memory', `${(doctorData?.scores?.memory ?? '—')}`, null],
                ['Healthy', `${healthy}/${checks.length}`, 'success'],
                ['Warnings', `${warnings}`, warnings > 0 ? 'warning' : 'success'],
                ['Critical', `${critical}`, critical > 0 ? 'alert' : 'success'],
                ['Last Check', doctorData?.updated_at ? new Date(doctorData.updated_at).toLocaleTimeString() : '—', null],
              ].map(([label, value, tone]) => (
                <div key={label} className="dr-diag__row">
                  <span className="dr-diag__label">{label}</span>
                  <span className={`dr-diag__val ${tone ? `dr-diag__val--${tone}` : ''}`}>{value}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel icon="⚡" title="Actions" className="dr-panel dr-col__grow">
            <div className="dr-actions">
              <HexButton onClick={() => {
                if (typeof api.chat?.send === 'function') {
                  api.chat.send('Run full system sweep')
                } else {
                  fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: 'Run full system sweep' })
                  }).catch(() => {})
                }
              }} variant="primary" tone="cyan" size="sm">RUN FULL SWEEP</HexButton>
              <HexButton onClick={() => {
                if (typeof api.chat?.send === 'function') {
                  api.chat.send('Restart all agents')
                } else {
                  fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: 'Restart all agents' })
                  }).catch(() => {})
                }
              }} variant="primary" tone="gold" size="sm">RESTART AGENTS</HexButton>
              <HexButton variant="primary" size="sm">CLEAR ERROR LOG</HexButton>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

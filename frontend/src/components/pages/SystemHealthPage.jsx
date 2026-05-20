import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../../store/appStore'
import { useSystemStore } from '../../store/systemStore'
import { useLiveData } from '../../hooks/useLiveData'
import './SystemHealthPage.css'

// ── Ring Gauge ──────────────────────────────────────────────────────
const R = 32
const CIRC = 2 * Math.PI * R
const STROKE = 4

function gaugeColor(pct) {
  if (pct >= 80) return 'var(--nx-danger)'
  if (pct >= 60) return 'var(--nx-warning)'
  return 'var(--nx-success)'
}

function RingGauge({ label, value, max = 100, unit = '%', tempMode = false }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const color = tempMode
    ? (value > 75 ? 'var(--nx-danger)' : value > 55 ? 'var(--nx-warning)' : 'var(--nx-success)')
    : gaugeColor(pct)
  const dash = (pct / 100) * CIRC
  const cx = R + STROKE + 2
  const sz = (R + STROKE + 2) * 2

  return (
    <div className="infra-gauge">
      <svg width={sz} height={sz} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={cx} cy={cx} r={R}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={STROKE}
        />
        <circle
          cx={cx} cy={cx} r={R}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={CIRC - dash}
          style={{ transition: 'stroke-dashoffset 0.6s var(--nx-ease), stroke 0.4s' }}
          filter={`drop-shadow(0 0 4px ${color})`}
        />
      </svg>
      <div className="infra-gauge__center">
        <span className="infra-gauge__val">{Math.round(value)}<span className="infra-gauge__unit">{unit}</span></span>
      </div>
      <span className="infra-gauge__label">{label}</span>
    </div>
  )
}

// ── Sparkline ───────────────────────────────────────────────────────
const SPARK_W = 180
const SPARK_H = 60
const SPARK_N = 60

function toPoints(buf) {
  const max = Math.max(...buf, 1)
  return buf.map((v, i) => {
    const x = (i / (SPARK_N - 1)) * SPARK_W
    const y = SPARK_H - (v / max) * (SPARK_H - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function Sparkline({ label, buf, color, current, unit = '%' }) {
  const pts = toPoints(buf)
  const areaBottom = `${SPARK_W},${SPARK_H} 0,${SPARK_H}`
  return (
    <div className="infra-spark">
      <div className="infra-spark__header">
        <span className="infra-spark__label">{label}</span>
        <span className="infra-spark__val" style={{ color }}>{current.toFixed(1)}{unit}</span>
      </div>
      <svg width={SPARK_W} height={SPARK_H} className="infra-spark__svg">
        <defs>
          <linearGradient id={`sg-${label}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon
          points={`${pts} ${areaBottom}`}
          fill={`url(#sg-${label})`}
        />
        <polyline
          points={pts}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  )
}

// ── Process Table ───────────────────────────────────────────────────
const PROCESSES = [
  { name: 'nexus-node',        type: 'SERVER',  cpu: 2.1,  mem: '512 MB',  status: 'RUNNING' },
  { name: 'python-backend',    type: 'AI_SVC',  cpu: 8.4,  mem: '1.2 GB',  status: 'RUNNING' },
  { name: 'agent-coordinator', type: 'AGENT',   cpu: 1.2,  mem: '128 MB',  status: 'RUNNING' },
  { name: 'agent-researcher',  type: 'AGENT',   cpu: 3.7,  mem: '256 MB',  status: 'RUNNING' },
  { name: 'agent-optimizer',   type: 'AGENT',   cpu: 0.8,  mem: '96 MB',   status: 'RUNNING' },
  { name: 'vector-store',      type: 'DB',      cpu: 0.3,  mem: '2.1 GB',  status: 'RUNNING' },
  { name: 'sqlite-audit',      type: 'DB',      cpu: 0.1,  mem: '24 MB',   status: 'RUNNING' },
  { name: 'message-bus',       type: 'IPC',     cpu: 0.2,  mem: '64 MB',   status: 'RUNNING' },
  { name: 'evolution-ctrl',    type: 'AGENT',   cpu: 0.0,  mem: '32 MB',   status: 'IDLE'    },
  { name: 'llm-cache',         type: 'CACHE',   cpu: 0.1,  mem: '384 MB',  status: 'RUNNING' },
]

const TYPE_COLOR = {
  SERVER: 'var(--nx-cyan)',
  AI_SVC: 'var(--nx-gold)',
  AGENT:  'var(--nx-purple)',
  DB:     'var(--nx-success)',
  IPC:    'var(--nx-amber)',
  CACHE:  'var(--nx-text-muted)',
}

const STATUS_COLOR = {
  RUNNING: 'var(--nx-success)',
  IDLE:    'var(--nx-amber)',
  ERROR:   'var(--nx-danger)',
}

const COLS = ['name', 'type', 'cpu', 'mem', 'status']

function ProcessTable() {
  const [sort, setSort] = useState({ col: 'name', asc: true })

  const sorted = [...PROCESSES].sort((a, b) => {
    const va = a[sort.col], vb = b[sort.col]
    const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb))
    return sort.asc ? cmp : -cmp
  })

  const toggle = col => setSort(s => ({ col, asc: s.col === col ? !s.asc : true }))

  const arrow = col => sort.col === col ? (sort.asc ? ' ▲' : ' ▼') : ''

  return (
    <div className="infra-proctable">
      <div className="infra-section-label">PROCESS MONITOR</div>
      <table className="infra-table">
        <thead>
          <tr>
            {COLS.map(c => (
              <th key={c} onClick={() => toggle(c)} className="infra-table__th">
                {c.toUpperCase()}{arrow(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(p => (
            <tr key={p.name} className="infra-table__row">
              <td className="infra-table__name">{p.name}</td>
              <td>
                <span className="infra-type-pill" style={{ color: TYPE_COLOR[p.type], borderColor: TYPE_COLOR[p.type] }}>
                  {p.type}
                </span>
              </td>
              <td className="infra-table__num">{p.cpu.toFixed(1)}%</td>
              <td className="infra-table__num">{p.mem}</td>
              <td>
                <span className="infra-status-pill" style={{ color: STATUS_COLOR[p.status] || 'var(--nx-text-muted)', borderColor: STATUS_COLOR[p.status] || 'var(--nx-text-muted)' }}>
                  {p.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Uptime formatter ─────────────────────────────────────────────────
function fmtUptime(seconds) {
  if (!seconds || isNaN(seconds)) return '—'
  const s = Math.floor(seconds)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${d}d ${h}h ${m}m`
}

// ── System Info Panel ────────────────────────────────────────────────
function SystemInfoPanel({ systemStatus }) {
  const uptime = systemStatus?.uptime ?? 0
  const mode = systemStatus?.mode ?? 'AUTONOMOUS'

  const rows = [
    { label: 'OS',          value: 'Linux 6.17 (Ubuntu 24.04)' },
    { label: 'NODE.JS',     value: 'v22.22.2' },
    { label: 'PYTHON',      value: '3.12.x' },
    { label: 'ARCH',        value: 'x64' },
    { label: 'UPTIME',      value: fmtUptime(uptime) },
    { label: 'MODE',        value: mode },
    { label: 'VERSION',     value: '2.5.0' },
    { label: 'LAST REBOOT', value: '2026-05-14 08:00 UTC' },
  ]

  return (
    <div className="infra-sysinfo">
      <div className="infra-section-label">SYSTEM INFO</div>
      <div className="infra-sysinfo__rows">
        {rows.map(r => (
          <div key={r.label} className="infra-sysinfo__row">
            <span className="infra-sysinfo__key">{r.label}</span>
            <span className="infra-sysinfo__val">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Container Grid ───────────────────────────────────────────────────
const CONTAINERS = [
  { name: 'nexus-node',      port: '8787',  net: 'HTTP/WS', status: 'HEALTHY', uptime: '99.9%' },
  { name: 'python-backend',  port: '18790', net: 'HTTP',    status: 'HEALTHY', uptime: '99.7%' },
  { name: 'vector-store',    port: '—',     net: 'LOCAL',   status: 'HEALTHY', uptime: '100%'  },
  { name: 'message-bus',     port: '—',     net: 'IPC',     status: 'HEALTHY', uptime: '100%'  },
  { name: 'evolution-ctrl',  port: '—',     net: 'LOCAL',   status: 'IDLE',    uptime: '—'     },
  { name: 'sqlite-audit',    port: '—',     net: 'LOCAL',   status: 'HEALTHY', uptime: '100%'  },
]

const CONT_DOT = { HEALTHY: 'var(--nx-success)', IDLE: 'var(--nx-amber)', ERROR: 'var(--nx-danger)' }

// ── System Diagnostics (from old DoctorPage) ─────────────────────────
const DIAG_CHECKS = [
  { id: 'db',       name: 'DB Connection',     endpoint: '/api/health' },
  { id: 'agents',   name: 'Agent Ping',        endpoint: '/api/agents' },
  { id: 'memory',   name: 'Memory Integrity',  endpoint: '/api/brain/status' },
  { id: 'brain',    name: 'Brain Weight Load', endpoint: '/api/brain/status' },
  { id: 'gateway',  name: 'API Gateway',       endpoint: '/api/health' },
  { id: 'fairness', name: 'Fairness Threshold', endpoint: '/api/fairness/status' },
]

function DiagnosticsPanel() {
  const [results, setResults] = useState({})
  const [running, setRunning] = useState(null)
  const [suite,   setSuite]   = useState(false)

  const runOne = useCallback(async (check) => {
    setRunning(check.id)
    setResults(r => ({ ...r, [check.id]: 'running' }))
    try {
      const res = await fetch(check.endpoint)
      setResults(r => ({ ...r, [check.id]: res.ok ? 'ok' : 'err' }))
    } catch {
      setResults(r => ({ ...r, [check.id]: 'err' }))
    } finally {
      setRunning(null)
    }
  }, [])

  const runAll = useCallback(async () => {
    setSuite(true)
    for (const c of DIAG_CHECKS) await runOne(c)
    setSuite(false)
  }, [runOne])

  return (
    <div className="infra-diag-panel">
      <div className="infra-diag-head">
        <span className="infra-diag-title">SYSTEM DIAGNOSTICS</span>
        <button className="infra-diag-runall" onClick={runAll} disabled={suite}>
          {suite ? 'RUNNING…' : 'RUN ALL'}
        </button>
      </div>
      <ul className="infra-diag-list">
        {DIAG_CHECKS.map(c => {
          const st = results[c.id]
          const cls = st === 'ok' ? 'ok' : st === 'err' ? 'err' : st === 'running' ? 'run' : ''
          return (
            <li key={c.id} className={`infra-diag-row infra-diag-row--${cls}`}>
              <span className="infra-diag-dot" />
              <span className="infra-diag-name">{c.name}</span>
              <span className="infra-diag-status">{st === 'ok' ? 'OK' : st === 'err' ? 'FAIL' : st === 'running' ? '…' : 'IDLE'}</span>
              <button
                className="infra-diag-run"
                onClick={() => runOne(c)}
                disabled={running === c.id || suite}
              >RUN</button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ── Emergency Controls (from old ControlCenterPage) ─────────────────
function EmergencyPanel() {
  const [haltConfirm, setHaltConfirm] = useState(false)
  const [halting,     setHalting]     = useState(false)
  const [restarting,  setRestarting]  = useState(false)
  const [recovery,    setRecovery]    = useState(false)

  const doHalt = useCallback(async () => {
    setHalting(true)
    try { await fetch('/api/system/halt', { method: 'POST' }) } catch {/* ignore */}
    finally { setHalting(false); setHaltConfirm(false) }
  }, [])

  const doRestart = useCallback(async () => {
    setRestarting(true)
    try { await fetch('/api/system/restart', { method: 'POST' }) } catch {/* ignore */}
    finally { setRestarting(false) }
  }, [])

  return (
    <div className="infra-emergency-panel">
      <div className="infra-emergency-head">
        <span className="infra-emergency-title">EMERGENCY CONTROLS</span>
        <span className={`infra-emergency-mode ${recovery ? 'on' : ''}`}>
          RECOVERY MODE: {recovery ? 'ON' : 'OFF'}
        </span>
      </div>
      <div className="infra-emergency-actions">
        {!haltConfirm ? (
          <button className="infra-emergency-btn infra-emergency-btn--halt" onClick={() => setHaltConfirm(true)}>
            EMERGENCY HALT
          </button>
        ) : (
          <div className="infra-emergency-confirm">
            <span>HALT ALL AGENTS?</span>
            <button className="infra-emergency-btn infra-emergency-btn--halt" onClick={doHalt} disabled={halting}>
              {halting ? 'HALTING…' : 'CONFIRM'}
            </button>
            <button className="infra-emergency-btn infra-emergency-btn--ghost" onClick={() => setHaltConfirm(false)}>
              CANCEL
            </button>
          </div>
        )}
        <button className="infra-emergency-btn infra-emergency-btn--restart" onClick={doRestart} disabled={restarting}>
          {restarting ? 'RESTARTING…' : 'RESTART SYSTEM'}
        </button>
        <button
          className={`infra-emergency-btn infra-emergency-btn--toggle ${recovery ? 'on' : ''}`}
          onClick={() => setRecovery(v => !v)}
        >
          {recovery ? '◉ RECOVERY MODE ON' : '○ RECOVERY MODE OFF'}
        </button>
      </div>
    </div>
  )
}

function ContainerGrid() {
  return (
    <div className="infra-containers">
      <div className="infra-section-label">SERVICE STATUS</div>
      <div className="infra-containers__grid">
        {CONTAINERS.map(c => (
          <div key={c.name} className="infra-card">
            <span className="infra-card__dot" style={{ background: CONT_DOT[c.status] ?? 'var(--nx-text-muted)', boxShadow: `0 0 6px ${CONT_DOT[c.status] ?? 'transparent'}` }} />
            <div className="infra-card__name">{c.name}</div>
            <div className="infra-card__meta">
              {c.port !== '—' && <span className="infra-card__port">:{c.port}</span>}
              <span className="infra-card__net">{c.net}</span>
            </div>
            <div className="infra-card__row">
              <span className="infra-card__status" style={{ color: CONT_DOT[c.status] }}>
                {c.status}
              </span>
              <span className="infra-card__uptime">{c.uptime}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── SLA Uptime Panel ────────────────────────────────────────────────
function SLAUptimePanel() {
  const { data } = useLiveData({ endpoint: '/api/system/uptime', pollMs: 60000 })
  const { data: sla } = useLiveData({ endpoint: '/api/system/sla', pollMs: 60000 })

  const STUB_SERVICES = [
    { name: 'backend',    uptime_30d: 99.8, uptime_90d: 99.6, incidents_30d: 1, mttr_minutes: 8.2 },
    { name: 'python-ai',  uptime_30d: 99.4, uptime_90d: 98.9, incidents_30d: 2, mttr_minutes: 14.5 },
    { name: 'redis',      uptime_30d: 100,  uptime_90d: 99.9, incidents_30d: 0, mttr_minutes: 0 },
    { name: 'postgres',   uptime_30d: 99.9, uptime_90d: 99.8, incidents_30d: 0, mttr_minutes: 0 },
  ]
  const services = data?.services || STUB_SERVICES
  const currentUptime = sla?.current?.uptime || 99.7
  const errorRate = sla?.current?.error_rate_pct || 0.3
  const p95Lat = sla?.current?.p95_latency_ms || 340

  return (
    <div className="infra-sla-panel">
      <div className="infra-section-label">UPTIME &amp; SLA</div>
      <div className="infra-sla-kpis">
        <div className="infra-sla-kpi">
          <span className="infra-sla-kpi-val" style={{ color: currentUptime >= 99.5 ? 'var(--nx-success)' : 'var(--nx-warning)' }}>
            {currentUptime.toFixed(2)}%
          </span>
          <span className="infra-sla-kpi-label">30-DAY UPTIME</span>
        </div>
        <div className="infra-sla-kpi">
          <span className="infra-sla-kpi-val" style={{ color: errorRate < 1 ? 'var(--nx-success)' : 'var(--nx-danger)' }}>
            {errorRate.toFixed(2)}%
          </span>
          <span className="infra-sla-kpi-label">ERROR RATE</span>
        </div>
        <div className="infra-sla-kpi">
          <span className="infra-sla-kpi-val">{p95Lat}ms</span>
          <span className="infra-sla-kpi-label">P95 LATENCY</span>
        </div>
      </div>
      <div className="infra-sla-table-head">
        <span>SERVICE</span><span>30D</span><span>90D</span><span>INCIDENTS</span><span>MTTR</span>
      </div>
      {services.map(s => (
        <div key={s.name} className="infra-sla-row">
          <span className="infra-sla-name">{s.name}</span>
          <span className={`infra-sla-val ${s.uptime_30d >= 99.5 ? 'infra-sla-val--ok' : 'infra-sla-val--warn'}`}>{s.uptime_30d.toFixed(2)}%</span>
          <span className={`infra-sla-val ${s.uptime_90d >= 99.5 ? 'infra-sla-val--ok' : 'infra-sla-val--warn'}`}>{s.uptime_90d.toFixed(2)}%</span>
          <span className="infra-sla-incidents">{s.incidents_30d}</span>
          <span className="infra-sla-mttr">{s.mttr_minutes > 0 ? `${s.mttr_minutes}m` : '—'}</span>
        </div>
      ))}
    </div>
  )
}

// ── Patch History Panel ─────────────────────────────────────────────────────
function PatchHistoryPanel() {
  const { data } = useLiveData({ endpoint: '/api/system/patches', pollMs: 30000 })

  const STUB_PATCHES = [
    { id: 'p001', component: 'email-writer', description: 'Prompt temperature 0.7→0.4', status: 'applied', applied_at: Date.now() - 86400000 * 5, improvement: '+18% CSAT' },
    { id: 'p002', component: 'data-analyst', description: 'ARR-tier segmentation default', status: 'applied', applied_at: Date.now() - 86400000 * 9, improvement: '+28% accuracy' },
    { id: 'p003', component: 'lead-hunter',  description: 'Warm-lead priority when depth > 40', status: 'applied', applied_at: Date.now() - 86400000 * 12, improvement: '+14% conv' },
    { id: 'p004', component: 'orchestrator', description: 'Retry logic for LLM timeouts > 8s', status: 'rolled_back', applied_at: Date.now() - 86400000 * 3, improvement: null },
  ]
  const patches = data?.patches?.length ? data.patches : STUB_PATCHES

  return (
    <div className="infra-patch-panel">
      <div className="infra-section-label">SELF-EVOLUTION PATCH HISTORY</div>
      {patches.map(p => (
        <div key={p.id} className={`infra-patch-row infra-patch-row--${p.status}`}>
          <div className="infra-patch-head">
            <span className="infra-patch-comp">{p.component}</span>
            <span className={`infra-patch-status infra-patch-status--${p.status}`}>
              {p.status === 'applied' ? '✓ APPLIED' : '↩ ROLLED BACK'}
            </span>
            <span className="infra-patch-date">{new Date(p.applied_at).toLocaleDateString()}</span>
          </div>
          <div className="infra-patch-desc">{p.description}</div>
          {p.improvement && <div className="infra-patch-improvement">{p.improvement}</div>}
        </div>
      ))}
    </div>
  )
}

// ── Log Stream Panel ─────────────────────────────────────────────────────────
function LogStreamPanel() {
  const [logs, setLogs] = useState([])
  const [filter, setFilter] = useState('')
  const [component, setComponent] = useState('all')

  useEffect(() => {
    function onWs(e) {
      if (e.detail?.type === 'system:log' || e.detail?.type === 'system:tick') {
        const d = e.detail.data || {}
        setLogs(prev => [{
          ts: Date.now(),
          level: d.level || 'INFO',
          component: d.component || 'system',
          msg: d.message || d.msg || JSON.stringify(d).slice(0, 120),
        }, ...prev].slice(0, 200))
      }
    }
    window.addEventListener('ws:event', onWs)
    return () => window.removeEventListener('ws:event', onWs)
  }, [])

  const STUB_LOGS = [
    { ts: Date.now() - 500,   level: 'INFO',  component: 'backend',   msg: 'GET /api/agents/list 200 4ms' },
    { ts: Date.now() - 1200,  level: 'INFO',  component: 'python-ai', msg: 'Pipeline phase: execute → format 91ms' },
    { ts: Date.now() - 2800,  level: 'WARN',  component: 'python-ai', msg: 'LLM response time 6.2s exceeds threshold' },
    { ts: Date.now() - 5000,  level: 'INFO',  component: 'agents',    msg: 'lead-hunter-elite: task completed (score 0.87)' },
    { ts: Date.now() - 7200,  level: 'DEBUG', component: 'memory',    msg: 'Vector store: 3 facts retrieved (84ms)' },
    { ts: Date.now() - 10000, level: 'INFO',  component: 'evolution', msg: 'Patch p004 rolled back — accuracy regression' },
    { ts: Date.now() - 14000, level: 'ERROR', component: 'backend',   msg: 'POST /api/forge/sessions 500 timeout' },
  ]
  const displayLogs = logs.length ? logs : STUB_LOGS
  const COMPONENTS = ['all', 'backend', 'python-ai', 'agents', 'memory', 'evolution', 'security']
  const LEVEL_COLOR = { INFO: 'var(--nx-text-muted)', WARN: 'var(--nx-warning)', ERROR: 'var(--nx-danger)', DEBUG: 'var(--nx-text-dim)' }

  const filtered = displayLogs.filter(l =>
    (component === 'all' || l.component === component) &&
    (!filter || l.msg.toLowerCase().includes(filter.toLowerCase()))
  )

  return (
    <div className="infra-log-panel">
      <div className="infra-log-controls">
        <div className="infra-section-label" style={{ flex: 1 }}>LIVE LOG STREAM</div>
        <select className="infra-log-select" value={component} onChange={e => setComponent(e.target.value)}>
          {COMPONENTS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input className="infra-log-filter" placeholder="Filter…" value={filter} onChange={e => setFilter(e.target.value)} />
        <button className="infra-log-clear" onClick={() => setLogs([])}>Clear</button>
      </div>
      <div className="infra-log-stream">
        {filtered.map((l, i) => (
          <div key={i} className="infra-log-row">
            <span className="infra-log-ts">{new Date(l.ts).toLocaleTimeString()}</span>
            <span className="infra-log-level" style={{ color: LEVEL_COLOR[l.level] || 'var(--nx-text-muted)' }}>{l.level}</span>
            <span className="infra-log-comp">{l.component}</span>
            <span className="infra-log-msg">{l.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────────
export default function SystemHealthPage() {
  const systemHealth  = useAppStore(s => s.systemHealth)
  const systemStatus  = useSystemStore(s => s.systemStatus)

  const cpu  = systemHealth?.cpu_percent    ?? 0
  const gpu  = systemHealth?.gpu_percent    ?? 0
  const ram  = systemHealth?.memory_percent ?? 0
  const disk = systemHealth?.disk_percent   ?? 0
  const temp = systemHealth?.gpu_temp       ?? 0
  const net  = systemHealth?.net_mbps       ?? 0

  // Rolling buffers
  const cpuBuf  = useRef(new Array(SPARK_N).fill(0))
  const gpuBuf  = useRef(new Array(SPARK_N).fill(0))
  const ramBuf  = useRef(new Array(SPARK_N).fill(0))
  const netBuf  = useRef(new Array(SPARK_N).fill(0))
  const [tick, setTick] = useState(0)

  // Capture latest values in a ref so the interval always reads current
  const latest = useRef({ cpu, gpu, ram, net })
  useEffect(() => { latest.current = { cpu, gpu, ram, net } }, [cpu, gpu, ram, net])

  useEffect(() => {
    const id = setInterval(() => {
      const { cpu: c, gpu: g, ram: r, net: n } = latest.current
      cpuBuf.current = [...cpuBuf.current.slice(1), c]
      gpuBuf.current = [...gpuBuf.current.slice(1), g]
      ramBuf.current = [...ramBuf.current.slice(1), r]
      netBuf.current = [...netBuf.current.slice(1), n]
      setTick(t => t + 1)
    }, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="infra-page">
      {/* KPI Row */}
      <div className="infra-kpi-row">
        <RingGauge label="CPU"      value={cpu}  unit="%" />
        <RingGauge label="GPU"      value={gpu}  unit="%" />
        <RingGauge label="RAM"      value={ram}  unit="%" />
        <RingGauge label="DISK"     value={disk} unit="%" />
        <RingGauge label="GPU TEMP" value={temp} max={100} unit="°C" tempMode />
      </div>

      {/* Sparkline Row */}
      <div className="infra-spark-row">
        <Sparkline label="CPU LOAD"  buf={cpuBuf.current}  color="var(--nx-gold)"    current={cpu}  unit="%" />
        <Sparkline label="GPU USAGE" buf={gpuBuf.current}  color="var(--nx-cyan)"    current={gpu}  unit="%" />
        <Sparkline label="RAM USAGE" buf={ramBuf.current}  color="var(--nx-purple)"  current={ram}  unit="%" />
        <Sparkline label="NET I/O"   buf={netBuf.current}  color="var(--nx-success)" current={net}  unit=" Mb/s" />
      </div>

      {/* Main split row */}
      <div className="infra-mid-row">
        <ProcessTable />
        <SystemInfoPanel systemStatus={systemStatus} />
      </div>

      {/* Diagnostics + Emergency controls */}
      <div className="infra-ops-row">
        <DiagnosticsPanel />
        <EmergencyPanel />
      </div>

      {/* Container grid */}
      <ContainerGrid />

      {/* SLA + Self-healing */}
      <div className="infra-bottom-row">
        <SLAUptimePanel />
        <PatchHistoryPanel />
      </div>

      {/* Live log stream */}
      <LogStreamPanel />
    </div>
  )
}

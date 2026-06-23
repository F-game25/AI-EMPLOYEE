/**
 * Ascend Forge — Agentic Build Surface
 * Bronze luxury cockpit design with 14-view navigation.
 * Real API integration preserved from original implementation.
 */
import { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import api from '../../api/client'
import { useForgeStore } from '../../store/forgeStore'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import './AscendForgePage.css'
import {
  JPOST, TOKEN, compactId, normalizeAction, isPendingAction,
  canBatchApprove, mergeActionLists
} from './forge/helpers'

/* ── Constants ─────────────────────────────────────────────────── */
const CLOSED_STATUSES = new Set(['staged', 'verified', 'applied', 'verify_failed', 'rejected', 'failed', 'blocked', 'deployed'])

/* ── SVG Icons ─────────────────────────────────────────────────── */
const ICONS = {
  compose:  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12.5V14h1.5L11 6.5 9.5 5 2 12.5z"/><path d="M10 4.5 11.5 3 13 4.5 11.5 6"/></svg>,
  activity: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M1 8h3l2-5 4 10 2-5h3"/></svg>,
  diff:     <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="4" cy="4" r="2"/><circle cx="12" cy="12" r="2"/><path d="M4 6v4a2 2 0 0 0 2 2h4"/><path d="M12 10V6a2 2 0 0 0-2-2H6"/></svg>,
  check:    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 8 3 3 7-7"/></svg>,
  cross:    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3l10 10M13 3 3 13"/></svg>,
  pipeline: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="3" cy="4" r="1.5"/><circle cx="13" cy="4" r="1.5"/><circle cx="3" cy="12" r="1.5"/><circle cx="13" cy="12" r="1.5"/><circle cx="8" cy="8" r="1.5"/><path d="M4.5 4 6.5 7M11.5 4 9.5 7M6.5 9 4.5 12M9.5 9l2 3"/></svg>,
  files:    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h4l1.5 1.5H14V13H2V3z"/></svg>,
  history:  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l2.5 2"/></svg>,
  agents:   <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="5" cy="6" r="2"/><circle cx="11" cy="6" r="2"/><path d="M2 13c0-2 1.5-3 3-3s3 1 3 3M8 13c0-2 1.5-3 3-3s3 1 3 3"/></svg>,
  search:   <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/></svg>,
  settings: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="2"/><path d="M8 1v2M8 13v2M3 8H1M15 8h-2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/></svg>,
  bell:     <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3.5 12h9l-1-2V7a3.5 3.5 0 0 0-7 0v3l-1 2zM6.5 13.5a1.5 1.5 0 0 0 3 0"/></svg>,
  play:     <svg viewBox="0 0 14 14" fill="currentColor"><path d="M3 2v10l9-5z"/></svg>,
  pause:    <svg viewBox="0 0 14 14" fill="currentColor"><rect x="3" y="2" width="3" height="10" rx="0.5"/><rect x="8" y="2" width="3" height="10" rx="0.5"/></svg>,
  spark:    <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M7 1v3M7 10v3M1 7h3M10 7h3M2.5 2.5l2 2M9.5 9.5l2 2M2.5 11.5l2-2M9.5 4.5l2-2"/></svg>,
  send:     <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M1.5 7 13 1.5 7.5 13 6 8z"/></svg>,
  branch:   <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="3" cy="3" r="1.5"/><circle cx="3" cy="11" r="1.5"/><circle cx="11" cy="5.5" r="1.5"/><path d="M3 4.5v5M4 5.5c0 2 4 1.5 6 0"/></svg>,
  more:     <svg viewBox="0 0 14 14" fill="currentColor"><circle cx="3" cy="7" r="1"/><circle cx="7" cy="7" r="1"/><circle cx="11" cy="7" r="1"/></svg>,
  chevron:  <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 2 7 5 3 8"/></svg>,
  folder:   <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M1.5 2.5h3l1 1H10.5v6h-9z"/></svg>,
  file:     <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 1.5h4.5L9.5 3.5V10.5h-6.5z"/></svg>,
  zap:      <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="m7 1-4 7h3l-1 5 4-7H6z" fill="currentColor" fillOpacity="0.15"/></svg>,
  stop:     <svg viewBox="0 0 14 14" fill="currentColor"><rect x="3" y="3" width="8" height="8" rx="1"/></svg>,
  projects: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="5" height="5" rx="1"/><rect x="9" y="3" width="5" height="5" rx="1"/><rect x="2" y="10" width="5" height="4" rx="1"/><rect x="9" y="10" width="5" height="4" rx="1"/></svg>,
  terminal: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h12v9H2z"/><path d="m5 7 2 2-2 2"/><path d="M9 11h3"/></svg>,
}

function Icon({ name, size = 16, style }) {
  const ic = ICONS[name]
  if (!ic) return null
  return <svg width={size} height={size} viewBox={ic.props.viewBox} fill={ic.props.fill} stroke={ic.props.stroke} strokeWidth={ic.props.strokeWidth} strokeLinecap={ic.props.strokeLinecap} strokeLinejoin={ic.props.strokeLinejoin} style={style}>
    {ic.props.children}
  </svg>
}

/* ── Design primitives ─────────────────────────────────────────── */
function Panel({ title, sub, icon, tone, actions, footer, flush, padding, children, style, headSize }) {
  const cls = ['af2-panel', tone ? `af2-panel--${tone}` : ''].filter(Boolean).join(' ')
  return (
    <div className={cls} style={style}>
      <span className="af2-tick af2-tick--tl"/>
      <span className="af2-tick af2-tick--tr"/>
      <span className="af2-tick af2-tick--bl"/>
      <span className="af2-tick af2-tick--br"/>
      {(title || actions) && (
        <div className={`af2-panel-head${headSize === 'lg' ? ' af2-panel-head--lg' : ''}`}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            {icon && <span style={{ color: 'var(--af2-bronze-bright)', display: 'inline-flex' }}><Icon name={icon} size={14}/></span>}
            {title && <span className="af2-label">{title}</span>}
            {sub && <span style={{ font: '500 9.5px var(--af2-mono)', letterSpacing: '0.10em', color: 'var(--af2-muted)', marginLeft: 4 }}>{sub}</span>}
          </div>
          {actions && <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>{actions}</div>}
        </div>
      )}
      <div className={`af2-panel-body${flush ? ' af2-panel-body--flush' : ''}`} style={{ padding: flush ? 0 : (padding ?? '14px 16px') }}>
        {children}
      </div>
      {footer && <div className="af2-panel-foot">{footer}</div>}
    </div>
  )
}

function Pill({ tone = 'bronze', dot = true, pulse = true, children, sm, style }) {
  return (
    <span className={['af2-pill', tone !== 'bronze' ? `af2-pill--${tone}` : '', sm ? 'af2-pill--sm' : ''].filter(Boolean).join(' ')} style={style}>
      {dot && <span className={`af2-pill-dot${pulse ? ' af2-pill-dot--pulse' : ''}`}/>}
      {children}
    </span>
  )
}

function Hex({ tone, size, glow, children, style, onClick }) {
  return (
    <span className={['af2-hex', size ? `af2-hex--${size}` : '', tone ? `af2-hex--${tone}` : '', glow ? 'af2-hex--glow' : ''].filter(Boolean).join(' ')} style={style} onClick={onClick}>
      {children}
    </span>
  )
}

function Btn({ variant, sm, lg, children, icon, style, onClick, disabled, title }) {
  return (
    <button className={['af2-btn', variant ? `af2-btn--${variant}` : '', sm ? 'af2-btn--sm' : '', lg ? 'af2-btn--lg' : ''].filter(Boolean).join(' ')} style={style} onClick={onClick} disabled={disabled} title={title}>
      {icon && <Icon name={icon} size={sm ? 12 : 14}/>}
      {children}
    </button>
  )
}

function IconBtn({ icon, active, onClick, title, style, size }) {
  return (
    <button className={`af2-iconbtn${active ? ' af2-iconbtn--active' : ''}`} style={style} onClick={onClick} title={title}>
      <Icon name={icon} size={size || 14}/>
    </button>
  )
}

function Spark({ data = [], color = '#CD7F32', h = 14, w = 60, fill }) {
  if (!data.length) return null
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 2) - 1}`).join(' ')
  return (
    <svg width={w} height={h}>
      {fill && <polygon points={`0,${h} ${pts} ${w},${h}`} fill={color} fillOpacity="0.16"/>}
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

function RingMeter({ value, max = 100, label, sub, color = 'var(--af2-bronze)', size = 70, thickness = 4 }) {
  const r = (size - thickness) / 2, c = 2 * Math.PI * r, pct = Math.min(1, value / max)
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(205,127,50,0.10)" strokeWidth={thickness}/>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={thickness} strokeDasharray={`${c * pct} ${c}`} strokeLinecap="round" style={{ filter: 'drop-shadow(0 0 6px rgba(205,127,50,0.5))', transition: 'stroke-dasharray 0.4s ease-out' }}/>
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
        <div style={{ font: '600 14px var(--af2-mono)', color: 'var(--af2-text)', lineHeight: 1 }}>{label}</div>
        {sub && <div style={{ font: '500 8.5px var(--af2-mono)', letterSpacing: '0.08em', color: 'var(--af2-muted)', marginTop: 3, textTransform: 'uppercase' }}>{sub}</div>}
      </div>
    </div>
  )
}

function Risk({ level }) {
  const map = { safe: 'SAFE', review: 'REVIEW', gated: 'GATED' }
  return <span className={`af2-risk af2-risk--${level}`}>{map[level] || level}</span>
}

/* ── Deterministic mini charts ─────────────────────────────────── */
function stableSpark({ len = 24, base = 50, amp = 30, seed = 0 }) {
  return Array.from({ length: len }, (_, i) => Math.max(0, base + Math.sin((i + seed) * 0.55) * amp))
}

function idxFromId(id = '') {
  return String(id).split('').reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % 17
}

function useClock() {
  const [d, setD] = useState(new Date())
  useEffect(() => { const t = setInterval(() => setD(new Date()), 1000); return () => clearInterval(t) }, [])
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/* ── ForgeMark ─────────────────────────────────────────────────── */
function ForgeMark({ size = 32 }) {
  return (
    <div style={{
      width: size, height: size, flexShrink: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(180deg, rgba(205,127,50,0.18) 0%, rgba(139,90,43,0.10) 100%)',
      border: '1px solid rgba(205,127,50,0.42)',
      clipPath: 'polygon(7px 0%, calc(100% - 7px) 0%, 100% 7px, 100% calc(100% - 7px), calc(100% - 7px) 100%, 7px 100%, 0% calc(100% - 7px), 0% 7px)',
      boxShadow: 'inset 0 0 12px rgba(205,127,50,0.20), 0 0 14px rgba(205,127,50,0.25)',
    }}>
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 20 20" fill="none">
        <defs>
          <linearGradient id="afm2" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#E89A4F"/>
            <stop offset="1" stopColor="#8B5A2B"/>
          </linearGradient>
        </defs>
        <polygon points="10,2 16,12 4,12" stroke="url(#afm2)" strokeWidth="1.4" fill="rgba(205,127,50,0.1)"/>
        <rect x="3" y="14" width="14" height="2" rx="0.5" fill="url(#afm2)"/>
        <line x1="6" y1="11" x2="14" y2="11" stroke="#FFD97A" strokeWidth="0.6" opacity="0.6"/>
      </svg>
    </div>
  )
}

/* ── TopBar ────────────────────────────────────────────────────── */
function ForgeTopBar({ activeView, project, runState, onToggleRun, onPaletteOpen, pendingCount }) {
  const time = useClock()
  const normalizedRunState = String(runState || 'idle').toLowerCase()
  const running = ['running', 'planning', 'testing', 'executing', 'in_progress', 'agentic', 'reviewing'].includes(normalizedRunState)
  const paused = normalizedRunState === 'paused'
  const runnable = running || paused
  return (
    <header className="af2-topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <ForgeMark/>
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
            <span style={{ font: '700 12.5px var(--af2-sans)', letterSpacing: '0.14em', color: 'var(--af2-text)' }}>ASCEND FORGE</span>
            <span style={{ font: '500 9px var(--af2-mono)', letterSpacing: '0.12em', color: 'var(--af2-faint)' }}>v2.4</span>
          </div>
          <div style={{ font: '500 8.5px var(--af2-mono)', letterSpacing: '0.18em', color: 'var(--af2-faint)', marginTop: 1, textTransform: 'uppercase' }}>AGENTIC BUILD SURFACE</div>
        </div>
      </div>

      <div className="af2-divider-v"/>

      {project && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ font: '500 9px var(--af2-mono)', letterSpacing: '0.18em', color: 'var(--af2-faint)', textTransform: 'uppercase' }}>PROJECT</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px', background: 'rgba(205,127,50,0.06)', border: '1px solid rgba(205,127,50,0.18)', borderRadius: 4 }}>
            <Icon name="branch" size={12} style={{ color: 'var(--af2-bronze-bright)' }}/>
            <span style={{ font: '600 11.5px var(--af2-sans)', color: 'var(--af2-text)' }}>{project.name || project.id}</span>
          </div>
        </div>
      )}

      <button onClick={onPaletteOpen} className="af2-search-pill">
        <Icon name="search" size={13}/>
        <span style={{ flex: 1 }}>Ask · build · search…</span>
        <span className="af2-kbd">⌘K</span>
      </button>

      <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginLeft: 'auto' }}>
        <div className="af2-kpi">
          <div className="af2-kpi-label">RUN</div>
          <div className="af2-kpi-value" style={{ color: 'var(--af2-bronze-bright)' }}>{time}</div>
        </div>
        <div className="af2-divider-v"/>
        <div className="af2-kpi">
          <div className="af2-kpi-label">QUEUE</div>
          <div className="af2-kpi-value" style={{ color: pendingCount > 0 ? '#F59E0B' : 'var(--af2-secondary)' }}>{pendingCount}</div>
        </div>
      </div>

      <div className="af2-divider-v"/>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Pill tone={running ? 'success' : paused ? 'warn' : 'idle'}>
          {running ? 'LIVE' : paused ? 'PAUSED' : (normalizedRunState === 'idle' ? 'IDLE' : normalizedRunState.toUpperCase())}
        </Pill>
        <Btn variant="ghost" sm icon={running ? 'pause' : 'play'} onClick={onToggleRun} disabled={!runnable} title={runnable ? undefined : 'No backend run can be controlled right now'}>
          {running ? 'Pause' : paused ? 'Resume' : 'No Run'}
        </Btn>
        <IconBtn icon="settings" title="Settings"/>
      </div>
    </header>
  )
}

/* ── Left Rail ─────────────────────────────────────────────────── */
const VIEWS = [
  { id: 'projects', icon: 'projects', label: 'Projects' },
  { id: 'compose',  icon: 'compose',  label: 'Compose'  },
  { id: 'queue',    icon: 'bell',     label: 'Queue'    },
  { id: 'activity', icon: 'activity', label: 'Activity' },
  { id: 'review',   icon: 'diff',     label: 'Review'   },
  { id: 'approvals',icon: 'check',    label: 'Approvals'},
  { id: 'pipeline', icon: 'pipeline', label: 'Pipeline' },
  { id: 'v5_project', icon: 'spark', label: 'V5 Project' },
  { id: 'v5_goals', icon: 'branch', label: 'V5 Goals' },
  { id: 'v5_reasoning', icon: 'search', label: 'V5 Reasoning' },
  { id: 'v5_quality', icon: 'check', label: 'V5 Quality' },
  { id: 'v7_execution', icon: 'zap', label: 'V7 Execute' },
  { id: 'github', icon: 'branch', label: 'GitHub' },
  { id: 'files',    icon: 'files',    label: 'Files'    },
  { id: 'history',  icon: 'history',  label: 'History'  },
  { id: 'agents',   icon: 'agents',   label: 'Agents'   },
  { id: 'terminal', icon: 'terminal', label: 'Terminal' },
]

function LeftRail({ active, onChange, pendingCount }) {
  return (
    <nav className="af2-rail">
      {VIEWS.map((v, i) => (
        <button key={v.id} className={`af2-rail-item${active === v.id ? ' af2-rail-item--active' : ''}`} onClick={() => onChange(v.id)} title={v.label}>
          <Icon name={v.icon} size={17}/>
          {(v.id === 'approvals' || v.id === 'queue') && pendingCount > 0 && (
            <span className="af2-rail-badge">{pendingCount}</span>
          )}
          <span className="af2-rail-tip">{v.label}<span style={{ marginLeft: 8, opacity: 0.5, font: '500 8px var(--af2-mono)' }}>{i + 1}</span></span>
        </button>
      ))}
      <div style={{ flex: 1 }}/>
    </nav>
  )
}

/* ── Command Palette ───────────────────────────────────────────── */
function CommandPalette({ onClose, onSelectView }) {
  const [q, setQ] = useState('')
  const inputRef = useRef(null)
  useEffect(() => { inputRef.current?.focus() }, [])

  const commands = [
    ...VIEWS.map(v => ({ id: `view:${v.id}`, icon: v.icon, label: `Go to ${v.label}`, sub: 'View', action: () => onSelectView(v.id) })),
    { id: 'new-goal', icon: 'compose', label: 'New goal · Forge plan', sub: 'Action', action: () => onSelectView('compose') },
  ]
  const filtered = commands.filter(c => c.label.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="af2-palette-overlay" onClick={onClose}>
      <div className="af2-panel af2-palette" onClick={e => e.stopPropagation()}>
        <span className="af2-tick af2-tick--tl"/><span className="af2-tick af2-tick--tr"/>
        <span className="af2-tick af2-tick--bl"/><span className="af2-tick af2-tick--br"/>
        <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(205,127,50,0.10)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icon name="search" size={16} style={{ color: 'var(--af2-bronze-bright)', flexShrink: 0 }}/>
          <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)} placeholder="Type a command or search…" className="af2-palette-input"/>
          <span className="af2-kbd">ESC</span>
        </div>
        <div style={{ overflow: 'auto', flex: 1 }}>
          {filtered.map(c => (
            <div key={c.id} className="af2-row" onClick={c.action}>
              <Hex tone="bronze" size="sm"><Icon name={c.icon} size={12}/></Hex>
              <span style={{ flex: 1, font: '500 12.5px var(--af2-sans)', color: 'var(--af2-text)' }}>{c.label}</span>
              <span style={{ font: '500 9.5px var(--af2-mono)', letterSpacing: '0.10em', color: 'var(--af2-faint)', textTransform: 'uppercase' }}>{c.sub}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Projects View ─────────────────────────────────────────────── */
function ProjectsView({ onSelect, onNew }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [focused, setFocused] = useState(null)
  const [togglingWrite, setTogglingWrite] = useState(false)

  const reload = () => {
    fetch('/api/forge/projects', { headers: TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {} })
      .then(r => r.ok ? r.json() : [])
      .then(d => {
        const list = Array.isArray(d) ? d : d.projects || []
        setProjects(list)
        setFocused(f => f ? (list.find(p => p.id === f.id) || f) : f)
      })
      .catch(() => setProjects([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { reload() }, [])

  const toggleWriteAccess = async (p) => {
    setTogglingWrite(true)
    try {
      const r = await fetch(`/api/forge/projects/${p.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...(TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {}) },
        body: JSON.stringify({ write_access: !p.write_access }),
      })
      const d = await r.json()
      if (!r.ok) { toastError(d.error || 'Failed to update'); return }
      toastSuccess(`Write access ${d.project.write_access ? 'enabled' : 'disabled'}`)
      reload()
    } catch (e) { toastError(e.message) }
    finally { setTogglingWrite(false) }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Projects" icon="projects" sub={`${projects.length}`}
        actions={<Btn variant="primary" sm icon="compose" onClick={onNew}>New project</Btn>} flush>
        <div style={{ overflow: 'auto', height: '100%' }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--af2-muted)' }}>Loading projects…</div>
          ) : projects.length === 0 ? (
            <div style={{ padding: 60, textAlign: 'center' }}>
              <div style={{ display: 'inline-flex', marginBottom: 14 }}><Hex tone="gold" size="lg" glow><Icon name="projects" size={22}/></Hex></div>
              <div style={{ font: '600 14px var(--af2-sans)', color: 'var(--af2-text)', marginBottom: 4 }}>No projects yet</div>
              <div style={{ font: '400 12px var(--af2-sans)', color: 'var(--af2-muted)', marginBottom: 16 }}>Create your first agentic project to get started.</div>
              <Btn variant="primary" onClick={onNew}>Create project</Btn>
            </div>
          ) : projects.map(p => (
            <div key={p.id} className="af2-row" style={{ background: focused?.id === p.id ? 'rgba(205,127,50,0.05)' : undefined, borderLeft: focused?.id === p.id ? '2px solid var(--af2-bronze)' : '2px solid transparent' }}
              onClick={() => setFocused(p)}>
              <Hex tone={p.write_access ? 'bronze' : 'idle'}><Icon name="branch" size={14}/></Hex>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ font: '600 13px var(--af2-sans)', color: 'var(--af2-text)' }}>{p.name || p.id}</div>
                <div style={{ font: '400 11px var(--af2-mono)', color: 'var(--af2-muted)', marginTop: 2 }}>{p.write_access ? 'writable' : 'read-only'} · {p.template || p.package_type || 'project'}</div>
              </div>
              <Btn variant="primary" sm onClick={e => { e.stopPropagation(); onSelect(p) }}>Open</Btn>
            </div>
          ))}
        </div>
      </Panel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {focused ? (
          <Panel title={focused.name} sub={focused.id ? compactId(focused.id) : ''} tone="gold">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <CapRow label="Template" value={focused.template || focused.package_type || '—'}/>
              <CapRow label="Write access" value={focused.write_access ? 'Yes' : 'No'}/>
              <CapRow label="Policy" value={focused.policy_profile || '—'}/>
              <div style={{ height: 1, background: 'var(--af2-border)', margin: '4px 0' }}/>
              <Btn variant={focused.write_access ? 'ghost' : 'primary'} sm
                disabled={togglingWrite}
                onClick={() => toggleWriteAccess(focused)}
                style={{ width: '100%', justifyContent: 'center' }}>
                {togglingWrite ? 'Updating…' : focused.write_access ? 'Disable write access' : 'Enable write access'}
              </Btn>
              <Btn variant="primary" sm onClick={() => onSelect(focused)} style={{ width: '100%', justifyContent: 'center' }}>
                Open in Forge
              </Btn>
            </div>
          </Panel>
        ) : (
          <Panel title="Forge capacity" tone="gold">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <CapRow label="Projects" value={`${projects.length}`}/>
              <CapRow label="Backend" value="Ready"/>
              <CapRow label="Provider" value="Anthropic"/>
            </div>
          </Panel>
        )}
      </div>
    </div>
  )
}

function CapRow({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ font: '500 10px var(--af2-mono)', letterSpacing: '0.10em', color: 'var(--af2-muted)', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ font: '500 12px var(--af2-mono)', color: 'var(--af2-text)' }}>{value}</span>
    </div>
  )
}

/* ── New Project Modal ─────────────────────────────────────────── */
function NewProjectModal({ onClose, onCreate }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!name.trim()) return
    setBusy(true)
    try {
      const r = await JPOST('/api/forge/projects', { name: name.trim(), description: desc.trim(), template: 'web-app' })
      const d = await r.json()
      onCreate(d)
      onClose()
    } catch (e) {
      toastError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="af2-palette-overlay" onClick={onClose}>
      <div className="af2-panel" style={{ width: 480 }} onClick={e => e.stopPropagation()}>
        <span className="af2-tick af2-tick--tl"/><span className="af2-tick af2-tick--tr"/>
        <span className="af2-tick af2-tick--bl"/><span className="af2-tick af2-tick--br"/>
        <div className="af2-panel-head">
          <span className="af2-label">New Project</span>
          <IconBtn icon="cross" onClick={onClose}/>
        </div>
        <div className="af2-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <div className="af2-label-plain" style={{ marginBottom: 6 }}>PROJECT NAME</div>
            <input value={name} onChange={e => setName(e.target.value)} className="af2-input" placeholder="my-project" onKeyDown={e => e.key === 'Enter' && submit()}/>
          </div>
          <div>
            <div className="af2-label-plain" style={{ marginBottom: 6 }}>DESCRIPTION</div>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} className="af2-input" placeholder="What are you building?" style={{ minHeight: 80, resize: 'vertical' }}/>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" icon="compose" onClick={submit} disabled={!name.trim() || busy}>{busy ? 'Creating…' : 'Create project'}</Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Compose View ──────────────────────────────────────────────── */
function ComposeView({ project, onSubmit, onAutoRun, onSwitchProject }) {
  const [goal, setGoal] = useState('')
  const [mode, setMode] = useState('balanced')
  const [autoApprove, setAutoApprove] = useState('safe')
  const [runMode, setRunMode] = useState('supervised') // 'supervised' | 'auto'
  const textRef = useRef(null)

  useEffect(() => { textRef.current?.focus() }, [])

  const templates = [
    { id: 'feat', icon: 'spark', label: 'New feature', sub: 'Plan → scaffold → test' },
    { id: 'bug', icon: 'zap', label: 'Bug hunt', sub: 'Repro → root cause → fix' },
    { id: 'refac', icon: 'branch', label: 'Refactor', sub: 'Map blast radius first' },
    { id: 'migr', icon: 'pipeline', label: 'Migration', sub: 'Schema + data + rollback' },
  ]

  const handleSubmit = () => {
    if (!goal.trim() || !project) return
    if (runMode === 'auto') onAutoRun(goal, { mode, autoApprove })
    else onSubmit(goal, { mode, autoApprove })
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 14, height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
        <Panel title="Forge a Goal" icon="compose" headSize="lg"
          actions={<>
            {project && <Pill tone="gold" pulse={false}>{project.name}</Pill>}
            {!project && <Btn variant="ghost" sm onClick={onSwitchProject}>Select project</Btn>}
          </>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ position: 'relative', background: 'rgba(8,6,4,0.6)', border: '1px solid rgba(205,127,50,0.20)', borderRadius: 6, padding: 16, minHeight: 200 }}>
              <textarea ref={textRef} value={goal} onChange={e => setGoal(e.target.value)}
                placeholder="Describe what to forge…  e.g. Add a Stripe webhook that records refunds in the payments table, with tests and observability."
                style={{ width: '100%', minHeight: 160, resize: 'vertical', background: 'transparent', border: 'none', outline: 'none', color: 'var(--af2-text)', font: '400 14px/1.6 var(--af2-sans)' }}
                onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); handleSubmit() } }}
              />
              <div style={{ position: 'absolute', bottom: 10, right: 12, display: 'flex', gap: 10, font: '500 10px var(--af2-mono)', color: 'var(--af2-faint)', letterSpacing: '0.08em' }}>
                <span>{goal.length} CHARS</span>
                <span style={{ color: 'var(--af2-dim)' }}>·</span>
                <span>~{Math.ceil(goal.length / 3.6)} TOKENS</span>
              </div>
            </div>

            {/* Run mode toggle */}
            <div style={{ display: 'flex', gap: 0, background: 'rgba(205,127,50,0.06)', border: '1px solid rgba(205,127,50,0.18)', borderRadius: 6, overflow: 'hidden' }}>
              {[['supervised', 'Supervised', 'Plan & propose — you approve each action'], ['auto', 'Full Auto', 'Planner → Coder → Tester loop — runs end to end']].map(([id, label, desc]) => (
                <button key={id} onClick={() => setRunMode(id)}
                  style={{ flex: 1, padding: '10px 14px', background: runMode === id ? 'rgba(205,127,50,0.18)' : 'transparent', border: 'none', borderRight: id === 'supervised' ? '1px solid rgba(205,127,50,0.18)' : 'none', cursor: 'pointer', textAlign: 'left' }}>
                  <div style={{ font: `600 11px var(--af2-mono)`, color: runMode === id ? 'var(--af2-bronze-bright)' : 'var(--af2-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{label}</div>
                  <div style={{ font: '400 10px var(--af2-sans)', color: 'var(--af2-muted)', marginTop: 2 }}>{desc}</div>
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              {runMode === 'supervised' && (
                <>
                  <div>
                    <div className="af2-label-plain" style={{ marginBottom: 6 }}>EXECUTION MODE</div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {['precise', 'balanced', 'speed'].map(m => (
                        <button key={m} onClick={() => setMode(m)} className={`af2-mode-btn${mode === m ? ' af2-mode-btn--active' : ''}`}>{m}</button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="af2-label-plain" style={{ marginBottom: 6 }}>AUTO-APPROVE</div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {[['none', 'None'], ['safe', 'Safe ops'], ['review', '+Review']].map(([id, lbl]) => (
                        <button key={id} onClick={() => setAutoApprove(id)} className={`af2-mode-btn${autoApprove === id ? ' af2-mode-btn--active' : ''}`}>{lbl}</button>
                      ))}
                    </div>
                  </div>
                </>
              )}
              {runMode === 'auto' && (
                <div style={{ font: '400 11px var(--af2-sans)', color: 'var(--af2-muted)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: '#FCA5A5', font: '600 10px var(--af2-mono)' }}>⚠</span>
                  Full Auto writes files and runs tests without per-action approval. Snapshots are taken before every write.
                </div>
              )}
              <div style={{ flex: 1 }}/>
              <Btn variant={runMode === 'auto' ? 'danger' : 'primary'} icon={runMode === 'auto' ? 'zap' : 'send'} lg onClick={handleSubmit} disabled={!goal.trim() || !project}>
                {runMode === 'auto' ? 'Run auto' : 'Forge plan'}
                <span style={{ marginLeft: 4, padding: '1px 5px', background: 'rgba(0,0,0,0.20)', borderRadius: 3, font: '600 9.5px var(--af2-mono)' }}>⌘↵</span>
              </Btn>
            </div>
          </div>
        </Panel>

        <Panel title="Start from a template" sub="quickstarts"
          actions={<Btn variant="ghost" sm>Browse library</Btn>}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            {templates.map(t => (
              <button key={t.id} className="af2-template-card" onClick={() => setGoal(g => g || t.label)}>
                <Hex tone="bronze" size="sm"><Icon name={t.icon} size={13}/></Hex>
                <div style={{ font: '600 11.5px var(--af2-sans)', color: 'var(--af2-text)', letterSpacing: '0.02em' }}>{t.label}</div>
                <div style={{ font: '500 10px var(--af2-mono)', color: 'var(--af2-muted)' }}>{t.sub}</div>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Panel title="Hotkeys" sub="cheat sheet">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              { k: '⌘K', desc: 'Command palette' },
              { k: '⌘↵', desc: 'Submit' },
              { k: 'A', desc: 'Approve highlighted' },
              { k: 'X', desc: 'Reject' },
              { k: '1-9', desc: 'Switch view' },
            ].map(h => (
              <div key={h.k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ font: '500 11px var(--af2-sans)', color: 'var(--af2-secondary)' }}>{h.desc}</span>
                <span className="af2-kbd">{h.k}</span>
              </div>
            ))}
          </div>
        </Panel>
        {runMode === 'auto' && (
          <Panel title="Full Auto pipeline" tone="gold">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {['Planner agent', 'Coder agent', 'Security scan', 'Test runner', 'Debug retry (×3)'].map((step, i) => (
                <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ font: '600 10px var(--af2-mono)', color: 'var(--af2-bronze)', width: 16, textAlign: 'right' }}>{i + 1}</span>
                  <span style={{ font: '400 11.5px var(--af2-sans)', color: 'var(--af2-text)' }}>{step}</span>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </div>
    </div>
  )
}

/* ── Activity View ─────────────────────────────────────────────── */
const _STRATEGY_LABEL = {
  local_tiny:      { label: 'Fast · Local',    color: '#4ADE80' },
  local_general:   { label: 'General · Local', color: '#4ADE80' },
  local_reasoning: { label: 'Reasoning · Local', color: '#60A5FA' },
  local_coder:     { label: 'Coder · Local',   color: '#A78BFA' },
  openrouter_free: { label: 'Cloud · Free',    color: '#F59E0B' },
  rent_gpu:        { label: 'Remote GPU',      color: '#F87171' },
}

function ComputePlanBadge({ plan, executed }) {
  if (!plan && !executed) return null
  const meta = plan ? (_STRATEGY_LABEL[plan.strategy] || { label: plan.strategy, color: '#94a3b8' }) : null
  const egress = !!executed?.egress
  const ranVia = executed ? (executed.provider || 'local') : null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 6, border: '1px solid rgba(255,255,255,0.08)', marginBottom: 8, flexShrink: 0, flexWrap: 'wrap' }}>
      {plan && <>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: meta.color, flexShrink: 0 }}/>
        <span style={{ font: '600 10px var(--af2-mono)', color: meta.color }}>{meta.label}</span>
        <span style={{ font: '500 10px var(--af2-mono)', color: 'var(--af2-muted)' }}>·</span>
        <span style={{ font: '500 10px var(--af2-mono)', color: 'var(--af2-text)', opacity: 0.8 }}>{plan.model}</span>
      </>}
      {executed && <span style={{ font: '600 9px var(--af2-mono)', color: egress ? '#f87171' : '#34d399', marginLeft: plan ? 8 : 0 }}>
        {'▶'} ran {executed.model} · {ranVia}{egress ? ' · EGRESS' : ' · local'}
      </span>}
      {executed?.approval_request_id && <span style={{ font: '600 9px var(--af2-mono)', color: '#fbbf24' }}>· rent approval pending</span>}
      <span style={{ font: '500 9px var(--af2-mono)', color: 'var(--af2-muted)', marginLeft: 'auto' }}>{executed?.rationale || plan?.rationale}</span>
    </div>
  )
}

function ActivityView({ messages, termLines, sending, agents, computePlan, executedRoute }) {
  const activitySpark = stableSpark({ len: 28, base: Math.max(10, messages.length + termLines.length), amp: Math.max(4, agents.length * 8), seed: messages.length })
  const logRef = useRef(null)
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages, termLines])

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Live activity" icon="activity" sub={`${messages.length} events`} flush>
        <div style={{ padding: '8px 12px 0' }}><ComputePlanBadge plan={computePlan} executed={executedRoute}/></div>
        <div ref={logRef} className="af2-log" style={{ flex: 1, overflow: 'auto' }}>
          {messages.map((m, i) => (
            <div key={i} className={`af2-log-line${m.role === 'assistant' ? ' af2-log-line--ai' : ''}`}>
              <span className="af2-log-agent">{m.role === 'assistant' ? 'FORGE' : 'USER'}</span>
              <span className="af2-log-msg">{typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}</span>
            </div>
          ))}
          {termLines.slice(-30).map((l, i) => (
            <div key={`t${i}`} className={`af2-log-line af2-log-line--${l.type}`}>
              <span className="af2-log-agent">SYS</span>
              <span className="af2-log-msg">{l.text}</span>
            </div>
          ))}
          {sending && (
            <div className="af2-log-line af2-log-line--ai">
              <span className="af2-log-agent">FORGE</span>
              <span className="af2-log-msg" style={{ color: 'var(--af2-bronze-bright)' }}>Thinking<span className="af2-caret"/></span>
            </div>
          )}
        </div>
      </Panel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Panel title="Agent presence" sub={`${agents.length}`} flush>
          <div style={{ overflow: 'auto' }}>
            {agents.map(a => (
              <div key={a.id} className="af2-row" style={{ padding: '10px 14px' }}>
                <Hex tone="bronze" size="sm"><span style={{ font: '700 10px var(--af2-sans)' }}>{a.name[0]}</span></Hex>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ font: '600 11.5px var(--af2-sans)', color: 'var(--af2-text)' }}>{a.name}</div>
                  <div style={{ font: '500 9.5px var(--af2-mono)', color: 'var(--af2-muted)', marginTop: 2 }}>{a.task || a.model}</div>
                </div>
                <Pill tone={a.status === 'running' ? 'success' : 'idle'} sm>{a.status || 'ready'}</Pill>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Token flow" tone="gold">
          <Spark data={activitySpark} color="#E89A4F" w={252} h={48} fill/>
        </Panel>
      </div>
    </div>
  )
}

/* ── Review View ───────────────────────────────────────────────── */
function ReviewView({ actions, onApprove, onReject }) {
  const pending = actions.filter(a => {
    const n = normalizeAction(a)
    return isPendingAction(n) && !CLOSED_STATUSES.has((n.status || '').toLowerCase())
  })

  if (pending.length === 0) {
    return (
      <Panel title="Review" icon="diff" style={{ height: '100%' }}>
        <div style={{ padding: 60, textAlign: 'center' }}>
          <div style={{ display: 'inline-flex', marginBottom: 14 }}><Hex tone="gold" size="lg" glow><Icon name="check" size={22}/></Hex></div>
          <div style={{ font: '600 14px var(--af2-sans)', color: 'var(--af2-text)', marginBottom: 4 }}>Nothing to review</div>
          <div style={{ font: '400 12px var(--af2-sans)', color: 'var(--af2-muted)' }}>All clear — forge something new.</div>
        </div>
      </Panel>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Pending review" icon="diff" sub={`${pending.length}`} flush>
        <div style={{ overflow: 'auto', height: '100%' }}>
          {pending.map(a => {
            const n = normalizeAction(a)
            return (
              <div key={n.id || n.action_id} style={{ padding: '16px 18px', borderBottom: '1px solid rgba(205,127,50,0.06)' }}>
                <div style={{ display: 'flex', gap: 10, justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                      <Risk level={n.risk_level === 'high' ? 'gated' : n.risk_level === 'medium' ? 'review' : 'safe'}/>
                      <span style={{ font: '600 9px var(--af2-mono)', padding: '1px 5px', background: 'rgba(205,127,50,0.12)', color: 'var(--af2-bronze-bright)', border: '1px solid rgba(205,127,50,0.24)', borderRadius: 2 }}>
                        {(n.type || n.action_type || 'ACTION').toUpperCase()}
                      </span>
                    </div>
                    <div style={{ font: '600 13px var(--af2-sans)', color: 'var(--af2-text)', marginBottom: 4 }}>{n.description || n.title || n.content || 'Action pending review'}</div>
                    {n.path && (
                      <div style={{ font: '500 11px var(--af2-mono)', color: 'var(--af2-secondary)', marginTop: 4 }}>{n.path}</div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <Btn variant="danger" sm icon="cross" onClick={() => onReject(n)}>Reject</Btn>
                    <Btn variant="success" sm icon="check" onClick={() => onApprove(n)}>Approve</Btn>
                  </div>
                </div>
                {n.diff && (
                  <div className="af2-diff" style={{ marginTop: 12, maxHeight: 200, overflow: 'auto', borderRadius: 5 }}>
                    {n.diff.split('\n').map((line, li) => (
                      <div key={li} className={`af2-diff-row af2-diff-row--${line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : 'ctx'}`}>
                        <span className="af2-diff-line">{line}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Panel>
      <Panel title="Policy" sub="auto-approval rules">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[
            { label: 'Edits in tested files', status: 'auto', desc: 'Coverage > 80%' },
            { label: 'New files in /server', status: 'auto', desc: 'If type-checked' },
            { label: 'Dependency adds', status: 'review', desc: 'Always show' },
            { label: 'DB migrations', status: 'review', desc: 'Diff + rollback' },
            { label: 'Production deploys', status: 'gated', desc: 'Operator only' },
          ].map(p => (
            <div key={p.label}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ font: '500 11.5px var(--af2-sans)', color: 'var(--af2-text)' }}>{p.label}</span>
                <Risk level={p.status === 'auto' ? 'safe' : p.status}/>
              </div>
              <div style={{ font: '400 10.5px var(--af2-mono)', color: 'var(--af2-muted)', marginTop: 2 }}>{p.desc}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

/* ── Approvals View ────────────────────────────────────────────── */
function ApprovalsView({ actions, onApprove, onReject }) {
  const pending = actions.filter(a => {
    const n = normalizeAction(a)
    return isPendingAction(n) && !CLOSED_STATUSES.has((n.status || '').toLowerCase())
  })
  const [selected, setSelected] = useState(new Set())
  const [diffOpen, setDiffOpen] = useState(new Set())

  const toggle = id => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const toggleDiff = id => setDiffOpen(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Approval queue" icon="check" sub={`${pending.length} pending`}
        footer={selected.size > 0 ? (
          <>
            <span style={{ color: 'var(--af2-bronze-bright)' }}>{selected.size} SELECTED</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <Btn variant="ghost" sm onClick={() => setSelected(new Set())}>Clear</Btn>
              <Btn variant="success" sm icon="check" onClick={() => { [...selected].forEach(id => { const a = pending.find(p => (normalizeAction(p).id || normalizeAction(p).action_id) === id); if (a) onApprove(normalizeAction(a)) }); setSelected(new Set()) }}>Approve selected</Btn>
            </div>
          </>
        ) : (
          <>
            <span>{pending.length} ACTIONS</span>
            <Btn variant="success" sm icon="check" onClick={() => pending.filter(a => { const n = normalizeAction(a); return n.risk_level !== 'high' && n.risk !== 'dangerous' && n.risk !== 'gated' }).forEach(a => onApprove(normalizeAction(a)))}>Approve all safe</Btn>
          </>
        )}
        flush>
        <div style={{ overflow: 'auto', height: '100%' }}>
          {pending.length === 0 ? (
            <div style={{ padding: 60, textAlign: 'center' }}>
              <div style={{ display: 'inline-flex', marginBottom: 14 }}><Hex tone="gold" size="lg" glow><Icon name="check" size={22}/></Hex></div>
              <div style={{ font: '600 14px var(--af2-sans)', color: 'var(--af2-text)', marginBottom: 4 }}>Queue clear</div>
              <div style={{ font: '400 12px var(--af2-sans)', color: 'var(--af2-muted)' }}>Nothing requires your attention.</div>
            </div>
          ) : pending.map(a => {
            const n = normalizeAction(a)
            const id = n.id || n.action_id
            const risk = n.risk_level === 'high' ? 'gated' : n.risk_level === 'medium' ? 'review' : 'safe'
            return (
              <div key={id} style={{ padding: '14px 16px', borderBottom: '1px solid rgba(205,127,50,0.06)', background: selected.has(id) ? 'rgba(205,127,50,0.05)' : 'transparent', borderLeft: selected.has(id) ? '2px solid var(--af2-bronze)' : '2px solid transparent', transition: 'all 0.16s' }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <button onClick={() => toggle(id)} className={`af2-checkbox${selected.has(id) ? ' af2-checkbox--checked' : ''}`}>
                    {selected.has(id) && <Icon name="check" size={11} style={{ color: '#14110A' }}/>}
                  </button>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
                      <Risk level={risk}/>
                      <span style={{ font: '500 9px var(--af2-mono)', padding: '1px 5px', background: 'rgba(205,127,50,0.12)', color: 'var(--af2-bronze-bright)', border: '1px solid rgba(205,127,50,0.24)', borderRadius: 2 }}>
                        {(n.type || n.action_type || 'ACTION').toUpperCase()}
                      </span>
                    </div>
                    <div style={{ font: '600 13px var(--af2-sans)', color: 'var(--af2-text)', marginBottom: 4 }}>{n.description || n.title || 'Pending action'}</div>
                    {(n.file_path || n.path) && (
                      <div style={{ font: '500 11px var(--af2-mono)', color: 'var(--af2-secondary)', marginBottom: 2 }}>{n.file_path || n.path}</div>
                    )}
                    {(n.diff || n.unified_diff) && (
                      <button onClick={() => toggleDiff(id)} style={{ background: 'none', border: 'none', cursor: 'pointer', font: '500 10px var(--af2-mono)', color: 'var(--af2-bronze-bright)', padding: 0, marginTop: 2 }}>
                        {diffOpen.has(id) ? '▲ hide diff' : '▼ show diff'}
                      </button>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <IconBtn icon="cross" onClick={() => onReject(n)} title="Reject"/>
                    <Btn variant="success" sm icon="check" onClick={() => onApprove(n)}>Approve</Btn>
                  </div>
                </div>
                {diffOpen.has(id) && (n.diff || n.unified_diff) && (
                  <div className="af2-diff" style={{ marginTop: 10, maxHeight: 260, overflow: 'auto', borderRadius: 4 }}>
                    {(n.unified_diff || n.diff).split('\n').map((line, li) => (
                      <div key={li} className={`af2-diff-row af2-diff-row--${line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : 'ctx'}`}>
                        <span className="af2-diff-num">{li + 1}</span>
                        <span className="af2-diff-line">{line}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Panel>
      <Panel title="Today" sub="approval activity">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {[
            { label: 'Approved', value: actions.filter(a => (normalizeAction(a).status || '').toLowerCase() === 'applied').length, color: '#4ADE80' },
            { label: 'Rejected', value: actions.filter(a => (normalizeAction(a).status || '').toLowerCase() === 'rejected').length, color: '#FCA5A5' },
            { label: 'Pending', value: pending.length, color: 'var(--af2-bronze-bright)' },
            { label: 'Total', value: actions.length, color: 'var(--af2-text)' },
          ].map(s => (
            <div key={s.label} style={{ padding: '10px 12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(205,127,50,0.10)', borderRadius: 5 }}>
              <div style={{ font: '600 18px var(--af2-mono)', color: s.color, lineHeight: 1.1 }}>{s.value}</div>
              <div style={{ font: '500 9.5px var(--af2-mono)', letterSpacing: '0.10em', color: 'var(--af2-muted)', marginTop: 3, textTransform: 'uppercase' }}>{s.label}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

/* ── Pipeline View ─────────────────────────────────────────────── */
function PipelineView({ activeRun }) {
  const steps = activeRun?.steps || []

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Run pipeline" icon="pipeline" sub={activeRun?.run_id || 'No active run'}
        actions={<>
          {activeRun && <Pill tone="success" dot pulse>ACTIVE</Pill>}
          {!activeRun && <Pill tone="idle" dot={false}>IDLE</Pill>}
        </>}
        flush>
        <div style={{ overflow: 'auto', height: '100%', padding: 20 }}>
          {steps.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--af2-muted)' }}>
              {activeRun ? 'No steps recorded yet.' : 'Start a run to see the pipeline.'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {steps.map((s, i) => (
                <div key={i} className={`af2-pipeline-node af2-pipeline-node--${s.status || 'pending'}`}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className={`af2-status-dot af2-status-dot--${s.status || 'pending'}`}/>
                      <span style={{ font: '600 12px var(--af2-sans)', color: s.status === 'pending' ? 'var(--af2-muted)' : 'var(--af2-text)' }}>{s.name || s.label || `Step ${i + 1}`}</span>
                    </div>
                    <span style={{ font: '500 10px var(--af2-mono)', color: 'var(--af2-muted)' }}>{s.duration || '—'}</span>
                  </div>
                  {s.status === 'running' && s.progress != null && (
                    <div style={{ marginTop: 8, height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${s.progress * 100}%`, background: 'var(--af2-grad-bronze)', boxShadow: '0 0 6px rgba(205,127,50,0.5)' }}/>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>
      <Panel title="Run summary" tone="gold">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <CapRow label="Run ID" value={activeRun?.run_id ? compactId(activeRun.run_id) : '—'}/>
          <CapRow label="Status" value={activeRun?.status || '—'}/>
          <CapRow label="Steps" value={`${steps.filter(s => s.status === 'done').length} / ${steps.length}`}/>
          <CapRow label="Spend" value={activeRun?.cost ? `$${activeRun.cost.toFixed(3)}` : '—'}/>
        </div>
      </Panel>
    </div>
  )
}

function flattenTree(node, files = []) {
  if (!node) return files
  if (node.type === 'file') files.push(node)
  if (Array.isArray(node.children)) node.children.forEach(c => flattenTree(c, files))
  return files
}

/* ── Files View ────────────────────────────────────────────────── */
function FilesView({ project }) {
  const [files, setFiles] = useState([])
  const [active, setActive] = useState(null)
  const [content, setContent] = useState('')

  useEffect(() => {
    if (!project?.id) return
    fetch(`/api/forge/files/tree?project_id=${encodeURIComponent(project.id)}`, { headers: TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {} })
      .then(r => r.ok ? r.json() : { tree: [] })
      .then(d => { const all = []; (d.tree || []).forEach(n => flattenTree(n, all)); setFiles(all) })
      .catch(() => {})
  }, [project?.id])

  const loadFile = async (path) => {
    setActive(path)
    try {
      const r = await fetch(`/api/forge/files/read?project_id=${encodeURIComponent(project.id)}&file_path=${encodeURIComponent(path)}`, { headers: TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {} })
      const d = await r.json()
      setContent(d.content || '')
    } catch { setContent('') }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Workspace" sub={`${files.length} files`} flush>
        <div className="af2-tree" style={{ overflow: 'auto', height: '100%' }}>
          {files.map((f, i) => (
            <div key={i} className={`af2-tree-node${active === (f.path || f) ? ' af2-tree-node--active' : ''}`} onClick={() => loadFile(f.path || f)}>
              <Icon name="file" size={11}/>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{(f.path || f).split('/').pop()}</span>
              {f.badge && <span className={`af2-tree-badge af2-tree-badge--${f.badge}`}>{f.stat || ''}</span>}
            </div>
          ))}
          {files.length === 0 && <div style={{ padding: 20, color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>{project ? 'No files found.' : 'Select a project first.'}</div>}
        </div>
      </Panel>
      <Panel title={active || 'Select a file'} icon="file" flush>
        <div className="af2-diff" style={{ overflow: 'auto', height: '100%', padding: '12px 16px' }}>
          {content ? content.split('\n').map((line, i) => (
            <div key={i} className="af2-diff-row af2-diff-row--ctx">
              <span className="af2-diff-num">{i + 1}</span>
              <span className="af2-diff-line">{line}</span>
            </div>
          )) : (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--af2-muted)' }}>Select a file to view its contents.</div>
          )}
        </div>
      </Panel>
    </div>
  )
}

/* ── History View ──────────────────────────────────────────────── */
function HistoryView({ project }) {
  const [runs, setRuns] = useState([])
  const [selected, setSelected] = useState(null)
  const [busy, setBusy] = useState('')

  const reload = useCallback(() => {
    if (!project?.id) return
    fetch(`/api/forge/runs?project_id=${encodeURIComponent(project.id)}`, { headers: TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {} })
      .then(r => r.ok ? r.json() : {})
      .then(d => {
        const list = Array.isArray(d) ? d : d.runs || []
        setRuns(list)
        setSelected(sel => sel ? (list.find(r => r.run_id === sel.run_id) || sel) : sel)
      })
      .catch(() => {})
  }, [project?.id])

  useEffect(() => { reload() }, [reload])

  const runAction = async (action) => {
    if (!selected) return
    setBusy(action)
    try {
      const runId = selected.run_id || selected.id
      const r = await fetch(`/api/forge/runs/${runId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {}) },
        body: JSON.stringify({ ownerApproved: true }),
      })
      const d = await r.json()
      if (!r.ok) { toastError(d.error || `${action} failed`); return }
      toastSuccess(`${action.charAt(0).toUpperCase() + action.slice(1)} complete`)
      reload()
    } catch (e) { toastError(e.message) }
    finally { setBusy('') }
  }

  const statusDot = s => s === 'applied' ? 'done' : s === 'running' ? 'running' : s === 'verified' ? 'done' : s === 'verify_failed' ? 'err' : 'pending'
  const runTone = s => s === 'applied' || s === 'verified' ? 'success' : s === 'running' ? 'bronze' : s === 'verify_failed' ? 'danger' : 'idle'

  const latestTest = selected?.test_results?.slice(-1)[0]
  const canVerify = selected && ['awaiting_approval', 'staged', 'approved', 'verify_failed'].includes(selected.status)
  const canApply = selected && (selected.status === 'verified' || latestTest?.all_passed)

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Run history" icon="history" sub={`${runs.length} runs`} flush>
        <div style={{ overflow: 'auto', height: '100%' }}>
          {runs.length === 0 && (
            <div style={{ padding: 60, textAlign: 'center', color: 'var(--af2-muted)' }}>No runs yet. Forge a plan to get started.</div>
          )}
          {runs.map((h) => {
            const isSelected = selected?.run_id === (h.run_id || h.id)
            return (
              <div key={h.run_id || h.id}
                onClick={() => setSelected(h)}
                style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 12, padding: '14px 16px', borderBottom: '1px solid rgba(205,127,50,0.06)', borderLeft: isSelected ? '2px solid var(--af2-bronze)' : '2px solid transparent', alignItems: 'center', cursor: 'pointer', background: isSelected ? 'rgba(205,127,50,0.05)' : 'transparent', transition: 'all 0.16s' }}>
                <span className={`af2-status-dot af2-status-dot--${statusDot(h.status)}`}/>
                <div style={{ minWidth: 0 }}>
                  <div style={{ font: '500 12.5px var(--af2-sans)', color: 'var(--af2-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.goal || 'Unnamed run'}</div>
                  <div style={{ font: '400 10px var(--af2-mono)', color: 'var(--af2-muted)', marginTop: 2 }}>{h.run_id ? compactId(h.run_id) : ''} · {h.created_at ? new Date(h.created_at).toLocaleTimeString() : ''}</div>
                </div>
                <Pill tone={runTone(h.status)} sm dot={false}>{h.status || 'unknown'}</Pill>
              </div>
            )
          })}
        </div>
      </Panel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
        {selected ? (
          <>
            <Panel title={compactId(selected.run_id || selected.id)} sub={selected.status} tone="gold">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ font: '400 12px var(--af2-sans)', color: 'var(--af2-text)', marginBottom: 4 }}>{selected.goal}</div>
                <CapRow label="Actions" value={`${selected.action_count ?? '—'}`}/>
                <CapRow label="Patches" value={`${selected.patch_count ?? '—'}`}/>
                <CapRow label="Mode" value={selected.mode || '—'}/>
                <CapRow label="Created" value={selected.created_at ? new Date(selected.created_at).toLocaleTimeString() : '—'}/>
              </div>
            </Panel>

            <Panel title="Actions">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Btn
                  variant="ghost" sm icon="check"
                  disabled={!canVerify || busy === 'verify'}
                  onClick={() => runAction('verify')}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  {busy === 'verify' ? 'Running tests…' : 'Run tests & verify'}
                </Btn>
                <Btn
                  variant={canApply ? 'success' : 'ghost'} sm icon="play"
                  disabled={!canApply || busy === 'apply'}
                  onClick={() => runAction('apply')}
                  style={{ width: '100%', justifyContent: 'center' }}
                  title={!canApply ? 'Verify must pass first' : undefined}
                >
                  {busy === 'apply' ? 'Applying…' : 'Apply to project'}
                </Btn>
              </div>
            </Panel>

            {latestTest && (
              <Panel title="Last test run" tone={latestTest.all_passed ? 'success' : 'danger'} flush>
                <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <Pill tone={latestTest.all_passed ? 'success' : 'danger'} dot pulse={!latestTest.all_passed}>
                    {latestTest.all_passed ? 'All passed' : 'Failed'}
                  </Pill>
                  {(latestTest.results || []).map((r, i) => (
                    <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                      <span style={{ font: '600 10px var(--af2-mono)', color: r.pass ? '#4ADE80' : '#FCA5A5', flexShrink: 0, paddingTop: 1 }}>{r.pass ? 'PASS' : 'FAIL'}</span>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ font: '500 10.5px var(--af2-mono)', color: 'var(--af2-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.command}</div>
                        {!r.pass && r.output && (
                          <div style={{ font: '400 10px var(--af2-mono)', color: 'var(--af2-muted)', marginTop: 2, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{r.output.slice(0, 300)}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
            )}
          </>
        ) : (
          <Panel title="Run detail" tone="gold">
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>Select a run to see actions</div>
          </Panel>
        )}
      </div>
    </div>
  )
}

/* ── Agents View ───────────────────────────────────────────────── */
function AgentsView({ agents }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 14, height: '100%', minHeight: 0 }}>
      <Panel title="Agent roster" icon="agents" sub={`${agents.length} active`} flush>
        <div style={{ overflow: 'auto', height: '100%' }}>
          {agents.map(a => (
            <div key={a.id} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 16, padding: '16px 18px', borderBottom: '1px solid rgba(205,127,50,0.08)', alignItems: 'center', cursor: 'pointer', transition: 'background 0.16s' }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(205,127,50,0.03)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
              <Hex tone="bronze" size="lg" glow>
                <span style={{ font: '700 18px var(--af2-sans)', color: 'var(--af2-bronze-bright)' }}>{(a.name || 'A')[0]}</span>
              </Hex>
              <div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ font: '600 14px var(--af2-sans)', color: 'var(--af2-text)' }}>{a.name || a.id}</span>
                  <Pill tone={a.status === 'running' ? 'success' : a.status === 'thinking' ? 'gold' : 'idle'} sm>{a.status || 'ready'}</Pill>
                </div>
                <div style={{ font: '500 10px var(--af2-mono)', color: 'var(--af2-muted)', marginTop: 3, textTransform: 'uppercase' }}>{a.model || 'claude-sonnet'}</div>
                {a.task && <div style={{ font: '400 11.5px var(--af2-mono)', color: 'var(--af2-secondary)', marginTop: 6 }}>{a.task}</div>}
              </div>
              <Spark data={stableSpark({ len: 24, base: Math.max(8, (a.task || '').length), amp: a.status === 'unavailable' ? 3 : 12, seed: idxFromId(a.id) })} color="#CD7F32" w={100} h={28}/>
            </div>
          ))}
          {agents.length === 0 && (
            <div style={{ padding: 60, textAlign: 'center', color: 'var(--af2-muted)' }}>No active agents. Start a run to see agents.</div>
          )}
        </div>
      </Panel>
      <Panel title="Crew utilization" tone="gold">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {agents.map(a => (
            <div key={a.id}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                <span style={{ font: '500 11px var(--af2-sans)', color: 'var(--af2-text)' }}>{a.name || a.id}</span>
                <span style={{ font: '500 10px var(--af2-mono)', color: 'var(--af2-bronze-bright)' }}>{Math.round((a.load || 0.5) * 100)}%</span>
              </div>
              <div style={{ height: 3, background: 'rgba(255,255,255,0.04)', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${(a.load || 0.5) * 100}%`, background: 'var(--af2-grad-bronze)', boxShadow: '0 0 6px rgba(205,127,50,0.5)' }}/>
              </div>
            </div>
          ))}
          {agents.length === 0 && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>No agents active.</div>}
        </div>
      </Panel>
    </div>
  )
}

/* ── Terminal View ─────────────────────────────────────────────── */
function TerminalView({ termLines }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [termLines])
  return (
    <Panel title="Terminal" icon="terminal" style={{ height: '100%' }} flush>
      <div ref={ref} className="af2-log" style={{ height: '100%', overflow: 'auto', padding: '12px 16px' }}>
        {termLines.map((l, i) => (
          <div key={i} className={`af2-log-line af2-log-line--${l.type || 'out'}`}>
            <span className="af2-log-msg" style={{ fontFamily: 'var(--af2-mono)', fontSize: 12 }}>{l.text}</span>
          </div>
        ))}
        {termLines.length === 0 && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-mono)' }}>$ _</div>}
      </div>
    </Panel>
  )
}

function useV5ProjectData(projectId) {
  const [data, setData] = useState({ brief: null, researchPack: null, goals: [], reasoning: null, report: null, loading: false, error: null })
  const refresh = useCallback(async () => {
    if (!projectId) return null
    setData(prev => ({ ...prev, loading: true, error: null }))
    try {
      const [brief, research, goals, report] = await Promise.all([
        api.forge.v5.getBrief(projectId).catch(() => ({})),
        api.forge.v5.getResearch(projectId).catch(() => ({})),
        api.forge.v5.getGoals(projectId).catch(() => ({})),
        api.forge.v5.getReport(projectId).catch(() => ({})),
      ])
      const next = {
        brief: brief.brief || null,
        researchPack: research.research_pack || null,
        goals: goals.goals || [],
        reasoning: goals.reasoning || null,
        report: report.report || null,
        loading: false,
        error: null,
      }
      setData(next)
      return next
    } catch (err) {
      setData(prev => ({ ...prev, loading: false, error: err?.message || 'V5 unavailable' }))
      return null
    }
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])
  return { data, setData, refresh }
}

function V5ProjectView({ project, onPrepared }) {
  const [rawInput, setRawInput] = useState('')
  const [busy, setBusy] = useState(false)
  const { data, setData, refresh } = useV5ProjectData(project?.id)
  const isHandoff = Boolean(project?.handoff || project?.target_type === 'orders_handoff')

  const start = async () => {
    if (isHandoff) {
      toastError('Import or convert this handoff before preparing executable V5 work')
      return
    }
    if (!rawInput.trim() || busy) return
    setBusy(true)
    try {
      const result = await api.forge.v5.startProject({ raw_input: rawInput, project_id: project?.id })
      if (result.project) onPrepared?.(result.project)
      setData({
        brief: result.brief || null,
        researchPack: result.research_pack || null,
        goals: result.goals || [],
        reasoning: result.reasoning || null,
        report: result.report || null,
        loading: false,
        error: null,
      })
      toastSuccess('V5 project prepared')
    } catch (err) {
      toastError(err?.message || 'V5 prepare failed')
    } finally {
      setBusy(false)
    }
  }

	  return (
	    <div className="af2-grid af2-grid--2">
	      <Panel title="Project Runtime" icon="spark" actions={<Btn sm variant="ghost" onClick={refresh} disabled={!project}>Refresh</Btn>}>
	        {isHandoff && <Pill tone="warn" pulse={false}>ORDERS HANDOFF READ ONLY</Pill>}
	        {isHandoff && <div style={{ margin: '10px 0', color: 'var(--af2-muted)', font: '400 12.5px/1.6 var(--af2-sans)' }}>This project was created by the Orders handoff. Brief, research, goals, and report state can be viewed here; execution and publishing require importing it as a normal local Forge project.</div>}
	        <textarea value={rawInput} onChange={e => setRawInput(e.target.value)} placeholder={isHandoff ? 'Import this handoff before preparing executable V5 work' : 'Project intent'} className="af2-input" style={{ minHeight: 130, marginBottom: 12, resize: 'vertical' }} disabled={isHandoff}/>
	        <Btn variant="primary" icon="spark" onClick={start} disabled={isHandoff || !rawInput.trim() || busy}>{isHandoff ? 'Import Required' : busy ? 'Preparing' : 'Prepare V5'}</Btn>
        <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
          <Pill tone={data.brief ? 'success' : 'idle'}>{data.brief ? 'BRIEF READY' : 'BRIEF UNAVAILABLE'}</Pill>
          <Pill tone={data.researchPack ? 'success' : 'idle'}>{data.researchPack ? 'RESEARCH READY' : 'RESEARCH UNAVAILABLE'}</Pill>
          <Pill tone={data.goals.length ? 'success' : 'idle'}>{data.goals.length} GOALS</Pill>
        </div>
      </Panel>
      <Panel title="Brief" icon="files">
        <div style={{ font: '600 18px var(--af2-sans)', color: 'var(--af2-text)', marginBottom: 8 }}>{data.brief?.title || 'Unavailable'}</div>
        <div style={{ font: '400 13px/1.6 var(--af2-sans)', color: 'var(--af2-muted)' }}>{data.brief?.summary || 'No V5 brief has been prepared for this project.'}</div>
        <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(data.brief?.constraints || []).slice(0, 4).map(item => <Pill key={item} sm tone="warn" pulse={false}>{item.slice(0, 42)}</Pill>)}
        </div>
      </Panel>
      <Panel title="Research Pack" icon="search">
        {(data.researchPack?.codebase_findings || []).slice(0, 5).map((item, idx) => (
          <div key={idx} className="af2-row"><span style={{ color: 'var(--af2-text)', font: '500 12.5px var(--af2-sans)' }}>{item}</span></div>
        ))}
	        {!data.researchPack && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>{isHandoff ? 'Research has not run for this handoff project.' : 'Unavailable'}</div>}
      </Panel>
      <Panel title="Report" icon="history">
        <div style={{ font: '600 22px var(--af2-mono)', color: 'var(--af2-bronze-bright)' }}>{data.report?.goals_prepared ?? data.goals.length}</div>
        <div style={{ color: 'var(--af2-muted)', font: '500 11px var(--af2-mono)', textTransform: 'uppercase' }}>Prepared goals</div>
      </Panel>
    </div>
  )
}

function V5GoalsView({ project, onRun }) {
  const { data, refresh } = useV5ProjectData(project?.id)
  const [busy, setBusy] = useState({})
  const isHandoff = Boolean(project?.handoff || project?.target_type === 'orders_handoff')
  const execute = async (goal) => {
    if (isHandoff) {
      toastError('Import or convert this handoff before executing V5 goals')
      return
    }
    if (!project?.id || !goal?.goal_id || busy[goal.goal_id]) return
    setBusy(prev => ({ ...prev, [goal.goal_id]: true }))
    try {
      const result = await api.forge.v5.executeGoal(project.id, goal.goal_id, { max_iterations: goal.max_iterations || 3 })
      onRun?.(result.run_result?.run || result.run_result)
      toastSuccess('V5 goal execution started')
      await refresh()
    } catch (err) {
      toastError(err?.message || 'V5 goal execution failed')
    } finally {
      setBusy(prev => { const next = { ...prev }; delete next[goal.goal_id]; return next })
    }
  }
  return (
    <Panel title="V5 Goals" icon="branch" actions={<Btn sm variant="ghost" onClick={refresh} disabled={!project}>Refresh</Btn>}>
      <div style={{ display: 'grid', gap: 10 }}>
        {data.goals.map(goal => (
	          <div key={goal.goal_id || goal.title} className="af2-row" style={{ alignItems: 'flex-start' }}>
            <Hex tone={goal.status === 'completed' ? 'success' : goal.status === 'failed' ? 'danger' : 'bronze'} size="sm"><Icon name="branch" size={12}/></Hex>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: 'var(--af2-text)', font: '600 13px var(--af2-sans)' }}>{goal.title}</div>
              <div style={{ color: 'var(--af2-muted)', font: '400 12px/1.5 var(--af2-sans)', marginTop: 4 }}>{goal.description}</div>
              <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                <Pill sm tone="idle" pulse={false}>{String(goal.status || 'proposed').toUpperCase()}</Pill>
                <Pill sm tone={goal.risk_level === 'high' ? 'danger' : goal.risk_level === 'medium' ? 'warn' : 'success'} pulse={false}>{String(goal.risk_level || 'low').toUpperCase()}</Pill>
              </div>
            </div>
	            <Btn sm variant="primary" icon="play" onClick={() => execute(goal)} disabled={isHandoff || busy[goal.goal_id] || ['in_progress', 'completed'].includes(goal.status) || !goal.goal_id}>
	              {isHandoff ? 'Import First' : busy[goal.goal_id] ? 'Starting' : 'Execute'}
	            </Btn>
          </div>
        ))}
        {!data.goals.length && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>No V5 goals prepared.</div>}
      </div>
    </Panel>
  )
}

function V5ReasoningView({ project }) {
  const { data, refresh } = useV5ProjectData(project?.id)
  const paths = data.reasoning?.paths_considered || data.goals.flatMap(goal => goal.qce_paths_considered || [])
  return (
    <div className="af2-grid af2-grid--2">
      <Panel title="QCE Paths Considered" icon="search" actions={<Btn sm variant="ghost" onClick={refresh} disabled={!project}>Refresh</Btn>}>
        <div style={{ display: 'grid', gap: 10 }}>
          {paths.slice(0, 8).map((pathItem, idx) => (
            <div key={`${pathItem.name || 'path'}-${idx}`} className="af2-row" style={{ alignItems: 'flex-start' }}>
              <Hex tone={idx === 0 ? 'success' : 'bronze'} size="sm"><Icon name="pipeline" size={12}/></Hex>
              <div style={{ flex: 1 }}>
                <div style={{ color: 'var(--af2-text)', font: '600 13px var(--af2-sans)' }}>{pathItem.name || `Path ${idx + 1}`}</div>
                <div style={{ color: 'var(--af2-muted)', font: '400 12px/1.5 var(--af2-sans)' }}>{pathItem.rationale || 'No rationale recorded.'}</div>
              </div>
              <span style={{ font: '600 11px var(--af2-mono)', color: 'var(--af2-bronze-bright)' }}>{Math.round((pathItem.confidence || 0) * 100)}%</span>
            </div>
          ))}
          {!paths.length && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>Unavailable</div>}
        </div>
      </Panel>
      <Panel title="Selected Route" icon="agents">
        <div style={{ display: 'grid', gap: 10 }}>
          <div className="af2-row"><span>Mode</span><Pill sm pulse={false}>{data.reasoning?.selected_mode || 'unavailable'}</Pill></div>
          <div className="af2-row"><span>Model</span><Pill sm pulse={false}>{data.reasoning?.model_used || 'unavailable'}</Pill></div>
          <div className="af2-row"><span>Complexity</span><Pill sm pulse={false}>{data.reasoning?.complexity || 'unavailable'}</Pill></div>
          <div className="af2-row"><span>Agents</span><span style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>{(data.reasoning?.agents || []).join(', ') || 'unavailable'}</span></div>
        </div>
      </Panel>
    </div>
  )
}

function V5QualityView({ project }) {
  const { data, refresh } = useV5ProjectData(project?.id)
  const [gates, setGates] = useState({})
  useEffect(() => {
    let alive = true
    async function load() {
      const entries = await Promise.all((data.goals || []).map(async goal => {
        const result = await api.forge.v5.getQualityGate(goal.goal_id).catch(() => ({}))
        return [goal.goal_id, result.quality_gate || null]
      }))
      if (alive) setGates(Object.fromEntries(entries))
    }
    load()
    return () => { alive = false }
  }, [data.goals])
  const dimensions = ['functional_correctness', 'safety', 'efficiency', 'usability', 'reliability', 'integration_quality', 'maintainability']
  return (
    <Panel title="Quality Gates" icon="check" actions={<Btn sm variant="ghost" onClick={refresh} disabled={!project}>Refresh</Btn>}>
      <div style={{ display: 'grid', gap: 12 }}>
        {data.goals.map(goal => {
          const gate = gates[goal.goal_id]
          return (
            <div key={goal.goal_id} className="af2-row" style={{ display: 'block' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
                <span style={{ color: 'var(--af2-text)', font: '600 13px var(--af2-sans)' }}>{goal.title}</span>
                <Pill sm tone={gate?.status === 'passed' ? 'success' : gate?.status === 'failed' ? 'danger' : 'idle'} pulse={false}>{gate?.status || 'unavailable'}</Pill>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8 }}>
                {dimensions.map(dim => {
                  const status = gate?.[dim]?.status || 'unavailable'
                  return <Pill key={dim} sm tone={status === 'passed' ? 'success' : status === 'failed' ? 'danger' : 'idle'} pulse={false}>{dim.replace(/_/g, ' ')} · {status}</Pill>
                })}
              </div>
            </div>
          )
        })}
        {!data.goals.length && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>No quality gates available.</div>}
      </div>
    </Panel>
  )
}

function ForgeQueueView({ project }) {
  const [tab, setTab] = useState('approvals')
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)
  const queue = useForgeStore(useShallow(s => s.queue))
  const refreshQueue = useForgeStore(s => s.refreshQueue)
  const submitQueueItem = useForgeStore(s => s.submitQueueItem)
  const approveQueueItem = useForgeStore(s => s.approveQueueItem)
  const rejectQueueItem = useForgeStore(s => s.rejectQueueItem)

  useEffect(() => { refreshQueue?.().catch(() => {}) }, [refreshQueue])

  const items = queue?.items || []
  const submit = async () => {
    if (!goal.trim() || busy) return
    setBusy(true)
    try {
      await submitQueueItem({ goal, project_id: project?.handoff ? null : project?.id, title: goal.slice(0, 90), mode: 'builder' })
      setGoal('')
      toastSuccess('Queue item submitted')
    } catch (err) {
      toastError(err?.message || 'Queue submit failed')
    } finally {
      setBusy(false)
    }
  }

  const decide = async (item, action) => {
    const id = item.id || item.action_id
    if (!id) return
    try {
      if (action === 'approve') {
        await approveQueueItem(id, { note: 'Approved from AscendForge Queue' })
        toastSuccess('Queue item approved')
      } else {
        await rejectQueueItem(id, { reason: 'Rejected from AscendForge Queue' })
        toastSuccess('Queue item rejected')
      }
    } catch (err) {
      toastError(err?.message || `Queue ${action} failed`)
    }
  }

  return (
    <div className="af2-grid af2-grid--2">
      <Panel title="Forge Queue" icon="bell" actions={
        <>
          {['approvals', 'builder', 'evolution'].map(name => (
            <Btn key={name} sm variant={tab === name ? 'primary' : 'ghost'} onClick={() => setTab(name)}>{name}</Btn>
          ))}
          <Btn sm variant="ghost" onClick={() => refreshQueue?.().catch(() => {})}>Refresh</Btn>
        </>
      }>
        {tab === 'approvals' && (
          <div style={{ display: 'grid', gap: 10 }}>
            {items.map(item => (
              <div key={item.id || item.action_id} className="af2-row" style={{ alignItems: 'flex-start' }}>
                <Hex tone={item.status === 'approved' ? 'success' : 'bronze'} size="sm"><Icon name="bell" size={12}/></Hex>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: 'var(--af2-text)', font: '600 13px var(--af2-sans)' }}>{item.label || item.title || 'Queued Forge item'}</div>
                  <div style={{ color: 'var(--af2-muted)', font: '400 12px/1.5 var(--af2-sans)', marginTop: 4 }}>{item.description || item.goal || 'No description recorded.'}</div>
                  <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                    <Pill sm tone={item.status === 'approved' ? 'success' : 'warn'} pulse={false}>{String(item.status || 'proposed').toUpperCase()}</Pill>
                    <Pill sm tone="idle" pulse={false}>{String(item.risk || 'review').toUpperCase()}</Pill>
                  </div>
                </div>
                <Btn sm variant="primary" icon="check" onClick={() => decide(item, 'approve')} disabled={item.status === 'approved'}>Approve</Btn>
                <Btn sm variant="ghost" icon="cross" onClick={() => decide(item, 'reject')}>Reject</Btn>
              </div>
            ))}
            {!items.length && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>Queue is empty.</div>}
          </div>
        )}
        {tab === 'builder' && (
          <div style={{ display: 'grid', gap: 10 }}>
            {project?.handoff && <Pill tone="warn" pulse={false}>HANDOFF PROJECTS MUST BE IMPORTED BEFORE EXECUTION</Pill>}
            <textarea value={goal} onChange={e => setGoal(e.target.value)} placeholder="Queue a supervised builder task" className="af2-input" style={{ minHeight: 120, resize: 'vertical' }}/>
            <Btn variant="primary" icon="send" onClick={submit} disabled={!goal.trim() || busy}>{busy ? 'Submitting' : 'Submit to Queue'}</Btn>
          </div>
        )}
        {tab === 'evolution' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
            <div className="af2-row" style={{ display: 'block' }}><div className="af2-label">Queued</div><div style={{ font: '600 28px var(--af2-mono)', color: 'var(--af2-bronze-bright)' }}>{items.length}</div></div>
            <div className="af2-row" style={{ display: 'block' }}><div className="af2-label">Approved</div><div style={{ font: '600 28px var(--af2-mono)', color: '#4ADE80' }}>{items.filter(i => i.status === 'approved').length}</div></div>
            <div className="af2-row" style={{ display: 'block' }}><div className="af2-label">Mode</div><Pill tone="idle" pulse={false}>CANONICAL STORE</Pill></div>
          </div>
        )}
      </Panel>
      <Panel title="Queue Contract" icon="pipeline">
        <div style={{ display: 'grid', gap: 10 }}>
          <div className="af2-row"><span>State source</span><Pill sm pulse={false}>forgeStore</Pill></div>
          <div className="af2-row"><span>Events</span><Pill sm pulse={false}>forge:queue_update</Pill></div>
          <div className="af2-row"><span>Execution</span><Pill sm tone="warn" pulse={false}>explicit Forge run only</Pill></div>
          <div style={{ color: 'var(--af2-muted)', font: '400 12.5px/1.6 var(--af2-sans)' }}>Queue approval records intent and review state. Code execution still runs through the existing Forge run and approval paths.</div>
        </div>
      </Panel>
    </div>
  )
}

function GitHubPublishView({ project }) {
  const github = useForgeStore(useShallow(s => s.github))
  const refreshGithubStatus = useForgeStore(s => s.refreshGithubStatus)
  const prepareGithubPublish = useForgeStore(s => s.prepareGithubPublish)
  const publishGithubDraft = useForgeStore(s => s.publishGithubDraft)
  const [draftInput, setDraftInput] = useState({ title: '', body: '', branch_name: '', commit_message: '' })
  const [busy, setBusy] = useState(false)
  const [confirmPublish, setConfirmPublish] = useState(false)
  const isHandoff = Boolean(project?.handoff || project?.target_type === 'orders_handoff')

  useEffect(() => {
    if (project?.id && !isHandoff) refreshGithubStatus?.(project.id).catch(() => {})
  }, [project?.id, isHandoff, refreshGithubStatus])

  const status = github.status
  const draft = github.draft
  const result = github.result
  const changed = status?.git?.dirty_files || []

  const prepare = async () => {
    if (!project?.id || isHandoff || busy) return
    setBusy(true)
    try {
      await prepareGithubPublish(project.id, draftInput)
      toastSuccess('GitHub publish draft prepared')
    } catch (err) {
      toastError(err?.message || 'GitHub prepare failed')
    } finally {
      setBusy(false)
    }
  }

  const publish = async () => {
    if (!project?.id || isHandoff || busy) return
    if (!draft?.publish_id) { toastError('Prepare a draft before publishing'); return }
    if (!confirmPublish) { toastError('Confirm the push + PR first'); return }
    setBusy(true)
    try {
      const response = await publishGithubDraft(project.id, { draft, confirm: true, publish_id: draft.publish_id })
      toastSuccess(response.pr?.url ? 'GitHub PR created' : 'GitHub branch pushed')
      setConfirmPublish(false)
    } catch (err) {
      const code = err?.body?.error || err?.error || err?.message
      if (code === 'publish_id_mismatch') {
        toastError('Draft changed since you prepared it — click Prepare again, then confirm.')
        setConfirmPublish(false)
      } else if (code === 'publish_requires_confirmation') {
        toastError('Tick the confirmation box before publishing.')
      } else if (code === 'publish_requires_prepared_draft') {
        toastError('Prepare a draft first, then publish.')
      } else {
        toastError(err?.message || 'GitHub publish failed')
      }
    } finally {
      setBusy(false)
    }
  }

  if (isHandoff) {
    return (
      <Panel title="GitHub Publish" icon="branch">
        <Pill tone="warn" pulse={false}>HANDOFF READ ONLY</Pill>
        <div style={{ marginTop: 12, color: 'var(--af2-muted)', font: '400 13px/1.6 var(--af2-sans)' }}>Orders handoff projects can be read in V5, but they must be imported or converted into a normal local Forge project before branch and PR publishing.</div>
      </Panel>
    )
  }

  return (
    <div className="af2-grid af2-grid--2">
      <Panel title="GitHub Status" icon="branch" actions={<Btn sm variant="ghost" onClick={() => project?.id && refreshGithubStatus?.(project.id).catch(() => {})} disabled={!project}>Refresh</Btn>}>
        {!project && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>Select a project to inspect GitHub status.</div>}
        {project && (
          <div style={{ display: 'grid', gap: 10 }}>
            <div className="af2-row"><span>Remote</span><span style={{ color: 'var(--af2-muted)', font: '500 11px var(--af2-mono)' }}>{status?.remote?.url || 'unavailable'}</span></div>
            <div className="af2-row"><span>Branch</span><Pill sm pulse={false}>{status?.git?.current_branch || 'unavailable'}</Pill></div>
            <div className="af2-row"><span>Token</span><Pill sm tone={status?.auth?.token_available ? 'success' : 'warn'} pulse={false}>{status?.auth?.token_available ? 'AVAILABLE' : 'NO TOKEN'}</Pill></div>
            <div className="af2-row"><span>Changed files</span><Pill sm tone={changed.length ? 'warn' : 'idle'} pulse={false}>{changed.length}</Pill></div>
            {(status?.blockers || []).map(blocker => <Pill key={blocker} tone="warn" pulse={false}>{blocker}</Pill>)}
          </div>
        )}
      </Panel>
      <Panel title="Publish Draft" icon="send">
        <div style={{ display: 'grid', gap: 9 }}>
          <input className="af2-input" value={draftInput.branch_name} onChange={e => setDraftInput(v => ({ ...v, branch_name: e.target.value }))} placeholder="Branch name, optional"/>
          <input className="af2-input" value={draftInput.title} onChange={e => setDraftInput(v => ({ ...v, title: e.target.value }))} placeholder="PR title, optional"/>
          <input className="af2-input" value={draftInput.commit_message} onChange={e => setDraftInput(v => ({ ...v, commit_message: e.target.value }))} placeholder="Commit message, optional"/>
          <textarea className="af2-input" value={draftInput.body} onChange={e => setDraftInput(v => ({ ...v, body: e.target.value }))} placeholder="PR body, optional" style={{ minHeight: 90, resize: 'vertical' }}/>
          {draft && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--af2-muted)', font: '500 12px var(--af2-sans)', cursor: 'pointer' }}>
              <input type="checkbox" checked={confirmPublish} onChange={e => setConfirmPublish(e.target.checked)}/>
              I confirm pushing branch <strong style={{ color: 'var(--af2-bronze-bright)' }}>{draft.branch_name}</strong> and opening a PR
            </label>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn variant="primary" icon="spark" onClick={prepare} disabled={!project || busy || !changed.length}>Prepare</Btn>
            <Btn variant="primary" icon="send" onClick={publish} disabled={!project || busy || !draft || !confirmPublish}>Publish Branch + PR</Btn>
          </div>
        </div>
      </Panel>
      <Panel title="Changed Files" icon="files">
        <div style={{ display: 'grid', gap: 7 }}>
          {changed.slice(0, 30).map(file => <div key={file.raw || file.path} className="af2-row"><span>{file.path}</span><Pill sm pulse={false}>{file.status}</Pill></div>)}
          {!changed.length && <div style={{ color: 'var(--af2-muted)', font: '400 12px var(--af2-sans)' }}>No changed files detected.</div>}
        </div>
      </Panel>
      <Panel title="Publish Result" icon="history">
        <div style={{ display: 'grid', gap: 10 }}>
          <div className="af2-row"><span>State</span><Pill sm tone={result?.state === 'published' ? 'success' : result?.state === 'partial' ? 'warn' : 'idle'} pulse={false}>{result?.state || github.phase || 'idle'}</Pill></div>
          <div className="af2-row"><span>Branch</span><span style={{ color: 'var(--af2-muted)', font: '500 11px var(--af2-mono)' }}>{result?.branch_name || draft?.branch_name || 'unavailable'}</span></div>
          {result?.pr?.url && <a href={result.pr.url} target="_blank" rel="noreferrer" style={{ color: 'var(--af2-bronze-bright)', font: '600 12px var(--af2-sans)' }}>Open pull request</a>}
          {result?.pr?.reason && <div style={{ color: '#F59E0B', font: '400 12px/1.5 var(--af2-sans)' }}>{result.pr.reason}</div>}
          {github.error && <div style={{ color: '#F87171', font: '400 12px/1.5 var(--af2-sans)' }}>{github.error}</div>}
        </div>
      </Panel>
    </div>
  )
}

function V7ExecutionView({ project }) {
  const { data: v5Data, refresh: refreshV5 } = useV5ProjectData(project?.id)
  const v7 = useForgeStore(useShallow(s => s.v7))
  const setMode = useForgeStore(s => s.setV7ExecutionMode)
  const refreshV7 = useForgeStore(s => s.refreshV7ExecutionState)
  const proposePatch = useForgeStore(s => s.v7ProposePatch)
  const createSandbox = useForgeStore(s => s.v7CreateSandbox)
  const applySandbox = useForgeStore(s => s.v7ApplyPatchSandbox)
  const validateWorkspace = useForgeStore(s => s.v7ValidateWorkspace)
  const requestApply = useForgeStore(s => s.v7RequestApply)
  const approveApply = useForgeStore(s => s.v7ApproveApply)
  const rejectApply = useForgeStore(s => s.v7RejectApply)
  const applyWorkspace = useForgeStore(s => s.v7ApplyToWorkspace)
  const postValidate = useForgeStore(s => s.v7PostValidate)
  const rollback = useForgeStore(s => s.v7Rollback)
  const [goalId, setGoalId] = useState('')
  const [summary, setSummary] = useState('')
  const [filesJson, setFilesJson] = useState('[{\"path\":\"README.md\",\"content\":\"# Updated by AscendForge V7\\n\"}]')
  const [diff, setDiff] = useState('')
  const [busy, setBusy] = useState('')

  const isHandoff = Boolean(project?.handoff || project?.target_type === 'orders_handoff')
  const goals = v5Data.goals || []
  const selectedGoal = goals.find(goal => goal.goal_id === goalId) || goals[0] || null
  const gid = selectedGoal?.goal_id || goalId
  const proposal = v7.patchProposals[0] || null
  const workspace = v7.workspaces[0] || null
  const validation = v7.sandboxRuns[0] || null
  const approval = v7.applyApprovals[0] || null
  const applied = v7.appliedChanges[0] || null
  const rollbackArtifact = v7.rollbackArtifacts[0] || null
  const mode = Number(v7.executionMode || 0)

  useEffect(() => {
    if (goals[0]?.goal_id && !goalId) setGoalId(goals[0].goal_id)
  }, [goals, goalId])

  useEffect(() => {
    if (project?.id && !isHandoff) refreshV7(project.id).catch(() => {})
  }, [project?.id, isHandoff, refreshV7])

  const run = async (key, fn) => {
    if (busy) return
    setBusy(key)
    try {
      await fn()
      toastSuccess('V7 step completed')
      if (project?.id) refreshV7(project.id).catch(() => {})
    } catch (err) {
      toastError(err?.message || 'V7 step failed')
    } finally {
      setBusy('')
    }
  }

  const parseFiles = () => {
    try {
      const parsed = JSON.parse(filesJson || '[]')
      return Array.isArray(parsed) ? parsed : []
    } catch {
      toastError('File patch JSON is invalid')
      return null
    }
  }

  const canUse = project?.id && gid && !isHandoff

  return (
    <div className="af2-grid af2-grid--2">
      <Panel title="Execution Mode" icon="zap" actions={<Btn sm variant="ghost" onClick={() => { refreshV5(); project?.id && refreshV7(project.id).catch(() => {}) }} disabled={!project}>Refresh</Btn>}>
        {isHandoff && <Pill tone="warn" pulse={false}>IMPORT REQUIRED BEFORE EXECUTION</Pill>}
        <div style={{ display: 'grid', gap: 10, marginTop: isHandoff ? 12 : 0 }}>
          <select className="af2-input" value={mode} onChange={e => setMode(Number(e.target.value))}>
            <option value={0}>Level 0 - read-only / plan-only</option>
            <option value={1}>Level 1 - proposal mode</option>
            <option value={2}>Level 2 - sandbox apply</option>
            <option value={3}>Level 3 - approved apply</option>
            <option value={4}>Level 4 - GitHub publish</option>
          </select>
          <select className="af2-input" value={gid || ''} onChange={e => setGoalId(e.target.value)} disabled={!goals.length}>
            {!goals.length && <option value="">No V5 goals available</option>}
            {goals.map(goal => <option key={goal.goal_id || goal.title} value={goal.goal_id}>{goal.title || goal.goal_id}</option>)}
          </select>
          <div style={{ color: 'var(--af2-muted)', font: '400 12.5px/1.6 var(--af2-sans)' }}>Level 0 can only read/plan. Level 1 creates proposals. Level 2 applies only in an isolated workspace. Level 3 still requires an approved apply request before the real workspace changes. GitHub publish remains a separate confirmation flow.</div>
        </div>
      </Panel>

      <Panel title="Patch Proposal" icon="diff">
        <div style={{ display: 'grid', gap: 9 }}>
          <input className="af2-input" value={summary} onChange={e => setSummary(e.target.value)} placeholder="Patch summary"/>
          <textarea className="af2-input" value={filesJson} onChange={e => setFilesJson(e.target.value)} style={{ minHeight: 120, resize: 'vertical', fontFamily: 'var(--af2-mono)' }} placeholder="File patch JSON: [{ path, content }]"/>
          <textarea className="af2-input" value={diff} onChange={e => setDiff(e.target.value)} style={{ minHeight: 90, resize: 'vertical', fontFamily: 'var(--af2-mono)' }} placeholder="Unified diff, optional"/>
          <Btn variant="primary" icon="spark" disabled={!canUse || mode < 1 || busy === 'propose'} onClick={() => run('propose', async () => {
            const files = parseFiles()
            if (!files) return
            await proposePatch(project.id, gid, { goal: selectedGoal, summary: summary || selectedGoal?.title, files, diff, risk_level: 'SAFE' })
          })}>{busy === 'propose' ? 'Proposing' : 'Propose Patch'}</Btn>
          {proposal && <div className="af2-row"><span>{proposal.title}</span><Pill sm tone={proposal.risk_level === 'SAFE' ? 'success' : 'warn'} pulse={false}>{proposal.risk_level}</Pill></div>}
        </div>
      </Panel>

      <Panel title="Sandbox Validation" icon="pipeline">
        <div style={{ display: 'grid', gap: 9 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn sm variant="primary" icon="files" disabled={!canUse || mode < 2 || !proposal || busy === 'sandbox'} onClick={() => run('sandbox', () => createSandbox(project.id, gid, { goal: selectedGoal, patch_artifact_id: proposal.artifact_id }))}>Create Sandbox</Btn>
            <Btn sm variant="primary" icon="diff" disabled={mode < 2 || !workspace || busy === 'apply_sandbox'} onClick={() => run('apply_sandbox', () => applySandbox(workspace.workspace_id))}>Apply In Sandbox</Btn>
            <Btn sm variant="primary" icon="check" disabled={mode < 2 || !workspace || busy === 'validate'} onClick={() => run('validate', () => validateWorkspace(workspace.workspace_id))}>Validate</Btn>
          </div>
          <div className="af2-row"><span>Workspace</span><Pill sm pulse={false}>{workspace?.mode || 'unavailable'}</Pill></div>
          <div className="af2-row"><span>Status</span><Pill sm tone={workspace?.status === 'validated' ? 'success' : 'idle'} pulse={false}>{workspace?.status || 'unavailable'}</Pill></div>
          {(validation?.commands || []).slice(0, 6).map(cmd => <div key={cmd.id} className="af2-row"><span>{cmd.label}</span><Pill sm tone={cmd.status === 'passed' ? 'success' : cmd.status === 'failed' ? 'danger' : 'idle'} pulse={false}>{cmd.status}</Pill></div>)}
        </div>
      </Panel>

      <Panel title="Apply Approval" icon="check">
        <div style={{ display: 'grid', gap: 9 }}>
          <Btn variant="primary" icon="bell" disabled={!canUse || mode < 2 || !workspace || busy === 'request'} onClick={() => run('request', () => requestApply(project.id, gid, { goal: selectedGoal, stage_only: false }))}>Request Apply Approval</Btn>
          {approval && <>
            <div className="af2-row"><span>{approval.summary}</span><Pill sm tone={approval.status === 'approved' ? 'success' : approval.status === 'rejected' ? 'danger' : 'warn'} pulse={false}>{approval.status}</Pill></div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Btn sm variant="primary" icon="check" disabled={busy === 'approve' || approval.status !== 'pending'} onClick={() => run('approve', () => approveApply(approval.approval_id))}>Approve</Btn>
              <Btn sm variant="ghost" icon="cross" disabled={busy === 'reject' || approval.status !== 'pending'} onClick={() => run('reject', () => rejectApply(approval.approval_id, { reason: 'Rejected from V7 panel' }))}>Reject</Btn>
              <Btn sm variant="primary" icon="play" disabled={mode < 3 || approval.status !== 'approved' || busy === 'apply'} onClick={() => run('apply', () => applyWorkspace(project.id, gid, { goal: selectedGoal, approval_id: approval.approval_id }))}>Apply To Workspace</Btn>
            </div>
          </>}
        </div>
      </Panel>

      <Panel title="Applied Changes & Rollback" icon="history">
        <div style={{ display: 'grid', gap: 9 }}>
          <div className="af2-row"><span>Applied files</span><Pill sm tone={applied?.files_applied?.length ? 'success' : 'idle'} pulse={false}>{applied?.files_applied?.length || 0}</Pill></div>
          <Btn sm variant="primary" icon="check" disabled={!canUse || !applied || busy === 'post'} onClick={() => run('post', () => postValidate(project.id, gid, { goal: selectedGoal }))}>Post-Apply Validate</Btn>
          <div className="af2-row"><span>Rollback</span><Pill sm tone={rollbackArtifact?.status === 'available' ? 'warn' : rollbackArtifact?.status === 'applied' ? 'success' : 'idle'} pulse={false}>{rollbackArtifact?.status || 'unavailable'}</Pill></div>
          <Btn sm variant="ghost" icon="history" disabled={!canUse || rollbackArtifact?.status !== 'available' || busy === 'rollback'} onClick={() => run('rollback', () => rollback(project.id, gid, { goal: selectedGoal, rollback_id: rollbackArtifact.rollback_id, confirm: true }))}>Rollback With Confirmation</Btn>
          {v7.error && <div style={{ color: '#F87171', font: '400 12px/1.5 var(--af2-sans)' }}>{v7.error}</div>}
        </div>
      </Panel>
    </div>
  )
}

/* ── Footer ────────────────────────────────────────────────────── */
function ForgeFooter({ runState, project, agents }) {
  const activeCount = agents.filter(a => a.status && a.status !== 'idle').length
  const activeRun = ['running', 'planning', 'testing', 'executing', 'in_progress', 'agentic', 'reviewing'].includes(String(runState || '').toLowerCase())
  return (
    <footer className="af2-footer">
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span className={`af2-status-dot af2-status-dot--${activeRun ? 'running' : 'pending'}`} style={{ animation: 'af2Pulse 2s ease-in-out infinite' }}/>
          <span style={{ color: activeRun ? '#4ADE80' : '#F59E0B' }}>{activeRun ? 'FORGE ACTIVE' : (runState || 'IDLE').toUpperCase()}</span>
        </span>
        <span style={{ color: 'var(--af2-dim)' }}>·</span>
        <span><span style={{ color: 'var(--af2-bronze-bright)' }}>{activeCount}</span> AGENTS</span>
        {project && <>
          <span style={{ color: 'var(--af2-dim)' }}>·</span>
          <span>{project.name || project.id}</span>
        </>}
      </div>
      <div style={{ flex: 1 }}/>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, font: '500 9.5px var(--af2-mono)', letterSpacing: '0.10em', color: 'var(--af2-muted)', textTransform: 'uppercase' }}>
        <span>ASCEND FORGE</span>
        <span style={{ color: 'var(--af2-dim)' }}>·</span>
        <span style={{ color: 'var(--af2-bronze-bright)' }}>v2.4</span>
      </div>
    </footer>
  )
}

/* ═══ MAIN PAGE ════════════════════════════════════════════════════ */
const CLOSED_ACTION_STATUSES = new Set(['staged', 'verified', 'applied', 'verify_failed', 'rejected', 'failed', 'blocked', 'deployed'])

function needsOperatorDecision(action) {
  const normalized = normalizeAction(action)
  return isPendingAction(normalized) && !CLOSED_ACTION_STATUSES.has((normalized.status || '').toLowerCase())
}

export default function AscendForgePage() {
  const [project, setProject]     = useState(null)
  const [showNewProj, setShowNewProj] = useState(false)
  const [view, setView]           = useState('projects')
  const [runState, setRunState]   = useState('idle')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages]   = useState([])
  const [sending, setSending]     = useState(false)
  const [actions, setActions]     = useState([])
  const [busyActions, setBusyActions] = useState({})
  const [termLines, setTermLines] = useState([])
  const [computePlan, setComputePlan] = useState(null)
  const [executedRoute, setExecutedRoute] = useState(null)
  const [activeRun, setActiveRun] = useState(null)
  const [runBusy, setRunBusy]     = useState(false)
  const [provider, setProvider]   = useState('anthropic')
  const forge = useForgeStore(useShallow(s => ({
    activeRun: s.activeRun,
    actions: s.actions,
    pendingApprovals: s.pendingApprovals,
    unsupportedActions: s.unsupportedActions,
    refresh: s.refresh,
    ensurePolling: s.ensurePolling,
    applyForgeEvent: s.applyForgeEvent,
    selectProject: s.selectProject,
    selectRun: s.selectRun,
  })))

  const addTerm = (text, type = 'out') => setTermLines(p => [...p.slice(-400), { text, type, ts: Date.now() }])
  const mergeActions = useCallback((items) => setActions(prev => mergeActionLists(prev, items)), [])

  useEffect(() => {
    forge.ensurePolling?.()
    forge.refresh?.({ silent: true, reason: 'forge_page_mount' }).catch(() => {})
  }, [forge.ensurePolling, forge.refresh])

	  useEffect(() => {
	    if (project?.id) forge.selectProject?.(project.id)
	  }, [project?.id, forge.selectProject])

	  useEffect(() => {
	    let alive = true
	    const openHandoffFromHash = async () => {
	      const hash = String(window.location.hash || '')
	      const match = hash.match(/(?:^#?\/?forge\/|forge_project_id=)([A-Za-z0-9._:-]+)/)
	      if (!match) return
	      const projectId = match[1]
	      try {
	        const result = await api.forge.v5.getBrief(projectId)
	        if (!alive || !result?.brief) return
	        setProject({
	          id: projectId,
	          name: result.brief.title || `Orders handoff ${compactId(projectId)}`,
	          target_type: 'orders_handoff',
	          write_access: false,
	          handoff: true,
	          source: 'orders',
	        })
	        setView('v5_project')
	      } catch {
	        // Unknown hashes are ignored by AscendForge.
	      }
	    }
	    openHandoffFromHash()
	    window.addEventListener('hashchange', openHandoffFromHash)
	    return () => { alive = false; window.removeEventListener('hashchange', openHandoffFromHash) }
	  }, [])

  useEffect(() => {
    if (forge.activeRun) {
      setActiveRun(forge.activeRun)
      setRunState(forge.activeRun.status || 'idle')
    }
  }, [forge.activeRun])

  useEffect(() => {
    if (forge.actions?.length) mergeActions(forge.actions)
  }, [forge.actions, mergeActions])

  useEffect(() => {
    const handler = e => {
      const { type, data } = e.detail || {}
      if (type === 'task:compute_plan') setComputePlan(data)
      if (type === 'task:compute_plan_executed') setExecutedRoute(data)
    }
    window.addEventListener('ws:event', handler)
    return () => window.removeEventListener('ws:event', handler)
  }, [])

  // Forge session when project changes
  useEffect(() => {
    if (!project?.id) return
    JPOST('/api/forge/sessions', { project_id: project.id, provider })
      .then(r => r.json())
      .then(d => { setSessionId(d.session_id); setMessages(d.history || []) })
      .catch(e => toastError(`Session error: ${e.message}`))
  }, [project?.id, provider])

  // Hotkeys
  useEffect(() => {
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setPaletteOpen(p => !p); return }
      if (e.key === 'Escape') { setPaletteOpen(false); return }
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      const idx = parseInt(e.key, 10) - 1
      if (!isNaN(idx) && VIEWS[idx]) setView(VIEWS[idx].id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const sendAutoRun = useCallback(async (text, opts = {}) => {
    if (!project?.id || !text.trim() || sending) return
    setSending(true)
    setRunState('running')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    addTerm('Full Auto run started — planner → coder → tester loop…', 'cmd')
    setView('activity')
    try {
      const resp = await fetch('/api/forge/agentic-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {}) },
        body: JSON.stringify({ project_id: project.id, goal: text, provider, ownerApproved: true, max_iterations: 3 }),
      })
      const d = await resp.json()
      if (!resp.ok || d.ok === false) throw new Error(d.error || `HTTP ${resp.status}`)
      if (d.run) {
        setActiveRun(d.run)
        forge.applyForgeEvent?.('forge:run_updated', { run: d.run })
        mergeActions(d.run.actions || [])
      }
      if (d.final_report) {
        const report = d.final_report
        addTerm(`Auto run complete — ${report.applied?.length || 0} file(s) applied`, 'success')
        setMessages(p => [...p, { role: 'assistant', content: report.summary || 'Auto run complete.' }])
        if (report.test_result) {
          const tr = report.test_result
          addTerm(`Tests: ${tr.all_passed ? 'ALL PASSED' : 'FAILURES DETECTED'}`, tr.all_passed ? 'success' : 'err')
        }
      } else {
        const msg = `Auto run finished — status: ${d.status || d.run?.status || 'complete'}`
        addTerm(msg, 'success')
        setMessages(p => [...p, { role: 'assistant', content: msg }])
      }
      setRunState('idle')
      setView('history')
    } catch (e) {
      toastError(`Auto run failed: ${e.message}`)
      addTerm(`Error: ${e.message}`, 'err')
      setRunState('idle')
    } finally {
      setSending(false)
    }
  }, [project, sending, provider, mergeActions, forge.applyForgeEvent])

  const sendGoal = useCallback(async (text, opts = {}) => {
    if (!sessionId || !text.trim() || sending) return
    setSending(true)
    setRunState('running')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    addTerm(`Sending goal to Forge…`, 'cmd')
    setView('activity')

    const { mode = 'balanced', autoApprove = 'safe' } = opts
    try {
      const resp = await fetch('/api/forge/runs/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {}) },
        body: JSON.stringify({ project_id: project.id, goal: text, provider, mode, auto_approve: autoApprove, max_iterations: 3 }),
      })
      if (!resp.ok) { const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` })); throw new Error(err.error || `HTTP ${resp.status}`) }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = '', evtName = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (line.startsWith('event: ')) { evtName = line.slice(7).trim(); continue }
          if (!line.startsWith('data: ')) continue
          try {
            const d = JSON.parse(line.slice(6))
            if (evtName === 'run' || d.run) {
              const run = d.run || d
              setActiveRun(run)
              forge.applyForgeEvent?.('forge:run_updated', { run })
              addTerm(`Run started: ${run.run_id || ''}`, 'info')
              if (d.actions?.length) mergeActions(d.actions)
            } else if (evtName === 'done' || d.run_id) {
              setRunState('idle')
              addTerm('Run complete.', 'success')
              forge.refresh?.({ silent: true, reason: 'stream_done', run_id: activeRun?.run_id || activeRun?.id }).catch(() => {})
              if (d.actions) mergeActions(d.actions)
            } else if (evtName === 'error') {
              addTerm(`Forge error: ${d.error}`, 'err')
              setRunState('idle')
            } else if (evtName === 'progress') {
              addTerm(d.message || d.stage || 'Working…', 'info')
            } else if (d.type === 'action') {
              forge.applyForgeEvent?.('forge:action_updated', { action: d.action })
              mergeActions([d.action])
            } else if (d.type === 'message') {
              setMessages(p => [...p, { role: 'assistant', content: d.content || d.message }])
            } else if (d.type === 'log') {
              addTerm(d.message || d.content, d.level || 'out')
            }
            evtName = ''
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e) {
      toastError(`Forge error: ${e.message}`)
      addTerm(`Error: ${e.message}`, 'err')
      setRunState('idle')
    } finally {
      setSending(false)
    }
  }, [sessionId, sending, project, provider, mergeActions, activeRun, forge.applyForgeEvent, forge.refresh])

  const handleApprove = useCallback(async (action) => {
    const id = action.id || action.action_id
    if (!id || busyActions[id]) return
    setBusyActions(p => ({ ...p, [id]: true }))
    try {
      const resp = await JPOST(`/api/forge/actions/${id}/approve`, { run_id: activeRun?.run_id })
      const data = await resp.json().catch(() => ({}))
      const updatedAction = data.action || { ...action, status: data.ok === false ? 'failed' : 'completed' }
      mergeActions([updatedAction])
      forge.applyForgeEvent?.('forge:action_updated', { action: updatedAction })
      forge.refresh?.({ silent: true, reason: 'action_approved', run_id: activeRun?.run_id || activeRun?.id }).catch(() => {})
      addTerm(`Approved: ${action.description || id}`, 'success')
      toastSuccess(data.output || 'Action approved')
    } catch (e) {
      toastError(`Approve failed: ${e.message}`)
    } finally {
      setBusyActions(p => { const n = { ...p }; delete n[id]; return n })
    }
  }, [busyActions, activeRun, mergeActions, forge.applyForgeEvent, forge.refresh])

  const handleReject = useCallback(async (action) => {
    const id = action.id || action.action_id
    if (!id || busyActions[id]) return
    setBusyActions(p => ({ ...p, [id]: true }))
    try {
      const resp = await JPOST(`/api/forge/actions/${id}/reject`, { run_id: activeRun?.run_id })
      const data = await resp.json().catch(() => ({}))
      const updatedAction = data.action || { ...action, status: 'rejected' }
      mergeActions([updatedAction])
      forge.applyForgeEvent?.('forge:action_updated', { action: updatedAction })
      forge.refresh?.({ silent: true, reason: 'action_rejected', run_id: activeRun?.run_id || activeRun?.id }).catch(() => {})
      addTerm(`Rejected: ${action.description || id}`, 'warn')
      toastSuccess('Action rejected')
    } catch (e) {
      toastError(`Reject failed: ${e.message}`)
    } finally {
      setBusyActions(p => { const n = { ...p }; delete n[id]; return n })
    }
  }, [busyActions, activeRun, mergeActions, forge.applyForgeEvent, forge.refresh])

	  const pendingCount = useMemo(() => Math.max(actions.filter(needsOperatorDecision).length, forge.pendingApprovals?.length || 0), [actions, forge.pendingApprovals])

  const agents = useMemo(() => {
    const run = forge.activeRun || activeRun
    const transcript = run?.final_report?.transcript || []
    const last = transcript[transcript.length - 1] || null
    if (last) {
      return ['planner', 'coder', 'tester', 'security', 'reviewer']
        .map(key => last[key] ? {
          id: key,
          name: key.charAt(0).toUpperCase() + key.slice(1),
          model: last[key].model || run?.provider || 'forge-agent',
          status: last[key].status || 'done',
          load: 0,
          task: last[key].output?.summary || last[key].summary || `${key} stage evidence available`,
        } : null)
        .filter(Boolean)
    }
    const state = String(run?.status || runState || 'idle').toLowerCase()
    if (['running', 'planning', 'testing', 'executing', 'reviewing'].includes(state)) {
      return [{ id: 'telemetry', name: 'Agent Telemetry', model: run?.provider || 'forge', status: 'unavailable', load: 0, task: 'Backend run is active; per-agent telemetry is unavailable.' }]
    }
    return []
  }, [forge.activeRun, activeRun, runState])

  const effectiveRunState = (forge.activeRun || activeRun)?.status || runState

  const handleToggleRun = useCallback(async () => {
    const run = forge.activeRun || activeRun
    const runId = run?.run_id || run?.id
    if (!runId) {
      toastError('No backend run selected')
      return
    }
    const state = String(run.status || '').toLowerCase()
    const isRunning = ['running', 'planning', 'testing', 'executing', 'in_progress', 'agentic', 'reviewing'].includes(state)
    const action = state === 'paused' ? 'resume' : isRunning ? 'pause' : null
    if (!action) {
      const reason = forge.unsupportedActions?.pause?.reason || forge.unsupportedActions?.resume?.reason || `Run control unsupported in status ${run.status || 'unknown'}`
      toastError(reason)
      return
    }
    setRunBusy(true)
    try {
      const result = action === 'pause' ? await api.forge.pauseRun(runId) : await api.forge.resumeRun(runId)
      if (result.run) {
        setActiveRun(result.run)
        setRunState(result.run.status || 'idle')
        forge.applyForgeEvent?.('forge:run_updated', { run: result.run })
      }
      forge.refresh?.({ silent: true, reason: `run_${action}`, run_id: runId }).catch(() => {})
      toastSuccess(action === 'pause' ? 'Run paused' : 'Run resumed')
    } catch (err) {
      toastError(err?.message || `Run ${action} failed`)
    } finally {
      setRunBusy(false)
    }
  }, [activeRun, forge])

	  const handleSelectProject = (p) => {
	    setProject(p)
    setView('compose')
    setMessages([])
    setActions([])
    setActiveRun(null)
	  }

  const handleNewProject = (p) => {
    setProject(p)
    setView('compose')
    toastSuccess(`Project "${p.name || p.id}" created`)
  }

  return (
    <div className="af2-root">
      {/* Ambient layers */}
      <div className="af2-ambient"/>
      <div className="af2-grain"/>
      <div className="af2-scanlines"/>

        <ForgeTopBar
        activeView={view}
        project={project}
        runState={effectiveRunState}
        onToggleRun={handleToggleRun}
        onPaletteOpen={() => setPaletteOpen(true)}
        pendingCount={pendingCount}
      />

      <div className="af2-body">
        <LeftRail active={view} onChange={setView} pendingCount={pendingCount}/>

        <main className="af2-main">
	          {view === 'projects'  && <ProjectsView onSelect={handleSelectProject} onNew={() => setShowNewProj(true)}/>}
	          {view === 'compose'   && <ComposeView project={project} onSubmit={(goal, opts) => sendGoal(goal, opts)} onAutoRun={(goal, opts) => sendAutoRun(goal, opts)} onSwitchProject={() => setView('projects')}/>}
	          {view === 'queue'     && <ForgeQueueView project={project}/>}
	          {view === 'activity'  && <ActivityView messages={messages} termLines={termLines} sending={sending} agents={agents} computePlan={computePlan} executedRoute={executedRoute}/>}
          {view === 'review'    && <ReviewView actions={actions} onApprove={handleApprove} onReject={handleReject}/>}
          {view === 'approvals' && <ApprovalsView actions={actions} onApprove={handleApprove} onReject={handleReject}/>}
          {view === 'pipeline'  && <PipelineView activeRun={activeRun}/>}
          {view === 'v5_project' && <V5ProjectView project={project} onPrepared={p => { if (p) setProject(p) }}/>}
          {view === 'v5_goals' && <V5GoalsView project={project} onRun={run => {
            if (run) {
              setActiveRun(run)
              forge.applyForgeEvent?.('forge:run_updated', { run })
            }
          }}/>}
	          {view === 'v5_reasoning' && <V5ReasoningView project={project}/>}
	          {view === 'v5_quality' && <V5QualityView project={project}/>}
	          {view === 'v7_execution' && <V7ExecutionView project={project}/>}
	          {view === 'github' && <GitHubPublishView project={project}/>}
	          {view === 'files'     && <FilesView project={project}/>}
          {view === 'history'   && <HistoryView project={project}/>}
          {view === 'agents'    && <AgentsView agents={agents}/>}
          {view === 'terminal'  && <TerminalView termLines={termLines}/>}
        </main>
      </div>

      <ForgeFooter runState={effectiveRunState} project={project} agents={agents}/>

      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} onSelectView={v => { setView(v); setPaletteOpen(false) }}/>}
      {showNewProj && <NewProjectModal onClose={() => setShowNewProj(false)} onCreate={handleNewProject}/>}
    </div>
  )
}

/* NEXUS OS — Mobile shared UI primitives */
import { useEffect, useRef } from 'react'

// ── TopBar ────────────────────────────────────────────────────────────────────
export function TopBar({ title, subtitle, right, onSearch, onBell, unread = 0 }) {
  return (
    <div style={S.topBar}>
      <div style={S.topBarLeft}>
        <div style={S.topBarTitle}>{title}</div>
        {subtitle && <div style={S.topBarSub}>{subtitle}</div>}
      </div>
      <div style={S.topBarRight}>
        {onSearch && (
          <button style={S.topBarBtn} onClick={onSearch} aria-label="Search">
            <span style={S.topBarBtnIcon}>⌕</span>
          </button>
        )}
        {onBell && (
          <button style={{ ...S.topBarBtn, position: 'relative' }} onClick={onBell} aria-label="Notifications">
            <span style={S.topBarBtnIcon}>🔔</span>
            {unread > 0 && <span style={S.badge}>{unread > 9 ? '9+' : unread}</span>}
          </button>
        )}
        {right}
      </div>
    </div>
  )
}

// ── Section ───────────────────────────────────────────────────────────────────
export function Section({ label, right, children }) {
  return (
    <div style={S.section}>
      {(label || right) && (
        <div style={S.sectionHead}>
          {label && <span style={S.sectionLabel}>{label}</span>}
          {right && <span style={S.sectionRight}>{right}</span>}
        </div>
      )}
      {children}
    </div>
  )
}

// ── KPITile ───────────────────────────────────────────────────────────────────
export function KPITile({ label, value, unit, delta, live, color = 'gold', onClick }) {
  const colors = {
    gold:  { accent: 'var(--gold)', bg: 'rgba(229,199,107,0.07)' },
    green: { accent: 'var(--success)', bg: 'rgba(34,197,94,0.07)' },
    red:   { accent: 'var(--error)', bg: 'rgba(239,68,68,0.07)' },
    cyan:  { accent: '#22d3ee', bg: 'rgba(34,211,238,0.07)' },
    blue:  { accent: 'var(--info)', bg: 'rgba(96,165,250,0.07)' },
  }
  const c = colors[color] || colors.gold
  return (
    <div style={{ ...S.kpiTile, background: c.bg, borderColor: live ? c.accent : 'var(--border-subtle)' }} onClick={onClick}>
      <div style={S.kpiCorner} />
      <div style={S.kpiLabel}>{label}</div>
      <div style={{ ...S.kpiValue, color: c.accent }}>
        {value ?? '—'}
        {unit && <span style={S.kpiUnit}>{unit}</span>}
      </div>
      {delta !== undefined && (
        <div style={{ ...S.kpiDelta, color: delta >= 0 ? 'var(--success)' : 'var(--error)' }}>
          {delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}%
        </div>
      )}
      {live && <div style={{ ...S.liveDot, background: c.accent }} />}
    </div>
  )
}

// ── KPIGrid ───────────────────────────────────────────────────────────────────
export function KPIGrid({ children }) {
  return <div style={S.kpiGrid}>{children}</div>
}

// ── ProgressBar ───────────────────────────────────────────────────────────────
export function ProgressBar({ value = 0, max = 100, color = 'var(--gold)', height = 3 }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div style={{ ...S.progressTrack, height }}>
      <div style={{ ...S.progressFill, width: `${pct}%`, background: color, height }} />
    </div>
  )
}

// ── Sparkline (SVG) ───────────────────────────────────────────────────────────
export function Sparkline({ data = [], color = 'var(--gold)', width = 80, height = 28 }) {
  if (data.length < 2) return <div style={{ width, height }} />
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((v - min) / range) * (height - 4) - 2
    return `${x},${y}`
  }).join(' ')
  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

// ── RingGauge (SVG) ───────────────────────────────────────────────────────────
export function RingGauge({ value = 0, max = 100, size = 64, color = 'var(--gold)', label }) {
  const r = (size / 2) - 6
  const circ = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(1, value / max))
  const dash = pct * circ
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(229,199,107,0.1)" strokeWidth="5" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="5"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" />
      </svg>
      {label && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          {label}
        </div>
      )}
    </div>
  )
}

// ── StatusPill ────────────────────────────────────────────────────────────────
export function StatusPill({ label, tone = 'idle' }) {
  const tones = {
    ok:       { bg: 'rgba(34,197,94,0.15)',   color: '#22c55e',  dot: '#22c55e' },
    warn:     { bg: 'rgba(245,158,11,0.15)',  color: '#f59e0b',  dot: '#f59e0b' },
    error:    { bg: 'rgba(239,68,68,0.15)',   color: '#ef4444',  dot: '#ef4444' },
    idle:     { bg: 'rgba(229,199,107,0.08)', color: 'var(--gold)', dot: 'var(--gold)' },
    inactive: { bg: 'rgba(100,100,120,0.15)', color: '#9ca3af',  dot: '#9ca3af' },
  }
  const t = tones[tone] || tones.idle
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 7px', borderRadius: 20,
      background: t.bg, color: t.color, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: t.dot, flexShrink: 0 }} />
      {label}
    </span>
  )
}

// ── Bubble (chat message) ─────────────────────────────────────────────────────
export function Bubble({ role, name, children }) {
  const isUser = role === 'user'
  const isSystem = role === 'system'
  if (isSystem) return (
    <div style={S.bubbleSystem}>{children}</div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
      {!isUser && name && <div style={S.bubbleName}>{name}</div>}
      <div style={isUser ? S.bubbleUser : S.bubbleAssistant}>{children}</div>
    </div>
  )
}

// ── Sheet (bottom slide-up) ───────────────────────────────────────────────────
export function Sheet({ open, onClose, title, children }) {
  if (!open) return null
  return (
    <>
      <div style={S.sheetOverlay} onClick={onClose} />
      <div style={S.sheet}>
        <div style={S.sheetHandle} />
        {title && <div style={S.sheetTitle}>{title}</div>}
        <div style={S.sheetBody}>{children}</div>
      </div>
    </>
  )
}

// ── Row ───────────────────────────────────────────────────────────────────────
export function Row({ icon, label, value, onClick, chevron = false, badge }) {
  return (
    <div style={{ ...S.row, cursor: onClick ? 'pointer' : 'default' }} onClick={onClick}>
      {icon && <span style={S.rowIcon}>{icon}</span>}
      <span style={S.rowLabel}>{label}</span>
      {badge && <span style={S.rowBadge}>{badge}</span>}
      {value && <span style={S.rowValue}>{value}</span>}
      {chevron && <span style={S.rowChevron}>›</span>}
    </div>
  )
}

// ── AgentCard (compact) ───────────────────────────────────────────────────────
export function AgentCard({ agent, onClick }) {
  const tone = agent.status === 'active' ? 'ok' : agent.status === 'error' ? 'error' : 'idle'
  return (
    <div style={S.agentCard} onClick={onClick}>
      <div style={S.agentCardIcon}>{(agent.name || agent.id || 'A')[0].toUpperCase()}</div>
      <div style={S.agentCardBody}>
        <div style={S.agentCardName}>{agent.name || agent.id}</div>
        <div style={S.agentCardSub}>{agent.role || agent.type || 'Agent'}</div>
      </div>
      <StatusPill label={agent.status || 'idle'} tone={tone} />
    </div>
  )
}

// ── TaskCard (compact) ────────────────────────────────────────────────────────
export function TaskCard({ task, onClick }) {
  const pct = task.progress ?? (task.status === 'completed' ? 100 : task.status === 'running' ? 50 : 0)
  const color = task.status === 'completed' ? 'var(--success)' : task.status === 'failed' ? 'var(--error)' : 'var(--gold)'
  return (
    <div style={S.taskCard} onClick={onClick}>
      <div style={S.taskCardHead}>
        <span style={S.taskCardTitle}>{task.name || task.goal || task.task || 'Task'}</span>
        <StatusPill label={task.status || 'pending'} tone={task.status === 'completed' ? 'ok' : task.status === 'failed' ? 'error' : 'idle'} />
      </div>
      <ProgressBar value={pct} color={color} />
      {task.assigned_to && <div style={S.taskCardSub}>→ {task.assigned_to}</div>}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
export function Empty({ icon = '◇', message }) {
  return (
    <div style={S.empty}>
      <div style={S.emptyIcon}>{icon}</div>
      <div style={S.emptyMsg}>{message}</div>
    </div>
  )
}

// ── Spinner ───────────────────────────────────────────────────────────────────
export function Spinner({ size = 20, color = 'var(--gold)' }) {
  return (
    <div style={{ width: size, height: size, border: `2px solid rgba(229,199,107,0.15)`,
      borderTopColor: color, borderRadius: '50%', animation: 'nx-spin 0.7s linear infinite' }} />
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  topBar: { display: 'flex', alignItems: 'center', padding: '12px 16px 10px', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0 },
  topBarLeft: { flex: 1, minWidth: 0 },
  topBarTitle: { fontSize: 15, fontWeight: 700, color: 'var(--gold)', letterSpacing: '0.06em', fontFamily: 'var(--nx-font-mono, monospace)' },
  topBarSub: { fontSize: 10, color: 'var(--text-muted)', marginTop: 1 },
  topBarRight: { display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 },
  topBarBtn: { width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'none', border: '1px solid var(--border-subtle)', borderRadius: 8, cursor: 'pointer', position: 'relative' },
  topBarBtnIcon: { fontSize: 14, color: 'var(--gold)' },
  badge: { position: 'absolute', top: -4, right: -4, background: 'var(--error)', color: '#fff',
    fontSize: 8, fontWeight: 700, borderRadius: 6, padding: '1px 4px', minWidth: 14, textAlign: 'center' },

  section: { marginBottom: 4 },
  sectionHead: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px 4px' },
  sectionLabel: { fontSize: 9, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-muted)' },
  sectionRight: { fontSize: 10, color: 'var(--gold)', cursor: 'pointer' },

  kpiGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '0 16px' },
  kpiTile: { borderRadius: 10, border: '1px solid', padding: '10px 12px', position: 'relative', overflow: 'hidden', cursor: 'default' },
  kpiCorner: { position: 'absolute', top: 0, right: 0, width: 16, height: 16,
    borderLeft: '1px solid rgba(229,199,107,0.2)', borderBottom: '1px solid rgba(229,199,107,0.2)',
    borderBottomLeftRadius: 4 },
  kpiLabel: { fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4 },
  kpiValue: { fontSize: 22, fontWeight: 700, fontFamily: 'var(--nx-font-mono, monospace)', lineHeight: 1 },
  kpiUnit: { fontSize: 11, marginLeft: 2, fontWeight: 400 },
  kpiDelta: { fontSize: 9, marginTop: 3 },
  liveDot: { position: 'absolute', top: 8, right: 8, width: 5, height: 5, borderRadius: '50%',
    animation: 'nx-pulse 2s ease-in-out infinite' },

  progressTrack: { background: 'rgba(229,199,107,0.1)', borderRadius: 2, overflow: 'hidden', width: '100%' },
  progressFill: { borderRadius: 2, transition: 'width 0.6s ease' },

  bubbleUser: { background: 'linear-gradient(135deg, rgba(229,199,107,0.22), rgba(229,199,107,0.12))',
    border: '1px solid rgba(229,199,107,0.3)', borderRadius: '14px 14px 4px 14px',
    padding: '8px 12px', fontSize: 13, color: 'var(--gold)', maxWidth: '80%' },
  bubbleAssistant: { background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
    borderRadius: '14px 14px 14px 4px', padding: '8px 12px', fontSize: 13, color: 'var(--text-primary)', maxWidth: '85%' },
  bubbleName: { fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 3, paddingLeft: 4 },
  bubbleSystem: { textAlign: 'center', fontSize: 10, color: 'var(--text-muted)', padding: '4px 16px', fontStyle: 'italic' },

  sheetOverlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 900 },
  sheet: { position: 'fixed', bottom: 0, left: 0, right: 0, background: 'var(--bg-card)',
    border: '1px solid var(--border-gold)', borderBottom: 'none', borderRadius: '16px 16px 0 0',
    zIndex: 901, maxHeight: '70vh', display: 'flex', flexDirection: 'column',
    animation: 'nx-slide-up 250ms cubic-bezier(0.32,0.72,0,1)' },
  sheetHandle: { width: 36, height: 4, background: 'rgba(229,199,107,0.3)', borderRadius: 2, margin: '12px auto 0' },
  sheetTitle: { padding: '12px 16px 8px', fontSize: 12, fontWeight: 700, color: 'var(--gold)', letterSpacing: '0.1em', textTransform: 'uppercase' },
  sheetBody: { flex: 1, overflowY: 'auto', padding: '0 0 24px' },

  row: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: '1px solid var(--border-subtle)' },
  rowIcon: { fontSize: 16, width: 24, textAlign: 'center', flexShrink: 0 },
  rowLabel: { flex: 1, fontSize: 13, color: 'var(--text-primary)' },
  rowBadge: { fontSize: 9, background: 'rgba(229,199,107,0.15)', color: 'var(--gold)', padding: '2px 6px', borderRadius: 10, fontWeight: 700 },
  rowValue: { fontSize: 11, color: 'var(--text-muted)' },
  rowChevron: { fontSize: 18, color: 'var(--text-muted)', lineHeight: 1 },

  agentCard: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
    borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' },
  agentCardIcon: { width: 34, height: 34, borderRadius: 8, background: 'rgba(229,199,107,0.12)',
    border: '1px solid rgba(229,199,107,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 14, fontWeight: 700, color: 'var(--gold)', flexShrink: 0 },
  agentCardBody: { flex: 1, minWidth: 0 },
  agentCardName: { fontSize: 13, color: 'var(--text-primary)', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  agentCardSub: { fontSize: 10, color: 'var(--text-muted)', marginTop: 1 },

  taskCard: { margin: '0 16px 8px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
    borderRadius: 10, padding: '10px 12px', cursor: 'pointer' },
  taskCardHead: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 },
  taskCardTitle: { flex: 1, fontSize: 12, color: 'var(--text-primary)', fontWeight: 600, minWidth: 0,
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  taskCardSub: { fontSize: 9, color: 'var(--text-muted)', marginTop: 4 },

  empty: { display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 16px', gap: 8 },
  emptyIcon: { fontSize: 28, color: 'rgba(229,199,107,0.3)' },
  emptyMsg: { fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' },
}

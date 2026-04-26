// Shared premium UI primitives — used across all pages

// ── Panel ─────────────────────────────────────────────────────────────────────
export function Panel({ title, badge, children, tone = 'gold', style = {}, bodyStyle = {} }) {
  const bc = tone === 'silver' ? 'rgba(216,216,224,0.14)' : tone === 'bronze' ? 'rgba(205,127,50,0.18)' : 'rgba(229,199,107,0.14)'
  const bg = tone === 'silver' ? 'var(--grad-card-silver)' : 'var(--grad-card)'
  return (
    <div style={{
      background: bg, border: `1px solid ${bc}`, borderRadius: 10,
      display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative',
      ...style,
    }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 1, background: tone === 'silver' ? 'linear-gradient(90deg, transparent, rgba(216,216,224,0.5), transparent)' : 'linear-gradient(90deg, transparent, rgba(229,199,107,0.5), transparent)' }} />
      {title && (
        <div style={{ padding: '10px 14px', borderBottom: `1px solid ${bc}`, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 10, fontFamily: 'var(--mono, monospace)', letterSpacing: '0.14em', textTransform: 'uppercase', color: tone === 'silver' ? 'var(--silver-dim, #8B8B9E)' : 'var(--text-2, #9A927E)', fontWeight: 500 }}>{title}</span>
          {badge}
        </div>
      )}
      <div style={{ flex: 1, padding: 14, minHeight: 0, overflow: 'auto', ...bodyStyle }}>{children}</div>
    </div>
  )
}

// ── Badge ─────────────────────────────────────────────────────────────────────
const BADGE_VARIANTS = {
  default: { color: 'rgba(255,255,255,0.35)', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.07)' },
  gold:    { color: 'var(--gold, #E5C76B)',   bg: 'rgba(212,175,55,0.08)',  border: 'rgba(212,175,55,0.2)' },
  teal:    { color: 'var(--teal, #20D6C7)',   bg: 'rgba(32,214,199,0.08)', border: 'rgba(32,214,199,0.2)' },
  green:   { color: '#22C55E',                bg: 'rgba(34,197,94,0.08)',  border: 'rgba(34,197,94,0.2)' },
  warn:    { color: '#F59E0B',                bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.2)' },
  error:   { color: '#EF4444',               bg: 'rgba(239,68,68,0.08)',  border: 'rgba(239,68,68,0.2)' },
}
export function Badge({ label, variant = 'default' }) {
  const v = BADGE_VARIANTS[variant] || BADGE_VARIANTS.default
  return (
    <span style={{ fontSize: 10, fontFamily: 'var(--mono, monospace)', letterSpacing: '0.07em', textTransform: 'uppercase', color: v.color, padding: '2px 6px', background: v.bg, borderRadius: 4, border: `1px solid ${v.border}`, whiteSpace: 'nowrap' }}>
      {label}
    </span>
  )
}

// ── StatusDot ─────────────────────────────────────────────────────────────────
const DOT_COLORS = { running: '#22C55E', busy: '#F59E0B', idle: '#50506A', online: '#22C55E', offline: '#EF4444', pass: '#22C55E', warn: '#F59E0B', fail: '#EF4444' }
const DOT_GLOW   = { running: 'rgba(34,197,94,.5)', busy: 'rgba(245,158,11,.5)', online: 'rgba(34,197,94,.5)', offline: 'rgba(239,68,68,.5)', pass: 'rgba(34,197,94,.5)', warn: 'rgba(245,158,11,.5)', fail: 'rgba(239,68,68,.5)' }
export function StatusDot({ status, size = 7 }) {
  const bg = DOT_COLORS[status] || DOT_COLORS.idle
  const glow = DOT_GLOW[status]
  return (
    <span style={{ display: 'inline-block', width: size, height: size, borderRadius: '50%', flexShrink: 0, background: bg, boxShadow: glow ? `0 0 7px ${glow}` : 'none' }} />
  )
}

// ── MiniBar ───────────────────────────────────────────────────────────────────
export function MiniBar({ value, color = 'var(--gold)', style = {} }) {
  const pct = Math.min(100, Math.max(0, value || 0))
  return (
    <div style={{ height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden', ...style }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width .5s ease', boxShadow: `0 0 6px ${color}` }} />
    </div>
  )
}

// ── GaugeRing ─────────────────────────────────────────────────────────────────
export function GaugeRing({ value, color, label, size = 72 }) {
  const stroke = 5, r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const offset = circ - (Math.min(100, Math.max(0, value || 0)) / 100) * circ
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
      <div style={{ position: 'relative', width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.07)" strokeWidth={stroke} fill="none" />
          <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} strokeLinecap="round" fill="none"
            strokeDasharray={circ} strokeDashoffset={offset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ filter: `drop-shadow(0 0 5px ${color})`, transition: 'stroke-dashoffset .6s ease' }} />
        </svg>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 500, color: 'var(--text-primary, #F0E9D2)' }}>{Math.round(value || 0)}%</span>
        </div>
      </div>
      <span style={{ fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary, #9A927E)' }}>{label}</span>
    </div>
  )
}

// ── StatCard ──────────────────────────────────────────────────────────────────
export function StatCard({ label, value, sub, color = 'var(--text-primary, #F0E9D2)', accent = false }) {
  return (
    <div style={{
      padding: '13px 15px', borderRadius: 10,
      border: `1px solid ${accent ? 'rgba(229,199,107,0.3)' : 'rgba(255,255,255,0.07)'}`,
      background: accent ? 'linear-gradient(180deg, rgba(229,199,107,0.07), rgba(229,199,107,0.02))' : 'var(--bg-card, #0C0E18)',
      display: 'flex', flexDirection: 'column', gap: 3, position: 'relative', overflow: 'hidden',
      boxShadow: accent ? '0 0 20px rgba(229,199,107,0.15), 0 0 40px rgba(229,199,107,0.05)' : 'none',
    }}>
      <div style={{ fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary, #9A927E)' }}>{label}</div>
      <div style={{ fontFamily: 'monospace', fontSize: 22, fontWeight: 500, color: accent ? 'var(--gold-bright, #FFD97A)' : color, lineHeight: 1, letterSpacing: '-0.02em', textShadow: accent ? '0 0 12px rgba(229,199,107,0.3)' : 'none' }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--text-muted, #55513F)' }}>{sub}</div>}
    </div>
  )
}

// ── Spark (sparkline) ────────────────────────────────────────────────────────
export function Spark({ data = [], color = 'var(--teal, #20D6C7)', h = 30, w = 120 }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 4) + 2}`).join(' ')
  const colorId = color.replace(/[^a-z0-9]/gi, '')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`sg${colorId}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity=".3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${h} ${pts} ${w},${h}`} fill={`url(#sg${colorId})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 3px ${color})` }} />
    </svg>
  )
}

// ── DataRow ───────────────────────────────────────────────────────────────────
export function DataRow({ label, value, color = 'var(--text-primary, #F0E9D2)' }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-secondary, #9A927E)' }}>{label}</span>
      <span style={{ fontFamily: 'monospace', fontSize: 12, color, fontWeight: 500 }}>{value}</span>
    </div>
  )
}

// ── AgentPill ─────────────────────────────────────────────────────────────────
export function AgentPill({ agent, onClick }) {
  const hc = agent.status === 'running' ? 'var(--teal, #20D6C7)' : agent.status === 'busy' ? 'var(--gold, #E5C76B)' : 'rgba(255,255,255,0.3)'
  return (
    <div onClick={onClick} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(229,199,107,0.08)', background: 'var(--bg-elevated, #12141F)', cursor: onClick ? 'pointer' : 'default', transition: 'border-color .15s, background .15s' }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(212,175,55,0.25)'; e.currentTarget.style.background = 'rgba(229,199,107,0.06)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(229,199,107,0.08)'; e.currentTarget.style.background = 'var(--bg-elevated, #12141F)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusDot status={agent.status} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary, #F0E9D2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{agent.name}</div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary, #9A927E)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1 }}>{agent.task || agent.description || 'Standing by'}</div>
        </div>
        <span style={{ fontFamily: 'monospace', fontSize: 11, color: hc, flexShrink: 0 }}>{agent.health ?? 80}%</span>
      </div>
      <MiniBar value={agent.health ?? 80} color={hc} style={{ marginTop: 6 }} />
    </div>
  )
}

// ── TabBtn ────────────────────────────────────────────────────────────────────
export function TabBtn({ label, active, onClick, gold = true }) {
  return (
    <button onClick={onClick} style={{
      padding: '6px 13px', borderRadius: 7, cursor: 'pointer',
      fontFamily: 'monospace', fontSize: 10, fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase',
      border: active && gold ? '1px solid rgba(229,199,107,0.5)' : '1px solid transparent',
      background: active ? (gold ? 'linear-gradient(135deg, rgba(229,199,107,0.15), rgba(205,127,50,0.08))' : 'rgba(255,255,255,0.06)') : 'transparent',
      color: active ? 'var(--gold-bright, #FFD97A)' : 'rgba(255,255,255,0.35)',
      transition: 'all .15s',
    }}>
      {label}
    </button>
  )
}

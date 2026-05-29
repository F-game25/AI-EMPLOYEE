import './KPITile.css'
import HexFrame from './HexFrame'
import Sparkline from './Sparkline'

/**
 * <KPITile>
 *   Compact metric tile with icon, label, value, optional delta and sparkline.
 *   The workhorse component for the KPI strip on every page.
 *
 *   Props:
 *     label     string       — small-caps label
 *     value     ReactNode    — main metric (string or formatted number)
 *     sub       string       — small caption under value
 *     icon      ReactNode    — icon glyph (rendered inside HexFrame)
 *     iconTone  hex tone     — see HexFrame: gold|cool|success|warn|alert|purple
 *     delta     number|null  — % change (e.g. 12.5 -> +12.5%, -3.1 -> -3.1%)
 *     deltaText string       — override delta display text
 *     trend     number[]     — sparkline data (12-30 points recommended)
 *     trendColor string      — sparkline stroke (default uses iconTone)
 *     accent    bool         — gold gradient + glow (use for primary KPI)
 *     hover     bool         — interactive lift on hover
 *     size      'sm'|'md'|'lg'
 *     onClick   fn
 *     className, style
 */
export default function KPITile({
  label,
  value,
  sub,
  icon,
  iconTone = 'gold',
  delta,
  deltaText,
  trend,
  trendColor,
  accent = false,
  hover = false,
  size = 'md',
  onClick,
  className = '',
  style,
}) {
  const cls = [
    'nx-kpi',
    size !== 'md' && `nx-kpi--${size}`,
    accent && 'nx-kpi--accent',
    hover && 'nx-kpi--hover',
    className,
  ].filter(Boolean).join(' ')

  const dir = delta == null ? null : delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'
  const deltaCls = dir ? `nx-kpi__delta nx-kpi__delta--${dir}` : 'nx-kpi__delta'
  const deltaArrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '•'
  const deltaLabel = deltaText ?? (delta == null ? null : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`)

  // Default sparkline colour: derive from iconTone
  const SPARK_TONES = {
    gold:    '#e5c76b',
    cool:    '#60a5fa',
    success: '#22c55e',
    warn:    '#f59e0b',
    alert:   '#ef4444',
    purple:  '#a855f7',
  }
  const sparkStroke = trendColor || SPARK_TONES[iconTone] || '#e5c76b'

  return (
    <div
      className={cls}
      style={style}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
    >
      <div className="nx-kpi__head">
        {icon && <HexFrame size="sm" tone={iconTone} glow={accent}>{icon}</HexFrame>}
        <span className="nx-kpi__label" title={label}>{label}</span>
        {deltaLabel && (
          <span className={deltaCls}>
            <span className="nx-kpi__delta-arrow">{deltaArrow}</span>
            <span>{deltaLabel}</span>
          </span>
        )}
      </div>

      <div className="nx-kpi__value" title={typeof value === 'string' ? value : undefined}>
        {value}
      </div>

      {sub && <div className="nx-kpi__sub">{sub}</div>}

      {trend && trend.length >= 2 && (
        <div className="nx-kpi__spark">
          <Sparkline data={trend} color={sparkStroke} thickness={1.4} height={size === 'sm' ? 16 : size === 'lg' ? 32 : 24} width={300} />
        </div>
      )}
    </div>
  )
}

import './StatusPill.css'

/**
 * <StatusPill>
 *   Compact status indicator: chamfered pill with dot + label.
 *   Use in topbars, panel headers, table cells.
 *
 *   Props:
 *     label    string                                  — pill text
 *     tone     'gold'|'cool'|'success'|'warn'|'alert'|'idle'|'purple'
 *     size     'sm'|'md'                               — default 'md'
 *     dot      bool                                    — show pulsing dot (default true)
 *     pulse    bool                                    — animate dot (default true when dot=true)
 *     icon     ReactNode                               — optional leading glyph (replaces dot)
 *     value    ReactNode                               — optional trailing mono value
 *     onClick  fn
 *     className, style
 */
export default function StatusPill({
  label,
  tone = 'cool',
  size = 'md',
  dot = true,
  pulse,
  icon,
  value,
  onClick,
  className = '',
  style,
}) {
  const animate = pulse ?? dot
  const cls = [
    'nx-pill',
    `nx-pill--${tone}`,
    size === 'sm' && 'nx-pill--sm',
    onClick && 'nx-pill--clickable',
    className,
  ].filter(Boolean).join(' ')

  return (
    <span
      className={cls}
      style={style}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
    >
      {icon ? (
        <span className="nx-pill__icon">{icon}</span>
      ) : dot ? (
        <span className={`nx-pill__dot ${animate ? 'nx-pill__dot--pulse' : ''}`} />
      ) : null}
      {label && <span className="nx-pill__label">{label}</span>}
      {value != null && <span className="nx-pill__value">{value}</span>}
    </span>
  )
}

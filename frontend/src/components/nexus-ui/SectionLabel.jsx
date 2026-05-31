import './SectionLabel.css'

/**
 * <SectionLabel>
 *   Small-caps gold label. Use for sub-section titles inside panels,
 *   data-row groupings, or stand-alone area labels.
 *
 *   Props:
 *     children   ReactNode    — label text
 *     icon       ReactNode    — optional 14px icon (gold)
 *     tone       'gold'|'muted'|'dim'   — default 'muted' (use 'gold' to emphasise)
 *     size       'sm'|'md'|'lg'         — default 'md'
 *     rule       bool         — append a horizontal rule that stretches to the right
 *     badge      ReactNode    — optional badge to the right (e.g. <LiveBadge>)
 *     className, style
 */
export function SectionLabel({
  children,
  icon,
  tone = 'muted',
  size = 'md',
  rule = false,
  badge,
  className = '',
  style,
  ...rest
}) {
  const cls = [
    'nx-section-label',
    tone === 'gold' && 'nx-section-label--gold',
    tone === 'dim' && 'nx-section-label--dim',
    size === 'lg' && 'nx-section-label--lg',
    size === 'sm' && 'nx-section-label--sm',
    className,
  ].filter(Boolean).join(' ')

  return (
    <div
      className={cls}
      style={{ width: rule || badge ? '100%' : undefined, ...style }}
      {...rest}
    >
      {icon && <span className="nx-section-label__icon">{icon}</span>}
      <span>{children}</span>
      {rule && <span className="nx-section-label__rule" aria-hidden="true" />}
      {badge}
    </div>
  )
}

/**
 * <LiveBadge>
 *   Pulsing dot + label. Variants: live (default green), idle, warn, alert.
 *
 *   Props:
 *     variant   'live'|'idle'|'warn'|'alert'   — default 'live'
 *     label     string                          — default 'LIVE'
 */
export function LiveBadge({ variant = 'live', label, className = '', ...rest }) {
  const cls = [
    'nx-live-badge',
    variant !== 'live' && `nx-live-badge--${variant}`,
    className,
  ].filter(Boolean).join(' ')

  const defaultLabel = {
    live: 'LIVE',
    idle: 'IDLE',
    warn: 'WARN',
    alert: 'ALERT',
  }[variant] || 'LIVE'

  return <span className={cls} {...rest}>{label || defaultLabel}</span>
}

export default SectionLabel

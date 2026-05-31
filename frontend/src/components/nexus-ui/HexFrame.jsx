import './HexFrame.css'

/**
 * <HexFrame>
 *   Hexagonal/chamfered border wrapper. Pure-CSS clip-path — no SVG, no JS.
 *   Used for KPI tile icons, agent avatars, status indicators.
 *
 *   Props:
 *     children  ReactNode               — icon / initial / number
 *     size      'xs'|'sm'|'md'|'lg'|'xl'  — default 'md'
 *     tone      'gold'|'cool'|'success'|'warn'|'alert'|'purple'   — default 'gold'
 *     glow      bool                    — add drop-shadow glow
 *     pulse     bool                    — slow pulse animation
 *     ring      bool                    — wrap with subtle orbital ring
 *     onClick   fn                      — makes it interactive (button-like)
 *     className, style, title (a11y)
 */
export default function HexFrame({
  children,
  size = 'md',
  tone = 'gold',
  glow = false,
  pulse = false,
  ring = false,
  onClick,
  className = '',
  style,
  title,
  ...rest
}) {
  const cls = [
    'nx-hex',
    size !== 'md' && `nx-hex--${size}`,
    tone !== 'gold' && `nx-hex--${tone}`,
    glow && 'nx-hex--glow',
    pulse && 'nx-hex--pulse',
    onClick && 'nx-hex--button',
    className,
  ].filter(Boolean).join(' ')

  const inner = (
    <span
      className={cls}
      style={style}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      title={title}
      {...rest}
    >
      <span className="nx-hex__content">{children}</span>
    </span>
  )

  if (ring) {
    return <span className="nx-hex-ring">{inner}</span>
  }
  return inner
}

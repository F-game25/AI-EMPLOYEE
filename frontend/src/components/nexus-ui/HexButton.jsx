import './HexButton.css'

/**
 * <HexButton>
 *   Chamfered action button with optional icon. The default action surface
 *   in Nexus OS — use for primary CTAs, panel actions, command-bar triggers.
 *
 *   Props:
 *     children   ReactNode  — label text
 *     icon       ReactNode  — leading glyph (optional)
 *     trailing   ReactNode  — trailing glyph or kbd hint
 *     variant    'primary'|'ghost'|'outline'|'danger'  — default 'ghost'
 *     size       'sm'|'md'|'lg'                        — default 'md'
 *     tone       'gold'|'cool'|'alert'                 — accent override
 *     loading    bool       — show spinner, disable
 *     disabled   bool
 *     full       bool       — width: 100%
 *     onClick    fn
 *     type       'button'|'submit'                     — default 'button'
 *     className, style
 */
export default function HexButton({
  children,
  icon,
  trailing,
  variant = 'ghost',
  size = 'md',
  tone = 'gold',
  loading = false,
  disabled = false,
  full = false,
  onClick,
  type = 'button',
  className = '',
  style,
}) {
  const cls = [
    'nx-hbtn',
    `nx-hbtn--${variant}`,
    `nx-hbtn--${size}`,
    `nx-hbtn--tone-${tone}`,
    full && 'nx-hbtn--full',
    loading && 'nx-hbtn--loading',
    disabled && 'nx-hbtn--disabled',
    className,
  ].filter(Boolean).join(' ')

  return (
    <button
      type={type}
      className={cls}
      style={style}
      onClick={onClick}
      disabled={disabled || loading}
    >
      <span className="nx-hbtn__inner">
        {loading ? (
          <span className="nx-hbtn__spin" aria-hidden="true" />
        ) : icon ? (
          <span className="nx-hbtn__icon">{icon}</span>
        ) : null}
        {children && <span className="nx-hbtn__label">{children}</span>}
        {trailing && <span className="nx-hbtn__trailing">{trailing}</span>}
      </span>
    </button>
  )
}

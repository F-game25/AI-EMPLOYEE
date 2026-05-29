import './NxButton.css'

/**
 * <NxButton> — general-purpose button for Nexus UI
 *
 * Props:
 *   variant   'primary'|'ghost'|'danger'|'warn'   default 'ghost'
 *   size      'sm'|'md'|'lg'                       default 'md'
 *   icon      ReactNode  leading icon
 *   iconRight ReactNode  trailing icon
 *   loading   bool       show spinner, disable interaction
 *   disabled  bool
 *   onClick   fn
 *   type      'button'|'submit'                    default 'button'
 *   title     string     used as aria-label in icon-only mode
 *   className string
 *   children  ReactNode
 */
export default function NxButton({
  variant = 'ghost',
  size = 'md',
  icon,
  iconRight,
  loading = false,
  disabled = false,
  onClick,
  type = 'button',
  title,
  className = '',
  children,
  ...rest
}) {
  const iconOnly = !children && (icon || iconRight)
  const cls = [
    'nx-btn',
    `nx-btn--${variant}`,
    `nx-btn--${size}`,
    iconOnly && 'nx-btn--icon-only',
    loading && 'nx-btn--loading',
    disabled && 'nx-btn--disabled',
    className,
  ].filter(Boolean).join(' ')

  return (
    <button
      type={type}
      className={cls}
      onClick={onClick}
      disabled={disabled || loading}
      aria-label={iconOnly ? (title || undefined) : undefined}
      title={title}
      {...rest}
    >
      {loading
        ? <span className="nx-btn__spinner" aria-hidden="true" />
        : icon && <span className="nx-btn__icon" aria-hidden="true">{icon}</span>
      }
      {children && <span className="nx-btn__label">{children}</span>}
      {!loading && iconRight && <span className="nx-btn__icon-right" aria-hidden="true">{iconRight}</span>}
    </button>
  )
}

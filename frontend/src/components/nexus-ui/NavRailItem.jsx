import './NavRailItem.css'
import HexFrame from './HexFrame'

/**
 * <NavRailItem>
 *   Sidebar nav row: hex icon + label + sublabel + active spine.
 *   Use inside a Sidebar/NavRail component.
 *
 *   Props:
 *     icon       ReactNode  — glyph rendered inside HexFrame
 *     label      string     — primary label (small-caps)
 *     sub        string     — optional caption below
 *     active     bool       — current route
 *     badge      ReactNode  — small trailing pill (count, "NEW", etc)
 *     tone       hex tone   — see HexFrame
 *     compact    bool       — collapsed rail (icon only, label hidden)
 *     onClick    fn
 *     href       string     — optional link
 *     className, style
 */
export default function NavRailItem({
  icon,
  label,
  sub,
  active = false,
  badge,
  tone = 'gold',
  compact = false,
  onClick,
  href,
  className = '',
  style,
}) {
  const cls = [
    'nx-rail',
    active && 'nx-rail--active',
    compact && 'nx-rail--compact',
    className,
  ].filter(Boolean).join(' ')

  const content = (
    <>
      <span className="nx-rail__spine" aria-hidden="true" />
      <HexFrame size="sm" tone={active ? tone : 'gold'} glow={active}>
        {icon}
      </HexFrame>
      {!compact && (
        <span className="nx-rail__text">
          <span className="nx-rail__label">{label}</span>
          {sub && <span className="nx-rail__sub">{sub}</span>}
        </span>
      )}
      {!compact && badge && <span className="nx-rail__badge">{badge}</span>}
    </>
  )

  if (href) {
    return (
      <a className={cls} style={style} href={href} aria-current={active ? 'page' : undefined}>
        {content}
      </a>
    )
  }
  return (
    <button
      type="button"
      className={cls}
      style={style}
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      title={compact ? label : undefined}
    >
      {content}
    </button>
  )
}

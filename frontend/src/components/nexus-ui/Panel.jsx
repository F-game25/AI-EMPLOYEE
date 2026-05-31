import './Panel.css'

/**
 * <Panel>
 *   Chamfered framed panel — the foundational container of the Nexus design system.
 *   Anatomy: corner ticks, top/bottom hairline, optional header (icon + small-caps
 *   gold title + actions), body (scrollable), optional footer.
 *
 *   Props:
 *     title       string       — small-caps gold title text
 *     icon        ReactNode    — optional 16px icon next to title
 *     sub         string       — optional secondary text (mono, dim) after title
 *     actions     ReactNode    — right-side header slot (badges, buttons)
 *     footer      ReactNode    — optional footer content
 *     tone        'gold'|'cool'|'alert'   — visual tone (default 'gold')
 *     size        'compact'|'default'|'airy'
 *     hover       bool         — enable hover lift
 *     corners     bool         — show corner ticks (default true)
 *     flush       bool         — body padding 0 (for full-bleed content)
 *     tight       bool         — body padding reduced
 *     className   string
 *     style       object       — applied to outer
 *     bodyStyle   object
 *     children    ReactNode
 */
export default function Panel({
  title,
  icon,
  sub,
  actions,
  footer,
  tone = 'gold',
  size = 'default',
  hover = false,
  corners = true,
  flush = false,
  tight = false,
  className = '',
  style,
  bodyStyle,
  children,
  ...rest
}) {
  const cls = [
    'nx-panel',
    tone !== 'gold' && `nx-panel--${tone}`,
    size !== 'default' && `nx-panel--${size}`,
    hover && 'nx-panel--hover',
    className,
  ].filter(Boolean).join(' ')

  const bodyCls = [
    'nx-panel__body',
    flush && 'nx-panel__body--flush',
    tight && 'nx-panel__body--tight',
  ].filter(Boolean).join(' ')

  return (
    <div className={cls} style={style} {...rest}>
      {corners && (
        <>
          <span className="nx-panel__corner nx-panel__corner--tl" aria-hidden="true" />
          <span className="nx-panel__corner nx-panel__corner--tr" aria-hidden="true" />
          <span className="nx-panel__corner nx-panel__corner--bl" aria-hidden="true" />
          <span className="nx-panel__corner nx-panel__corner--br" aria-hidden="true" />
        </>
      )}

      {(title || actions) && (
        <header className="nx-panel__header">
          <div className="nx-panel__title-wrap">
            {icon && <span className="nx-panel__title-icon">{icon}</span>}
            {title && <span className="nx-panel__title">{title}</span>}
            {sub && <span className="nx-panel__sub">{sub}</span>}
          </div>
          {actions && <div className="nx-panel__actions">{actions}</div>}
        </header>
      )}

      <div className={bodyCls} style={bodyStyle}>{children}</div>

      {footer && <footer className="nx-panel__footer">{footer}</footer>}
    </div>
  )
}

import { useRef, useEffect, useState } from 'react'
import './Panel.css'

export function useFreshnessColor(lastTick) {
  const [color, setColor] = useState('var(--nx-border)')
  useEffect(() => {
    if (!lastTick) return
    const update = () => {
      const age = Date.now() - lastTick
      if (age < 30000)      setColor('#00FF88')   // green  < 30s
      else if (age < 300000) setColor('#FFD93D')  // amber  < 5min
      else                   setColor('#FF6B6B')  // red    > 5min
    }
    update()
    const id = setInterval(update, 10000)
    return () => clearInterval(id)
  }, [lastTick])
  return color
}

function FreshnessDot({ lastTick }) {
  const color = useFreshnessColor(lastTick)
  return (
    <span
      className="nx-panel__freshness-dot"
      style={{ background: color, boxShadow: `0 0 5px ${color}` }}
      title={lastTick ? `Last update: ${new Date(lastTick).toLocaleTimeString()}` : 'No data yet'}
      aria-hidden="true"
    />
  )
}

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
 *     depth       0|1|2        — parallax depth tier (0=surface, 1=mid, 2=deep)
 *     className   string
 *     style       object       — applied to outer
 *     bodyStyle   object
 *     children    ReactNode
 */

function useParallax(ref, depth = 0) {
  useEffect(() => {
    if (!depth || !ref.current) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const el = ref.current
    const onMove = (e) => {
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      const dx = (e.clientX - cx) / (r.width / 2)
      const dy = (e.clientY - cy) / (r.height / 2)
      const factor = depth * 2  // depth 1=2deg, depth 2=4deg
      el.style.transform = `perspective(800px) rotateX(${-dy * factor}deg) rotateY(${dx * factor}deg)`
    }
    const onLeave = () => { el.style.transform = '' }
    el.addEventListener('mousemove', onMove)
    el.addEventListener('mouseleave', onLeave)
    return () => {
      el.removeEventListener('mousemove', onMove)
      el.removeEventListener('mouseleave', onLeave)
    }
  }, [ref, depth])
}

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
  depth = 0,
  lastTick,
  className = '',
  style,
  bodyStyle,
  children,
  ...rest
}) {
  const panelRef = useRef(null)
  useParallax(panelRef, depth)

  const cls = [
    'nx-panel',
    tone !== 'gold' && `nx-panel--${tone}`,
    size !== 'default' && `nx-panel--${size}`,
    hover && 'nx-panel--hover',
    depth > 0 && 'nx-panel--parallax',
    className,
  ].filter(Boolean).join(' ')

  const bodyCls = [
    'nx-panel__body',
    flush && 'nx-panel__body--flush',
    tight && 'nx-panel__body--tight',
  ].filter(Boolean).join(' ')

  return (
    <div
      ref={panelRef}
      className={cls}
      data-depth={depth}
      style={style}
      {...rest}
    >
      {corners && (
        <>
          <span className="nx-panel__corner nx-panel__corner--tl" aria-hidden="true" />
          <span className="nx-panel__corner nx-panel__corner--tr" aria-hidden="true" />
          <span className="nx-panel__corner nx-panel__corner--bl" aria-hidden="true" />
          <span className="nx-panel__corner nx-panel__corner--br" aria-hidden="true" />
        </>
      )}

      {(title || actions || lastTick !== undefined) && (
        <header className="nx-panel__header">
          <div className="nx-panel__title-wrap">
            {icon && <span className="nx-panel__title-icon">{icon}</span>}
            {title && <span className="nx-panel__title">{title}</span>}
            {sub && <span className="nx-panel__sub">{sub}</span>}
          </div>
          <div className="nx-panel__actions">
            {lastTick !== undefined && <FreshnessDot lastTick={lastTick} />}
            {actions}
          </div>
        </header>
      )}

      <div className={bodyCls} style={bodyStyle}>{children}</div>

      {footer && <footer className="nx-panel__footer">{footer}</footer>}
    </div>
  )
}

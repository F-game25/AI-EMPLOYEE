import { useRef, useEffect, useState, useCallback } from 'react'
import './PanelConnections.css'

/**
 * <PanelConnections>
 *   Fixed-position SVG overlay that draws animated data-flow lines between
 *   panels identified by their [data-panel-id] attribute.
 *
 *   Props:
 *     connections  Array<{ from, to, color, active }>
 *       from/to    — data-panel-id attribute values
 *       color      — stroke color (hex / rgba string)
 *       active     — true = bright + fast animation; false = dim + slow
 */
export default function PanelConnections({ connections = [] }) {
  const [lines, setLines] = useState([])
  const rafRef = useRef(null)
  const timerRef = useRef(null)

  const compute = useCallback(() => {
    const next = connections.map(({ from, to, color = '#e5c76b', active = true }) => {
      const elFrom = document.querySelector(`[data-panel-id="${from}"]`)
      const elTo   = document.querySelector(`[data-panel-id="${to}"]`)
      if (!elFrom || !elTo) return null
      const rf = elFrom.getBoundingClientRect()
      const rt = elTo.getBoundingClientRect()
      return {
        id: `${from}-${to}`,
        x1: rf.left + rf.width / 2,
        y1: rf.top  + rf.height / 2,
        x2: rt.left + rt.width / 2,
        y2: rt.top  + rt.height / 2,
        color,
        active,
      }
    }).filter(Boolean)
    setLines(next)
  }, [connections])

  useEffect(() => {
    // Initial compute after layout settles
    rafRef.current = requestAnimationFrame(compute)

    const onResize = () => {
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(compute, 150)
    }
    window.addEventListener('resize', onResize)
    return () => {
      cancelAnimationFrame(rafRef.current)
      clearTimeout(timerRef.current)
      window.removeEventListener('resize', onResize)
    }
  }, [compute])

  if (!lines.length) return null

  return (
    <svg className="nx-connections" aria-hidden="true">
      <defs>
        {lines.map(l => (
          <filter key={`glow-${l.id}`} id={`glow-${l.id}`} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation={l.active ? '2' : '1'} result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        ))}
      </defs>
      {lines.map(l => (
        <line
          key={l.id}
          className={`nx-conn-line${l.active ? ' nx-conn-line--active' : ''}`}
          x1={l.x1} y1={l.y1}
          x2={l.x2} y2={l.y2}
          stroke={l.color}
          strokeWidth={l.active ? 1.5 : 1}
          strokeOpacity={l.active ? 0.7 : 0.25}
          filter={`url(#glow-${l.id})`}
        />
      ))}
    </svg>
  )
}

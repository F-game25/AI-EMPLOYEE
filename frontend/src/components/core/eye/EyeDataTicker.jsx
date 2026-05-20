import { useId, useMemo } from 'react'
import './EyeDataTicker.css'

// Circular path for the ticker — radius 82, centered at 0,0.
// Drawn as two arc segments to make a full closed circle.
const R = 82
const TICKER_PATH = `M ${-R} 0 A ${R} ${R} 0 1 1 ${R} 0 A ${R} ${R} 0 1 1 ${-R} 0`

/**
 * EyeDataTicker — scrolling micro-text along the eye's outer ring.
 *
 * @param {string} text   Ticker payload (e.g. "REASONING: ... · MODEL: ... · TPS: ... · QUEUE: ...")
 * @param {number} speed  0..1, modulates animation period. Higher = faster scroll.
 */
export default function EyeDataTicker({ text = '', speed = 0.3 }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const pathId = `edt-path-${uid}`

  // Period inversely proportional to speed: dur = 20 / (0.3 + speed * 1.7)
  // speed=0 → 66.67s, speed=0.3 → 24.69s (≈ default 20), speed=1 → 10s
  const clampedSpeed = Math.max(0, Math.min(1, Number(speed) || 0))
  const dur = (20 / (0.3 + clampedSpeed * 1.7)).toFixed(2)

  // Repeat text 3x to ensure circumference is filled regardless of length.
  const safeText = (text || '').trim() || 'AI-EMPLOYEE · STANDBY'
  const repeated = useMemo(() => {
    const sep = '   ◆   '
    return `${safeText}${sep}${safeText}${sep}${safeText}${sep}`
  }, [safeText])

  return (
    <g className="edt-ticker" aria-hidden="true">
      <defs>
        <path id={pathId} d={TICKER_PATH} fill="none" />
      </defs>
      <text className="edt-text">
        <textPath
          href={`#${pathId}`}
          xlinkHref={`#${pathId}`}
          startOffset="0%"
          textLength={undefined}
        >
          {repeated}
          <animate
            attributeName="startOffset"
            from="0%"
            to="100%"
            dur={`${dur}s`}
            repeatCount="indefinite"
          />
        </textPath>
      </text>
    </g>
  )
}

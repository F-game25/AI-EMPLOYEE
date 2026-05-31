import './KPIDelta.css'

/**
 * KPIDelta — number + up/down arrow + delta %.
 *
 * Props:
 *   value     number|string   current value
 *   prev      number|string   previous value (for delta calc) — OR pass `delta` directly
 *   delta     number          pre-calculated delta % (overrides prev)
 *   format    function        value formatter, default String
 *   label     string
 *   className string
 */
export default function KPIDelta({ value, prev, delta: deltaProp, format = v => v, label, className = '' }) {
  const delta = deltaProp !== undefined
    ? deltaProp
    : (prev !== undefined && prev !== 0 ? ((Number(value) - Number(prev)) / Math.abs(Number(prev))) * 100 : null)

  const sign = delta === null ? '' : delta > 0 ? '↑' : delta < 0 ? '↓' : '—'
  const cls  = delta === null ? '' : delta > 0 ? 'pos' : delta < 0 ? 'neg' : 'flat'

  return (
    <div className={`nx-kpi ${className}`}>
      {label && <span className="nx-kpi__label">{label}</span>}
      <span className="nx-kpi__value">{format(value)}</span>
      {delta !== null && (
        <span className={`nx-kpi__delta nx-kpi__delta--${cls}`}>
          {sign} {Math.abs(delta).toFixed(1)}%
        </span>
      )}
    </div>
  )
}

import './LoadingSkeleton.css'

/**
 * LoadingSkeleton — pulse-animated placeholder bars.
 *
 * Props:
 *   variant   'bar'|'card'|'row'|'grid'|'card-grid'   default 'bar'
 *   rows      number   for bar/row/card-grid count (default 3)
 *   cols      number   for grid/card-grid columns (default 3)
 *   height    string   for single bar (default '14px')
 *   className string
 */
export default function LoadingSkeleton({ variant = 'bar', rows = 3, cols = 3, height = '14px', className = '' }) {
  if (variant === 'card-grid') {
    return (
      <div className={`nx-skel nx-skel--card-grid ${className}`} style={{ '--cols': cols }}>
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="nx-skel__card-tile">
            <div className="nx-skel__card-tile-avatar" />
            <div className="nx-skel__bar" style={{ width: '60%', marginBottom: 6 }} />
            <div className="nx-skel__bar" style={{ width: '40%', marginBottom: 8 }} />
            <div className="nx-skel__card-tile-bar" />
          </div>
        ))}
      </div>
    )
  }
  if (variant === 'grid') {
    return (
      <div className={`nx-skel nx-skel--grid ${className}`} style={{ '--cols': cols }}>
        {Array.from({ length: rows * cols }, (_, i) => <div key={i} className="nx-skel__cell" />)}
      </div>
    )
  }
  if (variant === 'card') {
    return (
      <div className={`nx-skel nx-skel--card ${className}`}>
        <div className="nx-skel__card-header" />
        <div className="nx-skel__bar" style={{ width: '60%', marginBottom: 8 }} />
        <div className="nx-skel__bar" style={{ width: '80%', marginBottom: 8 }} />
        <div className="nx-skel__bar" style={{ width: '45%' }} />
      </div>
    )
  }
  if (variant === 'row') {
    return (
      <div className={`nx-skel nx-skel--rows ${className}`}>
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="nx-skel__row">
            <div className="nx-skel__dot" />
            <div className="nx-skel__bar" style={{ width: `${55 + (i * 13) % 35}%` }} />
          </div>
        ))}
      </div>
    )
  }
  // default: bar
  return (
    <div className={`nx-skel ${className}`}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="nx-skel__bar" style={{ width: `${60 + (i * 17) % 35}%`, height, marginBottom: 8 }} />
      ))}
    </div>
  )
}

import './ErrorState.css'

/**
 * ErrorState — triangle icon + message + retry button.
 *
 * Props:
 *   message   string
 *   onRetry   function
 *   className string
 */
export default function ErrorState({ message = 'Failed to load data.', onRetry, className = '' }) {
  return (
    <div className={`nx-err ${className}`}>
      <span className="nx-err__icon">⚠</span>
      <p className="nx-err__msg">{message}</p>
      {onRetry && (
        <button className="nx-err__retry" onClick={onRetry}>Retry</button>
      )}
    </div>
  )
}

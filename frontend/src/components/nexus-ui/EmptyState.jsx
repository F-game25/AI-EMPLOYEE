import './EmptyState.css'

/**
 * EmptyState — icon + headline + optional sub + optional CTA.
 *
 * Props:
 *   icon      string|ReactNode   emoji or element, default '◈'
 *   title     string             required
 *   sub       string
 *   action    string             CTA label
 *   onAction  function
 *   className string
 */
export default function EmptyState({ icon = '◈', title, sub, action, onAction, className = '' }) {
  return (
    <div className={`nx-empty ${className}`}>
      <span className="nx-empty__icon">{icon}</span>
      <p className="nx-empty__title">{title}</p>
      {sub && <p className="nx-empty__sub">{sub}</p>}
      {action && onAction && (
        <button className="nx-empty__cta" onClick={onAction}>{action}</button>
      )}
    </div>
  )
}

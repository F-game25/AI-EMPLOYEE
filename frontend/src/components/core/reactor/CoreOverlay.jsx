/* ─────────────────────────────────────────────────────────────────────────
 * CoreOverlay.jsx
 * ---------------
 * DOM overlay sitting on top of the reactor stack. Shows the COGNITIVE CORE
 * title, subtitle, current state badge (color-coded) and optional focus
 * keyword caption. Positioning + styling lives in CognitiveCoreReactor.css.
 * ──────────────────────────────────────────────────────────────────────── */

export default function CoreOverlay({ state = 'IDLE', focusKeyword = '' }) {
  const stateLower = String(state || 'idle').toLowerCase()

  return (
    <div className="co-overlay" role="status" aria-live="polite">
      <div className="co-title">COGNITIVE CORE</div>
      <div className="co-sub">AUTONOMOUS AI INTELLIGENCE</div>
      <div className={`co-state co-state--${stateLower}`}>
        <span className="co-state-dot" aria-hidden="true" />
        {state}
      </div>
      {focusKeyword && (
        <div className="co-focus">FOCUS · {String(focusKeyword).toUpperCase()}</div>
      )}
    </div>
  )
}

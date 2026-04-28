import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// ── Global error telemetry ────────────────────────────────────────────────────
// Captures unhandled JS errors and promise rejections and routes them into the
// heartbeat log so operators can see them in the HeartbeatPanel without opening
// DevTools. Also sends to /api/error-report for backend persistence.

function reportError(msg, stack) {
  console.error('[UI ERROR]', msg, stack)
  try {
    // Lazy-import store to avoid circular init issues
    import('./store/appStore.js').then(({ useAppStore }) => {
      useAppStore.getState().addHeartbeatLog({
        text: `[UI ERROR] ${msg}`,
        level: 'error',
        ts: Date.now(),
      })
    })
  } catch { /* store not ready */ }
  // Best-effort POST to backend — don't await, don't throw
  try {
    fetch('/api/error-report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg, stack, ts: Date.now(), source: 'frontend' }),
    }).catch(() => {})
  } catch { /* ignore */ }
}

window.onerror = (msg, _url, _line, _col, error) => {
  reportError(String(msg), error?.stack)
}

window.addEventListener('unhandledrejection', (evt) => {
  const reason = evt.reason
  const msg = reason instanceof Error ? reason.message : String(reason)
  reportError(`Unhandled rejection: ${msg}`, reason?.stack)
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

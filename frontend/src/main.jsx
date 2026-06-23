import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { reportBootPhase } from './bootPhase'

// Same-origin API calls are protected by the local JWT tenant middleware.
// Many dashboard widgets use raw fetch(), so attach the local operator token
// centrally instead of relying on every component to remember the header.
try {
  const nativeFetch = window.fetch.bind(window)
  window.fetch = (input, init = {}) => {
    const rawUrl = typeof input === 'string' ? input : input?.url
    const url = rawUrl ? new URL(rawUrl, window.location.origin) : null
    const sameOriginApi = url?.origin === window.location.origin && url.pathname.startsWith('/api/')
    const token = sameOriginApi ? sessionStorage.getItem('ai_jwt') : null
    if (!token) return nativeFetch(input, init)

    const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined) || {})
    if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
    return nativeFetch(input, { ...init, headers })
  }
} catch { /* fetch may be unavailable in tests */ }

// ── Global error telemetry ────────────────────────────────────────────────────
// Captures unhandled JS errors and promise rejections and routes them into the
// heartbeat log so operators can see them in the HeartbeatPanel without opening
// DevTools. Also sends to /api/error-report for backend persistence.

function reportError(msg, stack) {
  console.error('[UI ERROR]', msg, stack)
  try {
    window.ai?.notifyUiFailed?.({ message: msg, stack, source: 'frontend' })
  } catch { /* not in Electron */ }
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

createRoot(document.getElementById('root')).render(<App />)

// Warm-start the Dashboard chunk so it's cached by the time BootSequence completes.
// Fire-and-forget — runs in parallel with first paint, doesn't block.
import('./components/Dashboard')

// v4 diagnostic: if we're loaded inside Electron (`?electron=1`) but
// window.ai is undefined, the preload didn't inject. Log loudly so the
// launcher's webContents 'console-message' handler captures it in
// ~/.ai-employee/logs/launcher.log.
try {
  const params = new URLSearchParams(window.location.search)
  if (params.has('electron') && typeof window.ai === 'undefined') {
    console.error('[LAUNCHER-HANDSHAKE] window.ai is undefined inside Electron — preload script did not inject. ' +
                  'Check launcher/preload.js path, contextIsolation, and CSP headers.')
  }
} catch { /* sandboxed contexts may not allow URLSearchParams */ }

// Earliest possible "I'm alive" signal to the shell (Electron launcher OR Tauri).
// Fires synchronously after createRoot — before any lazy chunk resolves — so the shell
// can advance from "html-loaded" to "react-rendered" and show the dashboard without
// waiting for the full <Dashboard> tree (gated behind <Suspense>). reportBootPhase routes
// it via the Electron bridge AND POST /api/boot/phase, so it also works under Tauri.
try {
  reportBootPhase('react-rendered')
} catch { /* best-effort */ }

import { useCallback, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useAppStore } from './store/appStore'
import BootSequence from './components/BootSequence'
import ErrorScreen from './components/ErrorScreen'
import ErrorBoundary from './components/ErrorBoundary'
import { useWebSocket, bootstrapWsStore } from './hooks/useWebSocket'
import Toaster from './components/nexus-ui/Toaster'

const Dashboard = lazy(() => import('./components/Dashboard'))
import ContextCheckModal from './components/dashboard/ContextCheckModal'
let localAuthPromise = null
const READINESS_POLL_MS = 1500
const READINESS_DEGRADED_AFTER_MS = 12000

function notifyBootPhase(phase, message, extra = {}) {
  const payload = { phase, message, ...extra, ts: Date.now() }
  try {
    window.dispatchEvent(new CustomEvent('nx:boot-phase', { detail: payload }))
  } catch {
    // Browser event dispatch is best-effort during early boot.
  }
  try {
    window.ai?.notifyUiBootPhase?.(payload)
  } catch {
    // Electron IPC is unavailable in normal browser mode.
  }
}

function ensureLocalOperatorToken() {
  const existing = sessionStorage.getItem('ai_jwt')
  if (existing) return Promise.resolve(existing)
  if (localAuthPromise) return localAuthPromise

  notifyBootPhase('auth', 'Requesting local operator token')
  localAuthPromise = fetch('/api/auth/auto-token', { signal: AbortSignal.timeout(5000) })
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      if (d?.token) {
        sessionStorage.setItem('ai_jwt', d.token)
        notifyBootPhase('auth', 'Operator token acquired', { status: 'ok' })
        window.dispatchEvent(new CustomEvent('nx:auth-ready'))
        return d.token
      }
      notifyBootPhase('auth', 'Operator token unavailable', { status: 'degraded' })
      return null
    })
    .catch(err => {
      notifyBootPhase('auth', err?.message || 'Auth token request failed', { status: 'degraded' })
      return null
    })
    .finally(() => {
      localAuthPromise = null
    })
  return localAuthPromise
}

function AppLoadingFallback() {
  useEffect(() => {
    notifyBootPhase('dashboard-lazy-load', 'Loading dashboard bundle')
  }, [])

  return (
    <div style={{
      minHeight: '100vh',
      display: 'grid',
      placeItems: 'center',
      background: '#050608',
      color: '#e5c76b',
      fontFamily: 'var(--nx-font-mono, monospace)',
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 86,
          height: 86,
          margin: '0 auto 18px',
          borderRadius: '50%',
          border: '1px solid rgba(229,199,107,0.45)',
          boxShadow: '0 0 34px rgba(255,184,0,0.2), inset 0 0 24px rgba(229,199,107,0.08)',
          background: 'radial-gradient(circle, #050608 0 22%, #ffb84d 24% 34%, rgba(255,184,0,0.18) 36% 60%, transparent 62%)',
          animation: 'appFallbackPulse 1.5s ease-in-out infinite',
        }} />
        <div style={{ fontSize: 11, letterSpacing: '0.16em' }}>LOADING COMMAND CENTER</div>
        <style>{'@keyframes appFallbackPulse{0%,100%{transform:scale(.96);opacity:.72}50%{transform:scale(1.04);opacity:1}}'}</style>
      </div>
    </div>
  )
}

function AppContent() {
  const appState = useAppStore(s => s.appState)
  const setAppState = useAppStore(s => s.setAppState)
  const setPythonBackendReady = useAppStore(s => s.setPythonBackendReady)
  const setReadiness = useAppStore(s => s.setReadiness)
  const login = useAppStore(s => s.login)
  useWebSocket()

  useEffect(() => {
    notifyBootPhase('app-init', 'React application initialized')
  }, [])

  // Fetch a session JWT on boot so api.client can attach auth headers
  useEffect(() => {
    ensureLocalOperatorToken().finally(() => {
      // Mark store as bootstrapped so queued WS events can be replayed
      bootstrapWsStore()
      notifyBootPhase('websocket-bootstrap', 'WebSocket store bootstrapped')
    })
  }, [])

  // REST readiness check — transition to dashboard when Node responds, but keep
  // polling AI-core readiness so fragile pages can gate themselves correctly.
  useEffect(() => {
    let cancelled = false
    const started = Date.now()
    const check = () => {
      notifyBootPhase('readiness', 'Checking system readiness')
      fetch('/api/readiness', { signal: AbortSignal.timeout(5000) })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (cancelled) return
          if (d) {
            setReadiness?.(d)
            ensureLocalOperatorToken().finally(() => {
              if (cancelled) return
              const pythonOk = !!d.pythonReady
              setPythonBackendReady(pythonOk)
              const fullyReady = !!(d.nodeReady && d.pythonReady && d.neuralBrainReady && d.graphReady)
              notifyBootPhase(
                'readiness',
                fullyReady ? 'System online' : `System starting: ${d.phase || 'AI core initializing'}`,
                { status: fullyReady ? 'ok' : 'degraded', readiness: d },
              )
              setAppState(fullyReady ? 'dashboard' : 'degraded')
              if (!fullyReady && Date.now() - started < READINESS_DEGRADED_AFTER_MS) {
                setTimeout(check, READINESS_POLL_MS)
              }
            })
            return
          }
          if (!cancelled) setTimeout(check, READINESS_POLL_MS)
        })
        .catch(() => {
          notifyBootPhase('readiness', 'Readiness check delayed; retrying', { status: 'pending' })
          if (!cancelled) setTimeout(check, READINESS_POLL_MS)
        })
    }
    check()
    return () => { cancelled = true }
  }, [setAppState, setPythonBackendReady, setReadiness])

  // Listen for system:ready WS event to update Python backend status
  useEffect(() => {
    function onSystemReady(e) {
      const detail = e.detail || {}
      const { python_ok } = detail
      const wsReadiness = detail.readiness?.readiness || detail.readiness || {}
      setPythonBackendReady(!!python_ok)
      setReadiness?.({
        nodeReady: true,
        pythonReady: !!(wsReadiness.pythonReady ?? python_ok),
        subsystemsReady: !!(wsReadiness.subsystemsReady ?? python_ok),
        neuralBrainReady: !!wsReadiness.neuralBrainReady,
        graphReady: !!wsReadiness.graphReady,
        phase: wsReadiness.phase || (python_ok ? 'AI_CORE_INITIALIZING' : 'INITIALIZING'),
        degraded: wsReadiness.degraded ?? true,
        degradedReasons: wsReadiness.degradedReasons || (python_ok ? ['ai_core_initializing'] : ['python_backend_not_ready']),
      })
      if (!python_ok) setAppState('degraded')
    }
    window.addEventListener('ws:system:ready', onSystemReady)
    return () => window.removeEventListener('ws:system:ready', onSystemReady)
  }, [setAppState, setPythonBackendReady, setReadiness])

  // Fallback: if still in boot/connecting after 8s, force dashboard
  useEffect(() => {
    if (appState === 'dashboard' || appState === 'degraded' || appState === 'error') return
    const t = setTimeout(() => {
      console.warn('[APP] Boot timeout — forcing dashboard')
      notifyBootPhase('dashboard-timeout', 'Boot timeout; opening degraded dashboard', { status: 'degraded' })
      setAppState('degraded')
    }, 8000)
    return () => clearTimeout(t)
  }, [appState, setAppState])

  const handleBootComplete = useCallback(() => {
    notifyBootPhase('handoff', 'Boot animation handoff complete')
    login('operator')
  }, [login])

  const isBootPhase = appState === 'boot' || appState === 'connecting' || appState === 'ready_check'
  const bootSubState = appState === 'ready_check' ? 'initializing' : appState === 'connecting' ? 'connecting' : 'boot'

  return (
    <AnimatePresence mode="sync">
      {isBootPhase && (
        <BootSequence key="boot" onComplete={handleBootComplete} subState={bootSubState} />
      )}
      {(appState === 'dashboard' || appState === 'degraded') && (
        <Suspense fallback={<AppLoadingFallback />}>
          <Dashboard key="dashboard" degraded={appState === 'degraded'} />
        </Suspense>
      )}
      {appState === 'error' && <ErrorScreen key="error" />}
      <ContextCheckModal />
    </AnimatePresence>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary label="Application" severity="fatal">
        <div className="app">
          <AppContent />
          <Toaster />
        </div>
      </ErrorBoundary>
    </BrowserRouter>
  )
}

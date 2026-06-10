import { useCallback, useEffect, useRef, lazy, Suspense } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useAppStore } from './store/appStore'
import BootSequence from './components/BootSequence'
import BootMenu from './components/BootMenu'
import ErrorScreen from './components/ErrorScreen'
import ErrorBoundary from './components/ErrorBoundary'
import { useWebSocket, bootstrapWsStore } from './hooks/useWebSocket'
import Toaster from './components/nexus-ui/Toaster'
import SearchOmnibar from './components/ui/SearchOmnibar'
import LoginPage from './components/LoginPage'
import { PerformanceModeProvider } from './context/PerformanceModeContext'

const Dashboard = lazy(() => import('./components/Dashboard'))
import ContextCheckModal from './components/dashboard/ContextCheckModal'
let localAuthPromise = null
const READINESS_POLL_MS = 1500
const READINESS_DEGRADED_AFTER_MS = 12000
const BOOT_MIN_MS = 2800

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

function getStoredToken() {
  return localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || null
}

function ensureLocalOperatorToken() {
  const existing = getStoredToken()
  if (existing) return Promise.resolve(existing)
  if (localAuthPromise) return localAuthPromise

  notifyBootPhase('auth', 'Requesting local operator token')
  localAuthPromise = fetch('/api/auth/auto-token', { signal: AbortSignal.timeout(5000) })
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      if (d?.token) {
        // Persist in both storages: localStorage survives restarts, sessionStorage
        // is required by useWebSocket.js and the main.jsx fetch interceptor.
        localStorage.setItem('ai_jwt', d.token)
        sessionStorage.setItem('ai_jwt', d.token)
        notifyBootPhase('auth', 'Operator token acquired', { status: 'ok' })
        window.dispatchEvent(new CustomEvent('nx:auth-ready'))
        return d.token
      }
      notifyBootPhase('auth', 'Operator token unavailable — login required', { status: 'degraded' })
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
  const bootStartRef = useRef(Date.now())
  useWebSocket()

  useEffect(() => {
    notifyBootPhase('app-init', 'React application initialized')
  }, [])

  // Fetch a session JWT on boot, then poll readiness with the token.
  // /api/readiness requires auth — we must have a token before the first call.
  // Gated to boot-phase states: while the BootMenu ('menu') is showing, nothing
  // may auto-transition the app — the user (or the menu's own countdown) decides.
  useEffect(() => {
    if (appState !== 'connecting' && appState !== 'boot' && appState !== 'ready_check') return
    let cancelled = false
    const started = Date.now()
    bootStartRef.current = Date.now()

    const check = (token) => {
      notifyBootPhase('readiness', 'Checking system readiness')
      const headers = token ? { Authorization: `Bearer ${token}` } : {}
      fetch('/api/readiness', { signal: AbortSignal.timeout(5000), headers })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (cancelled) return
          if (d) {
            setReadiness?.(d)
            const pythonOk = !!d.pythonReady
            setPythonBackendReady(pythonOk)
            const fullyReady = !!(d.nodeReady && d.pythonReady && d.neuralBrainReady && d.graphReady)
            notifyBootPhase(
              'readiness',
              fullyReady ? 'System online' : `System starting: ${d.phase || 'AI core initializing'}`,
              { status: fullyReady ? 'ok' : 'degraded', readiness: d },
            )
            const elapsed = Date.now() - bootStartRef.current
            const delay = Math.max(0, BOOT_MIN_MS - elapsed)
            setTimeout(() => {
              if (!cancelled) setAppState(fullyReady ? 'dashboard' : 'degraded')
            }, delay)
            if (!fullyReady && Date.now() - started < READINESS_DEGRADED_AFTER_MS) {
              setTimeout(() => check(token), READINESS_POLL_MS)
            }
            return
          }
          if (!cancelled) setTimeout(() => check(token), READINESS_POLL_MS)
        })
        .catch(() => {
          notifyBootPhase('readiness', 'Readiness check delayed; retrying', { status: 'pending' })
          if (!cancelled) setTimeout(() => check(token), READINESS_POLL_MS)
        })
    }

    // Acquire token first, then bootstrap WS store, then start readiness polling
    ensureLocalOperatorToken().then(token => {
      if (cancelled) return
      bootstrapWsStore()
      notifyBootPhase('websocket-bootstrap', 'WebSocket store bootstrapped')
      check(token)
    })

    return () => { cancelled = true }
  }, [appState, setAppState, setPythonBackendReady, setReadiness])

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

  // Handle token expiry from any API call → show login page
  useEffect(() => {
    const onExpired = () => {
      notifyBootPhase('auth', 'Session expired — showing login', { status: 'degraded' })
      setAppState('login')
    }
    window.addEventListener('nx:auth-expired', onExpired)
    return () => window.removeEventListener('nx:auth-expired', onExpired)
  }, [setAppState])

  // Fallback: if still in boot/connecting after 8s, check for token.
  // 'menu' is excluded — the BootMenu waits for the user (its own countdown
  // handles unattended startups).
  useEffect(() => {
    if (appState === 'menu' || appState === 'dashboard' || appState === 'degraded' || appState === 'error' || appState === 'login') return
    const t = setTimeout(() => {
      // If we have no token at all, go to login; otherwise degrade to dashboard
      if (!getStoredToken()) {
        notifyBootPhase('auth', 'No token found — showing login', { status: 'degraded' })
        setAppState('login')
      } else {
        console.warn('[APP] Boot timeout — forcing dashboard')
        notifyBootPhase('dashboard-timeout', 'Boot timeout; opening degraded dashboard', { status: 'degraded' })
        setAppState('degraded')
      }
    }, 8000)
    return () => clearTimeout(t)
  }, [appState, setAppState])

  const handleBootComplete = useCallback(() => {
    notifyBootPhase('handoff', 'Boot animation handoff complete')
    login('operator')
  }, [login])

  const handleLoginSuccess = useCallback((token) => {
    localStorage.setItem('ai_jwt', token)
    sessionStorage.setItem('ai_jwt', token)
    notifyBootPhase('auth', 'Login successful', { status: 'ok' })
    window.dispatchEvent(new CustomEvent('nx:auth-ready'))
    login('operator')
  }, [login])

  const isBootPhase = appState === 'boot' || appState === 'connecting' || appState === 'ready_check'
  const bootSubState = appState === 'ready_check' ? 'initializing' : appState === 'connecting' ? 'connecting' : 'boot'

  // BootMenu → BOOT: enter the boot phase (BootSequence animation → dashboard).
  const handleMenuBoot = useCallback(() => {
    bootStartRef.current = Date.now()
    notifyBootPhase('menu', 'Boot requested from system menu')
    setAppState('connecting')
  }, [setAppState])

  return (
    <>
      {/* Boot/login/error keep their cross-fade. The Dashboard lives OUTSIDE
          AnimatePresence: with a non-motion child (Suspense), an appState
          flicker (e.g. dashboard→connecting→dashboard on a WS bounce) left a
          zombie Dashboard mounted next to the new one — two full app trees,
          double WS hooks/intervals/panels. Outside presence, exactly one
          Dashboard can ever exist. */}
      {appState === 'menu' && <BootMenu onBoot={handleMenuBoot} />}
      <AnimatePresence mode="sync">
        {isBootPhase && (
          <BootSequence key="boot" onComplete={handleBootComplete} subState={bootSubState} />
        )}
        {appState === 'login' && (
          <LoginPage key="login" onSuccess={handleLoginSuccess} />
        )}
        {appState === 'error' && <ErrorScreen key="error" />}
      </AnimatePresence>
      {(appState === 'dashboard' || appState === 'degraded') && (
        <Suspense fallback={<AppLoadingFallback />}>
          <Dashboard degraded={appState === 'degraded'} />
        </Suspense>
      )}
      <ContextCheckModal />
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary label="Application" severity="fatal">
        <PerformanceModeProvider>
          <div className="app">
            <AppContent />
            <Toaster />
            <SearchOmnibar />
          </div>
        </PerformanceModeProvider>
      </ErrorBoundary>
    </BrowserRouter>
  )
}

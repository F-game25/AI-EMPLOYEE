import { useCallback, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useAppStore } from './store/appStore'
import BootSequence from './components/BootSequence'
import ErrorScreen from './components/ErrorScreen'
import ErrorBoundary from './components/ErrorBoundary'
import { useWebSocket, bootstrapWsStore } from './hooks/useWebSocket'

const Dashboard = lazy(() => import('./components/Dashboard'))

function AppContent() {
  const appState = useAppStore(s => s.appState)
  const setAppState = useAppStore(s => s.setAppState)
  const setPythonBackendReady = useAppStore(s => s.setPythonBackendReady)
  const login = useAppStore(s => s.login)
  useWebSocket()

  // Fetch a session JWT on boot so api.client can attach auth headers
  useEffect(() => {
    if (!sessionStorage.getItem('ai_jwt')) {
      fetch('/api/auth/auto-token')
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d?.token) sessionStorage.setItem('ai_jwt', d.token)
        })
        .catch(() => {})
        .finally(() => {
          // Mark store as bootstrapped so queued WS events can be replayed
          bootstrapWsStore()
        })
    } else {
      bootstrapWsStore()
    }
  }, [])

  // Listen for system:ready WS event to transition out of ready_check
  useEffect(() => {
    function onSystemReady(e) {
      const { python_ok } = e.detail || {}
      setPythonBackendReady(!!python_ok)
      setAppState(!!python_ok ? 'dashboard' : 'degraded')
    }
    window.addEventListener('ws:system:ready', onSystemReady)
    return () => window.removeEventListener('ws:system:ready', onSystemReady)
  }, [setAppState, setPythonBackendReady])

  // Fallback: if we're in connecting/ready_check for > 10s, go to dashboard anyway
  useEffect(() => {
    if (appState !== 'connecting' && appState !== 'ready_check') return
    const t = setTimeout(() => {
      setAppState('dashboard')
    }, 10000)
    return () => clearTimeout(t)
  }, [appState, setAppState])

  const handleBootComplete = useCallback(() => {
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
        <Suspense fallback={null}>
          <Dashboard key="dashboard" degraded={appState === 'degraded'} />
        </Suspense>
      )}
      {appState === 'error' && <ErrorScreen key="error" />}
    </AnimatePresence>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary label="Application">
        <div className="app">
          <AppContent />
        </div>
      </ErrorBoundary>
    </BrowserRouter>
  )
}

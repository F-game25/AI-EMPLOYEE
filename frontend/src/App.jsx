import { useCallback } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useAppStore } from './store/appStore'
import BootSequence from './components/BootSequence'
import Dashboard from './components/Dashboard'
import ErrorScreen from './components/ErrorScreen'
import ErrorBoundary from './components/ErrorBoundary'
import { useWebSocket } from './hooks/useWebSocket'

function AppContent() {
  // Use selective selectors to avoid re-rendering on unrelated store changes
  // (e.g. WebSocket heartbeats, agent updates) which would reset boot timers.
  const appState = useAppStore(s => s.appState)
  const login = useAppStore(s => s.login)
  useWebSocket() // initialize WebSocket connection

  // Stable reference so BootSequence's useEffect dependency never changes.
  const handleBootComplete = useCallback(() => {
    // Auto-login and go straight to dashboard — no login screen needed
    login('operator')
  }, [login])

  return (
    <AnimatePresence mode="sync">
      {appState === 'boot' && (
        <BootSequence key="boot" onComplete={handleBootComplete} />
      )}
      {appState === 'dashboard' && <Dashboard key="dashboard" />}
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

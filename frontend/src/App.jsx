import { useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useAppStore } from './store/appStore'
import BootSequence from './components/BootSequence'
import LoginScreen from './components/LoginScreen'
import Dashboard from './components/Dashboard'
import ErrorScreen from './components/ErrorScreen'
import { useWebSocket } from './hooks/useWebSocket'

function AppContent() {
  const { appState, setAppState, setError } = useAppStore()
  useWebSocket() // initialize WebSocket connection

  const handleBootComplete = async () => {
    setAppState('connecting')
    try {
      const res = await fetch('http://localhost:3001/health')
      if (res.ok) {
        setAppState('login')
      } else {
        setError('Backend health check failed')
      }
    } catch {
      setError('Cannot connect to AI-EMPLOYEE backend (localhost:3001)')
    }
  }

  return (
    <AnimatePresence mode="wait">
      {appState === 'boot' && (
        <BootSequence key="boot" onComplete={handleBootComplete} />
      )}
      {appState === 'connecting' && (
        <div key="connecting" className="fixed inset-0 flex items-center justify-center" style={{ background: '#050505' }}>
          <div className="font-mono text-sm" style={{ color: '#F5C400' }}>CONNECTING...</div>
        </div>
      )}
      {appState === 'login' && <LoginScreen key="login" />}
      {appState === 'dashboard' && <Dashboard key="dashboard" />}
      {appState === 'error' && <ErrorScreen key="error" />}
    </AnimatePresence>
  )
}

export default function App() {
  return (
    <div className="app">
      <AppContent />
    </div>
  )
}

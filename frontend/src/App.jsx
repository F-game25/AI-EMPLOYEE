import { AnimatePresence } from 'framer-motion'
import { useAppStore } from './store/appStore'
import BootSequence from './components/BootSequence'
import Dashboard from './components/Dashboard'
import { useWebSocket } from './hooks/useWebSocket'

function AppContent() {
  const { appState, login } = useAppStore()
  useWebSocket() // initialize WebSocket connection

  const handleBootComplete = () => {
    // Auto-login and go straight to dashboard — no login screen needed
    login('operator')
  }

  return (
    <AnimatePresence mode="sync">
      {appState === 'boot' && (
        <BootSequence key="boot" onComplete={handleBootComplete} />
      )}
      {appState === 'dashboard' && <Dashboard key="dashboard" />}
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

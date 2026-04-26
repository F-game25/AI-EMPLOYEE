import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useEffect } from 'react'
import { TopBar } from './components/TopBar'
import { Sidebar } from './components/Sidebar'
import { ErrorBoundary } from './components/ErrorBoundary'
import { useWebSocket } from './hooks/useWebSocket'
import { useStore } from './store/ascendStore'
import { Dashboard } from './pages/Dashboard'
import { AscendForge } from './pages/AscendForge'
import { MoneyMode } from './pages/MoneyMode'
import { BlacklightMode } from './pages/BlacklightMode'
import { HermesAgent } from './pages/HermesAgent'
import { Doctor } from './pages/Doctor'
import { LiveFeedback } from './pages/LiveFeedback'
import { Settings } from './pages/Settings'
import { FairnessDashboard } from './pages/FairnessDashboard'
import { GovernanceDashboard } from './pages/GovernanceDashboard'
import './styles/globals.css'

function AppShell() {
  useWebSocket()
  const { setMockMode, setAgents, setLlmStatus } = useStore()

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/health', { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setMockMode(d.mock || false))
      .catch(() => setMockMode(true))
    fetch('/api/agents', { signal: controller.signal })
      .then((r) => r.json())
      .then(setAgents)
      .catch(() => {})
    fetch('/api/llm/status', { signal: controller.signal })
      .then((r) => r.json())
      .then(setLlmStatus)
      .catch(() => {})
    return () => controller.abort()
  }, [setMockMode, setAgents, setLlmStatus])

  return (
    <div className="app-layout">
      <TopBar />
      <Sidebar />
      <main className="main-content">
        <AnimatePresence mode="wait">
          <Routes>
            <Route path="/" element={<ErrorBoundary fallbackTitle="Dashboard Error"><Dashboard /></ErrorBoundary>} />
            <Route path="/forge" element={<ErrorBoundary fallbackTitle="Ascend Forge Error"><AscendForge /></ErrorBoundary>} />
            <Route path="/money" element={<ErrorBoundary fallbackTitle="Money Mode Error"><MoneyMode /></ErrorBoundary>} />
            <Route path="/blacklight" element={<ErrorBoundary fallbackTitle="Blacklight Error"><BlacklightMode /></ErrorBoundary>} />
            <Route path="/hermes" element={<ErrorBoundary fallbackTitle="Hermes Error"><HermesAgent /></ErrorBoundary>} />
            <Route path="/doctor" element={<ErrorBoundary fallbackTitle="Doctor Error"><Doctor /></ErrorBoundary>} />
            <Route path="/live" element={<ErrorBoundary fallbackTitle="Live Feedback Error"><LiveFeedback /></ErrorBoundary>} />
            <Route path="/settings" element={<ErrorBoundary fallbackTitle="Settings Error"><Settings /></ErrorBoundary>} />
            <Route path="/fairness" element={<ErrorBoundary fallbackTitle="Fairness Error"><FairnessDashboard /></ErrorBoundary>} />
            <Route path="/governance" element={<ErrorBoundary fallbackTitle="Governance Error"><GovernanceDashboard /></ErrorBoundary>} />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary fallbackTitle="Application Error">
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </ErrorBoundary>
  )
}

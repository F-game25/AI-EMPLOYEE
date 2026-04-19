import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useEffect } from 'react'
import { TopBar } from './components/TopBar'
import { Sidebar } from './components/Sidebar'
import { useWebSocket } from './hooks/useWebSocket'
import { useStore } from './store/ascendStore'
import { Dashboard } from './pages/Dashboard'
import { AscendForge } from './pages/AscendForge'
import { MoneyMode } from './pages/MoneyMode'
import { BlacklightMode } from './pages/BlacklightMode'
import { Doctor } from './pages/Doctor'
import { LiveFeedback } from './pages/LiveFeedback'
import { Settings } from './pages/Settings'
import { FairnessDashboard } from './pages/FairnessDashboard'
import { GovernanceDashboard } from './pages/GovernanceDashboard'
import './styles/globals.css'

function AppShell() {
  useWebSocket()
  const { setMockMode, setAgents } = useStore()

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setMockMode(d.mock || false))
      .catch(() => setMockMode(true))
    fetch('/api/agents')
      .then((r) => r.json())
      .then(setAgents)
      .catch(() => {})
  }, [setMockMode, setAgents])

  return (
    <div className="app-layout">
      <TopBar />
      <Sidebar />
      <main className="main-content">
        <AnimatePresence mode="wait">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/forge" element={<AscendForge />} />
            <Route path="/money" element={<MoneyMode />} />
            <Route path="/blacklight" element={<BlacklightMode />} />
            <Route path="/doctor" element={<Doctor />} />
            <Route path="/live" element={<LiveFeedback />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/fairness" element={<FairnessDashboard />} />
            <Route path="/governance" element={<GovernanceDashboard />} />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}

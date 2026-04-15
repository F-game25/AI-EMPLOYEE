import { useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../store/appStore'
import Sidebar from './layout/Sidebar'
import ContextPanel from './layout/ContextPanel'
import DashboardPage from './pages/DashboardPage'
import AIControlPage from './pages/AIControlPage'
import NeuralBrainPage from './pages/NeuralBrainPage'
import OperationsPage from './pages/OperationsPage'
import AgentsPage from './pages/AgentsPage'
import SystemPage from './pages/SystemPage'
import VoicePage from './pages/VoicePage'
import { API_URL } from '../config/api'

const BASE = API_URL

const PAGES = {
  'dashboard': DashboardPage,
  'ai-control': AIControlPage,
  'neural-brain': NeuralBrainPage,
  'operations': OperationsPage,
  'agents': AgentsPage,
  'system': SystemPage,
  'voice': VoicePage,
}

export default function Dashboard() {
  const activeSection = useAppStore(s => s.activeSection)
  const setProductMetrics = useAppStore(s => s.setProductMetrics)
  const setAutomationStatus = useAppStore(s => s.setAutomationStatus)
  const setBrainInsights = useAppStore(s => s.setBrainInsights)
  const setBrainStatus = useAppStore(s => s.setBrainStatus)
  const setBrainActivity = useAppStore(s => s.setBrainActivity)
  const setWorkflowSnapshot = useAppStore(s => s.setWorkflowSnapshot)

  // Background data fetching — shared across all sections
  const refreshDashboard = useCallback(async () => {
    try {
      const [modeRes, dashRes] = await Promise.all([
        fetch(`${BASE}/api/mode`),
        fetch(`${BASE}/api/product/dashboard`),
      ])
      const modeData = await modeRes.json()
      const dashData = await dashRes.json()
      // modeData is fetched for dashboard sync but mode state is primarily
      // driven by WebSocket events stored in the Zustand store.
      if (modeData?.mode) { /* tracked via WebSocket */ }
      setProductMetrics(dashData || {})
      if (dashData?.learning?.brain) setBrainInsights(dashData.learning.brain)
      if (Array.isArray(dashData?.workflow_runs)) {
        setWorkflowSnapshot({
          active_run: dashData?.workflow_focus || null,
          runs: dashData.workflow_runs,
        })
      }
    } catch (e) {
      console.error('Failed to refresh dashboard', e)
      setAutomationStatus('Unable to refresh dashboard data.')
    }
  }, [setAutomationStatus, setProductMetrics, setBrainInsights, setWorkflowSnapshot])

  const refreshBrainRuntime = useCallback(async () => {
    try {
      const [statusRes, insightsRes, activityRes] = await Promise.all([
        fetch(`${BASE}/api/brain/status`),
        fetch(`${BASE}/api/brain/insights`),
        fetch(`${BASE}/api/brain/activity?limit=20`),
      ])
      const [statusData, insightsData, activityData] = await Promise.all([
        statusRes.json(),
        insightsRes.json(),
        activityRes.json(),
      ])
      if (statusData) setBrainStatus(statusData)
      if (insightsData) setBrainInsights(insightsData)
      if (activityData) setBrainActivity(activityData)
    } catch (e) {
      console.error('Failed to refresh brain runtime', e)
      // Keep current state; WebSocket updates continue in real time.
    }
  }, [setBrainActivity, setBrainInsights, setBrainStatus])

  useEffect(() => {
    refreshDashboard()
    const i = setInterval(refreshDashboard, 8000)
    return () => clearInterval(i)
  }, [refreshDashboard])

  useEffect(() => {
    refreshBrainRuntime()
    const i = setInterval(refreshBrainRuntime, 3000)
    return () => clearInterval(i)
  }, [refreshBrainRuntime])

  const PageComponent = PAGES[activeSection] || DashboardPage

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 flex scanlines"
      style={{ background: 'var(--bg-base)' }}
    >
      <Sidebar />

      {/* Main content area */}
      <main style={{
        flex: 1,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--space-5) var(--space-5) var(--space-8)',
        }}>
          <PageComponent />
        </div>
      </main>

      {/* Optional context panel */}
      <ContextPanel />
    </motion.div>
  )
}

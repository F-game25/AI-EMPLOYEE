import { useCallback, useEffect, lazy, Suspense } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAppStore } from '../store/appStore'
import { useBrainStore } from '../store/brainStore'
import Sidebar from './layout/Sidebar'
import ContextPanel from './layout/ContextPanel'

const DashboardPage       = lazy(() => import('./pages/DashboardPage'))
const ControlCenterPage   = lazy(() => import('./pages/ControlCenterPage'))
const AIControlPage       = lazy(() => import('./pages/AIControlPage'))
const NeuralBrainPage     = lazy(() => import('./pages/NeuralBrainPage'))
const OperationsPage      = lazy(() => import('./pages/OperationsPage'))
const AgentsPage          = lazy(() => import('./pages/AgentsPage'))
const SystemPage          = lazy(() => import('./pages/SystemPage'))
const VoicePage           = lazy(() => import('./pages/VoicePage'))
const LearningLadderPage  = lazy(() => import('./pages/LearningLadderPage'))
const PromptInspectorPage = lazy(() => import('./pages/PromptInspectorPage'))
const AscendForgePage     = lazy(() => import('./pages/AscendForgePage'))
const DoctorPage          = lazy(() => import('./pages/DoctorPage'))
const BlacklightPage      = lazy(() => import('./pages/BlacklightPage'))
const FairnessPage        = lazy(() => import('./pages/FairnessPage'))
const HermesPage          = lazy(() => import('./pages/HermesPage'))
const MoneyModePage       = lazy(() => import('./pages/MoneyModePage'))
const WorkspacePage       = lazy(() => import('./pages/WorkspacePage'))
const EvolutionPage       = lazy(() => import('./pages/EvolutionPage'))
const TrainingPage        = lazy(() => import('./pages/TrainingPage'))
import { API_URL } from '../config/api'
import TopBar from './dashboard/TopBar'
import ErrorBoundary from './ErrorBoundary'

const BASE = API_URL

const PAGES = {
  'dashboard': DashboardPage,
  'ai-control': AIControlPage,
  'neural-brain': NeuralBrainPage,
  'operations': OperationsPage,
  'agents': AgentsPage,
  'control-center': ControlCenterPage,
  'ascend-forge': AscendForgePage,
  'doctor': DoctorPage,
  'blacklight': BlacklightPage,
  'fairness': FairnessPage,
  'hermes': HermesPage,
  'learning-ladder': LearningLadderPage,
  'system': SystemPage,
  'voice': VoicePage,
  'prompt-inspector': PromptInspectorPage,
  'money-mode':       MoneyModePage,
  'workspace':        WorkspacePage,
  'evolution':        EvolutionPage,
  'training':         TrainingPage,
}

export default function Dashboard() {
  const activeSection = useAppStore(s => s.activeSection)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const navigate = useNavigate()
  const location = useLocation()

  // Sync URL → store when user navigates with browser back/forward
  useEffect(() => {
    const section = location.pathname.replace(/^\//, '') || 'dashboard'
    if (section !== activeSection) setActiveSection(section)
  }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync store → URL when in-app navigation changes activeSection
  useEffect(() => {
    const target = `/${activeSection}`
    if (location.pathname !== target) navigate(target, { replace: false })
  }, [activeSection]) // eslint-disable-line react-hooks/exhaustive-deps

  const setProductMetrics = useAppStore(s => s.setProductMetrics)
  const setAutomationStatus = useAppStore(s => s.setAutomationStatus)
  const setBrainInsights = useAppStore(s => s.setBrainInsights)
  const setBrainStatus = useAppStore(s => s.setBrainStatus)
  const setBrainActivity = useAppStore(s => s.setBrainActivity)
  const setWorkflowSnapshot = useAppStore(s => s.setWorkflowSnapshot)
  const setGraph = useBrainStore(s => s.setGraph)

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
      const [statusRes, insightsRes, activityRes, graphRes] = await Promise.all([
        fetch(`${BASE}/api/brain/status`),
        fetch(`${BASE}/api/brain/insights`),
        fetch(`${BASE}/api/brain/activity?limit=20`),
        fetch(`${BASE}/api/brain/graph`),
      ])
      const [statusData, insightsData, activityData, graphData] = await Promise.all([
        statusRes.json(),
        insightsRes.json(),
        activityRes.json(),
        graphRes.ok ? graphRes.json() : null,
      ])
      if (statusData) setBrainStatus(statusData)
      if (insightsData) setBrainInsights(insightsData)
      if (activityData) setBrainActivity(activityData)
      if (graphData) setGraph(graphData)
    } catch (e) {
      console.error('Failed to refresh brain runtime', e)
      // Keep current state; WebSocket updates continue in real time.
    }
  }, [setBrainActivity, setBrainInsights, setBrainStatus, setGraph])

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
        <TopBar />
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--space-2) var(--space-3)',
        }}>
          <ErrorBoundary key={activeSection} label={activeSection}>
            <Suspense fallback={
              <div style={{ padding: 32, color: 'var(--text-dim, #888)', fontFamily: 'var(--font-mono, monospace)', fontSize: 13 }}>
                Loading…
              </div>
            }>
              <PageComponent />
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>

      {/* Optional context panel */}
      <ContextPanel />
    </motion.div>
  )
}

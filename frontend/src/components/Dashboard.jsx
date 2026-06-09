import { useCallback, useEffect, lazy, Suspense, useState, useTransition } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAppStore } from '../store/appStore'
import Sidebar from './layout/Sidebar'
import MobileNav from './layout/MobileNav'
import ContextPanel from './layout/ContextPanel'
import CommandDock from './dock/CommandDock'
import ChatPanel from './core/ChatPanel'

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const handler = e => setMatches(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [query])
  return matches
}

const DashboardPage     = lazy(() => import('./pages/NexusOSDashboard'))
const AscendForgePage   = lazy(() => import('./pages/AscendForgePage'))
const WorkflowsPage     = lazy(() => import('./pages/WorkflowsPage'))
const WorkspacePage     = lazy(() => import('./pages/WorkspacePage'))
const OperationsPage    = lazy(() => import('./pages/OperationsPage'))
const SettingsPage      = lazy(() => import('./pages/SettingsPage'))
const NeuralNetworkPage = lazy(() => import('./pages/NeuralNetworkPage'))
const GraphsPage        = lazy(() => import('./pages/GraphsPage'))
const IntelligencePage  = lazy(() => import('./pages/IntelligencePage'))
const SystemHealthPage  = lazy(() => import('./pages/SystemHealthPage'))
const SystemSetupCenter = lazy(() => import('./pages/SystemSetupCenter'))
const ProofCenter       = lazy(() => import('./pages/ProofCenter'))
const ApprovalInbox     = lazy(() => import('./pages/ApprovalInbox'))
const ApiCatalogPage    = lazy(() => import('./pages/ApiCatalogPage'))
const UserExperienceCenter = lazy(() => import('./pages/UserExperienceCenter'))
const IntegrationsPage  = lazy(() => import('./pages/IntegrationsPage'))
const ModelsPage        = lazy(() => import('./pages/ModelsPage'))
const ModelFabricPage   = lazy(() => import('./pages/ModelFabricPage'))
const ComputeCenterPage = lazy(() => import('./pages/ComputeCenterPage'))
const AgentsPage        = lazy(() => import('./pages/AgentsPage'))
const MoneyModePage     = lazy(() => import('./pages/MoneyModePage'))
const SecurityPanel     = lazy(() => import('./pages/SecurityPanel'))
const MemoryPage        = lazy(() => import('./pages/MemoryPage'))
const KnowledgePage     = lazy(() => import('./pages/KnowledgePage'))
const ResearchPage      = lazy(() => import('./pages/ResearchPage'))
const CognitionPage     = lazy(() => import('./pages/CognitionPage'))
const ReconPage         = lazy(() => import('./pages/ReconPage'))
const PromptInspectorPage = lazy(() => import('./pages/PromptInspectorPage'))
const SalesPage         = lazy(() => import('./pages/sales/SalesPage'))
const AvatarLabPage     = lazy(() => import('./pages/AvatarLabPage'))
const QuantumBrainPage   = lazy(() => import('./pages/QuantumBrainPage'))
const DeepResearchPage   = lazy(() => import('./pages/DeepResearchPage'))
const OrdersPage         = lazy(() => import('./pages/OrdersPage'))
import { API_URL } from '../config/api'
import { usePerformanceMode } from '../hooks/usePerformanceMode'
import TopBar from './dashboard/TopBar'
import BottomDrawer from './dock/BottomDrawer'
import ErrorBoundary from './ErrorBoundary'
import CommandPalette from './ui/CommandPalette'
import VoiceModal from './ui/VoiceModal'

const BASE = API_URL

const PAGES = {
  // Legacy aliases
  'dashboard':      DashboardPage,
  'neural-network': NeuralNetworkPage,
  'intelligence':   IntelligencePage,
  'operations':     OperationsPage,
  'ascend-forge':   AscendForgePage,
  'system':         SystemHealthPage,
  'setup':          SystemSetupCenter,
  'system-setup':   SystemSetupCenter,
  'workspace':      WorkspacePage,
  'integrations':   IntegrationsPage,
  'settings':       SettingsPage,
  // CORE
  'nexus':          DashboardPage,
  'cognition':      CognitionPage,
  'agents':         AgentsPage,
  'memory':         MemoryPage,
  'economy':        MoneyModePage,
  'sales':          SalesPage,
  'orders':         SalesPage,
  // OPERATIONS
  'tasks':          OperationsPage,
  'workflows':      WorkflowsPage,
  'infrastructure': SystemHealthPage,
  'deployments':    SystemHealthPage,
  // INTELLIGENCE
  'neural-graph':   NeuralNetworkPage,
  'graphs':         GraphsPage,
  'memory-graphs':  GraphsPage,
  'knowledge':      KnowledgePage,
  'trends':         IntelligencePage,
  'research':       ResearchPage,
  'deep-research':  DeepResearchPage,
  'recon':          ReconPage,
  'prompt-inspector': PromptInspectorPage,
  // SECURITY — panel switches internally on activeSection
  'policies':       SecurityPanel,
  'security':       SecurityPanel,
  'blacklight':     SecurityPanel,
  'audit':          SecurityPanel,
  'proof':          ProofCenter,
  'proof-center':   ProofCenter,
  'approvals':      ApprovalInbox,
  'approval-inbox': ApprovalInbox,
  // SYSTEM
  'models':         ModelsPage,
  'model-fabric':   ModelFabricPage,
  'compute':        ComputeCenterPage,
  'compute-center': ComputeCenterPage,
  'runtime':        SystemHealthPage,
  'api-catalog':    ApiCatalogPage,
  'user-views':     UserExperienceCenter,
  'roles':          UserExperienceCenter,
  'perspectives':   UserExperienceCenter,
  'avatar-lab':     AvatarLabPage,
  'quantum-brain':  QuantumBrainPage,
}

function DashboardMountedSignal({ section }) {
  useEffect(() => {
    try {
      window.ai?.notifyUiMounted?.({
        phase: 'dashboard-rendered',
        section,
        message: `Dashboard rendered: ${section}`,
      })
    } catch {
      // Electron IPC is best-effort; browser mode has no launcher.
    }
  }, [section])
  return null
}

function SystemBanner() {
  const [rateLimitSecs, setRateLimitSecs] = useState(0)
  const [pythonOffline, setPythonOffline] = useState(false)

  // Rate limit countdown
  useEffect(() => {
    const handler = e => setRateLimitSecs(e.detail?.seconds || 60)
    window.addEventListener('nx:rate-limit', handler)
    return () => window.removeEventListener('nx:rate-limit', handler)
  }, [])
  useEffect(() => {
    if (rateLimitSecs <= 0) return
    const t = setTimeout(() => setRateLimitSecs(s => Math.max(0, s - 1)), 1000)
    return () => clearTimeout(t)
  }, [rateLimitSecs])

  // Python backend health check (every 30s)
  useEffect(() => {
    const check = () => fetch('/api/health', { signal: AbortSignal.timeout(4000) })
      .then(r => r.json())
      .then(d => setPythonOffline(d?.python === false || d?.services?.python === 'offline'))
      .catch(() => {})
    check()
    const t = setInterval(check, 30000)
    return () => clearInterval(t)
  }, [])

  if (!rateLimitSecs && !pythonOffline) return null
  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999,
      display: 'flex', flexDirection: 'column', gap: 0,
      fontFamily: 'var(--nx-font-mono, monospace)', fontSize: 12,
    }}>
      {rateLimitSecs > 0 && (
        <div style={{
          background: 'rgba(229,150,0,0.92)', color: '#000',
          padding: '6px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>⚡ Rate limit reached — retry in {rateLimitSecs}s</span>
          <button onClick={() => setRateLimitSecs(0)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}>✕</button>
        </div>
      )}
      {pythonOffline && (
        <div style={{
          background: 'rgba(180,30,30,0.92)', color: '#fff',
          padding: '6px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>⚠ AI backend offline — run <code style={{ background: 'rgba(0,0,0,0.3)', padding: '1px 4px', borderRadius: 3 }}>bash start.sh</code> to enable full AI features</span>
          <button onClick={() => setPythonOffline(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#fff', fontWeight: 700 }}>✕</button>
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const [chatPanelOpen, setChatPanelOpen] = useState(false)
  const isMobile = useMediaQuery('(max-width: 768px)')
  const activeSection = useAppStore(s => s.activeSection)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const navigate = useNavigate()
  const location = useLocation()
  const { tier } = usePerformanceMode()

  // Non-blocking page swaps: `activeSection` (store) updates instantly so URL sync,
  // sidebar highlight and the click feel immediate; the heavy page mount is deferred
  // into a transition via `renderedSection`, keeping the previous page on screen until
  // the new one is ready. `isPending` drives a subtle loading affordance.
  const [renderedSection, setRenderedSection] = useState(activeSection)
  const [isPending, startTransition] = useTransition()
  useEffect(() => {
    if (activeSection === renderedSection) return
    startTransition(() => setRenderedSection(activeSection))
  }, [activeSection, renderedSection])

  // Expose the performance tier as a root attribute so CSS can drop expensive
  // compositing (backdrop blurs, scanlines, animations) on low/Lite mode.
  useEffect(() => {
    document.documentElement.dataset.perf = (tier === 'high') ? 'high' : 'low'
  }, [tier])

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

  const wsConnected = useAppStore(s => s.wsConnected)
  const setProductMetrics = useAppStore(s => s.setProductMetrics)
  const setAutomationStatus = useAppStore(s => s.setAutomationStatus)
  const setBrainInsights = useAppStore(s => s.setBrainInsights)
  const setWorkflowSnapshot = useAppStore(s => s.setWorkflowSnapshot)

  // Initial hydration fetch — runs once on mount; WS broadcast handles all subsequent updates
  const refreshDashboard = useCallback(async () => {
    try {
      const [modeRes, dashRes] = await Promise.all([
        fetch(`${BASE}/api/mode`),
        fetch(`${BASE}/api/product/dashboard`),
      ])
      const dashData = await dashRes.json()
      await modeRes.json()
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

  // Initial hydration only; fallback REST poll only when WS is disconnected
  useEffect(() => {
    refreshDashboard()
    if (wsConnected) return
    const i = setInterval(refreshDashboard, 8000)
    return () => clearInterval(i)
  }, [refreshDashboard, wsConnected])
  // Brain runtime data is now entirely WS-driven (broadcast every 5s from server)

  // Keyboard shortcuts for chat panel (Alt+T / Meta+T)
  // Note: Ctrl/Cmd+K is owned by CommandPalette
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.altKey || e.metaKey) && e.key === 't') {
        e.preventDefault()
        setChatPanelOpen(v => !v)
      }
      if (e.key === 'Escape' && chatPanelOpen) {
        setChatPanelOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [chatPanelOpen])

  // Listen for the topbar/search-pill → open chat command
  useEffect(() => {
    const openChat = () => setChatPanelOpen(true)
    window.addEventListener('nx:chat:open', openChat)
    return () => window.removeEventListener('nx:chat:open', openChat)
  }, [])

  // Companion click (dashboard eye / toolbar eye) → open chat panel
  useEffect(() => {
    const openCompanion = () => setChatPanelOpen(v => !v)
    window.addEventListener('nx:companion:open', openCompanion)
    return () => window.removeEventListener('nx:companion:open', openCompanion)
  }, [])

  // Page-coupled bits follow `renderedSection` so the boundary/container stay paired
  // with the page that is actually mounted during a pending transition.
  const PageComponent = PAGES[renderedSection] || DashboardPage
  const isFullscreen = renderedSection === 'dashboard' || renderedSection === 'nexus'
  const showCommandDock = true

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 flex scanlines"
      style={{ background: 'var(--bg-base)' }}
    >
      <SystemBanner />
      <a href="#main-content" className="skip-link">Skip to content</a>
      <Sidebar />

      {/* Main content area */}
      <main id="main-content" style={{
        flex: 1,
        minWidth: 0,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        paddingBottom: isMobile ? 60 : (showCommandDock ? 116 : 0),
        marginLeft: isMobile ? 0 : undefined,
      }}>
        <TopBar />
        <div style={{
          flex: 1,
          minHeight: 0,    // allow this flex child to shrink so the scroll region below works
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          padding: isFullscreen ? 0 : 'var(--space-2) var(--space-3)',
        }}>
          <ErrorBoundary key={renderedSection} label={renderedSection} severity="page">
            <Suspense fallback={
              <div style={{ flex: 1, minHeight: 0, padding: 32, color: 'var(--text-dim, #888)', fontFamily: 'var(--nx-font-mono, monospace)', fontSize: 13 }}>
                Loading…
              </div>
            }>
              {/* Always a flex column with a definite height: full-height pages (Forge,
                  graphs) fill it; long pages scroll inside it. Scroll lives here, not on
                  the parent, so height:100% pages don't collapse in non-fullscreen.
                  During a pending page transition the previous page stays mounted but is
                  dimmed slightly so the swap reads as intentional, not janky. */}
              <div style={{
                flex: 1,
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
                overflowY: isFullscreen ? 'hidden' : 'auto',
                opacity: isPending ? 0.6 : 1,
                transition: 'opacity 0.15s ease',
              }}>
                <PageComponent />
                <DashboardMountedSignal section={renderedSection} />
              </div>
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>

      {/* Optional context panel */}
      <ContextPanel />

      {/* Bottom Drawer + Command Bar — desktop only */}
      {!isMobile && <BottomDrawer />}
      {!isMobile && <CommandDock onToggleChat={setChatPanelOpen} chatOpen={chatPanelOpen} />}
      <ChatPanel isOpen={chatPanelOpen} onClose={() => setChatPanelOpen(false)} />
      <CommandPalette />
      <VoiceModal />

      {/* Mobile bottom navigation */}
      {isMobile && <MobileNav />}
    </motion.div>
  )
}

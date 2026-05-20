import { create } from 'zustand'

// ── localStorage hydrate/persist (metric fields only — never chat or event histories) ──
const SNAPSHOT_KEY = 'nexus:snapshot:system'
const PERSIST_FIELDS = ['systemStatus', 'systemHealth', 'backendStatus']
let _persistTimer = null

function loadSnapshot() {
  try {
    const raw = localStorage.getItem(SNAPSHOT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch { return null }
}

function schedulePersist(getState) {
  if (_persistTimer) return
  _persistTimer = setTimeout(() => {
    _persistTimer = null
    try {
      const s = getState()
      const snapshot = {}
      for (const f of PERSIST_FIELDS) snapshot[f] = s[f]
      localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot))
    } catch (_e) { /* localStorage full or unavailable — skip persist */ }
  }, 5000)
}

const HYDRATED = (typeof localStorage !== 'undefined') ? (loadSnapshot() || {}) : {}

const DEFAULT_BACKEND_STATUS = {
  python_ok: false,
  llm_ok: false,
  node_ok: false,
  neural_brain_ok: false,
  graph_ok: false,
  ws_connected: false,
  readiness_phase: 'BOOTING',
  degraded: true,
  degradedReasons: [],
  last_seen: 0,
}

const DEFAULT_SYSTEM_STATUS = {
  cpu: 0, memory: 0, uptime: 0, connections: 0,
  cpu_usage: 0, gpu_usage: 0, cpu_temperature: 0, gpu_temperature: 0,
  heartbeat: 0, running_agents: 0, total_agents: 0,
  mode: 'MANUAL', robot_location: 'idle', active_robot: 'none',
  active_subsystem: 'general', thinking_mode: '', money_template: null,
}

export const useSystemStore = create((set, get) => ({
  // App lifecycle
  appState: 'connecting',
  setAppState: (s) => set({ appState: s }),

  // Legacy single flag — kept as derived alias for backward compat with App.jsx & SystemBar
  // Existing setter still works but new code should use setBackendStatus.
  pythonBackendReady: !!HYDRATED.backendStatus?.python_ok,
  setPythonBackendReady: (v) => {
    set(state => ({
      pythonBackendReady: !!v,
      backendStatus: { ...state.backendStatus, python_ok: !!v, last_seen: Date.now() },
    }))
    schedulePersist(get)
  },

  // Backend health (new structure — replaces ad-hoc flags)
  backendStatus: { ...DEFAULT_BACKEND_STATUS, ...(HYDRATED.backendStatus || {}), ws_connected: false },
  setBackendStatus: (partial) => {
    set(state => ({
      backendStatus: { ...state.backendStatus, ...(partial || {}), last_seen: Date.now() },
      // mirror python_ok into legacy flag so existing consumers keep working
      pythonBackendReady: partial?.python_ok != null ? !!partial.python_ok : state.pythonBackendReady,
    }))
    schedulePersist(get)
  },

  readiness: {
    nodeReady: false,
    pythonReady: false,
    subsystemsReady: false,
    neuralBrainReady: false,
    graphReady: false,
    phase: 'BOOTING',
    degraded: true,
    degradedReasons: [],
    lastChecked: 0,
  },
  setReadiness: (partial) => {
    const next = {
      nodeReady: !!partial?.nodeReady,
      pythonReady: !!partial?.pythonReady,
      subsystemsReady: !!partial?.subsystemsReady,
      neuralBrainReady: !!partial?.neuralBrainReady,
      graphReady: !!partial?.graphReady,
      phase: partial?.phase || 'UNKNOWN',
      degraded: !!partial?.degraded,
      degradedReasons: Array.isArray(partial?.degradedReasons) ? partial.degradedReasons : [],
      lastChecked: Date.now(),
    }
    set(state => ({
      readiness: next,
      pythonBackendReady: next.pythonReady,
      backendStatus: {
        ...state.backendStatus,
        node_ok: next.nodeReady,
        python_ok: next.pythonReady,
        neural_brain_ok: next.neuralBrainReady,
        graph_ok: next.graphReady,
        readiness_phase: next.phase,
        degraded: next.degraded,
        degradedReasons: next.degradedReasons,
        last_seen: Date.now(),
      },
    }))
    schedulePersist(get)
  },

  // Navigation — initialize from the URL so deep links / refresh restore the page
  activeSection: (() => {
    try {
      const seg = (window.location.pathname || '').replace(/^\/+/, '').split('/')[0]
      return seg || 'dashboard'
    } catch { return 'dashboard' }
  })(),
  setActiveSection: (s) => set({ activeSection: s }),

  // Sidebar
  sidebarCollapsed: false,
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  mobileSidebarOpen: false,
  toggleMobileSidebar: () => set(s => ({ mobileSidebarOpen: !s.mobileSidebarOpen })),
  setMobileSidebarOpen: (v) => set({ mobileSidebarOpen: v }),

  // WebSocket
  ws: null,
  wsConnected: false,
  setWs: (ws) => set({ ws }),
  setWsConnected: (v) => set(state => ({
    wsConnected: v,
    backendStatus: { ...state.backendStatus, ws_connected: !!v, last_seen: Date.now() },
  })),

  // Heartbeat log
  heartbeatLogs: [],
  addHeartbeatLog: (log) => set((state) => ({
    heartbeatLogs: [...state.heartbeatLogs.slice(-199), log],
  })),

  // System status (hardware, agents, mode) — hydrated from snapshot
  systemStatus: { ...DEFAULT_SYSTEM_STATUS, ...(HYDRATED.systemStatus || {}) },
  setSystemStatus: (s) => { set({ systemStatus: s, freshness_ms: Date.now() }); schedulePersist(get) },

  // Health
  systemHealth: HYDRATED.systemHealth || { uptime: 0, errors_per_minute: 0, status: 'unknown' },
  setSystemHealth: (h) => { set({ systemHealth: h, freshness_ms: Date.now() }); schedulePersist(get) },

  // Last-update timestamp for STALE / LIVE / OFFLINE pills
  freshness_ms: 0,

  // Error state
  errorMessage: null,
  setError: (msg) => set({ errorMessage: msg, appState: 'error' }),

  // Debug mode
  debugMode: false,
  setDebugMode: (v) => set({ debugMode: v }),
  toggleDebugMode: () => set((state) => ({ debugMode: !state.debugMode })),

  // Selected event
  selectedEventId: null,
  setSelectedEventId: (id) => set({ selectedEventId: id }),

  // Update status
  updateStatus: {
    available: false, checking: false, applying: false,
    lastChecked: null, currentCommit: null, remoteCommit: null,
    progress: 0, stage: null, log: [], error: null, updateComplete: false,
  },
  setUpdateStatus: (partial) => set(state => ({ updateStatus: { ...state.updateStatus, ...partial } })),
  appendUpdateLog: (entry) => set(state => ({ updateStatus: { ...state.updateStatus, log: [...state.updateStatus.log.slice(-499), entry] } })),
  clearUpdateLog: () => set(state => ({ updateStatus: { ...state.updateStatus, log: [], error: null, progress: 0, stage: null } })),

  // Critical alert flag — set true for 30s on security:breach / system:critical_failure.
  // Causes both central avatar + mini-eye to switch to deep red (#dc2626).
  criticalAlert: false,
  _criticalTimer: null,
  triggerCriticalAlert: () => set(state => {
    if (state._criticalTimer) clearTimeout(state._criticalTimer)
    const timer = setTimeout(() => {
      useSystemStore.setState({ criticalAlert: false, _criticalTimer: null })
    }, 30000)
    return { criticalAlert: true, _criticalTimer: timer }
  }),
  clearCriticalAlert: () => set(state => {
    if (state._criticalTimer) clearTimeout(state._criticalTimer)
    return { criticalAlert: false, _criticalTimer: null }
  }),
}))

// ── Selector helpers ───────────────────────────────────────────
// Returns { healthy, reason } — reason is null when healthy, otherwise a specific string
// describing what's offline. Banner reads this directly.
export function selectBackendHealth(s) {
  const b = s?.backendStatus || DEFAULT_BACKEND_STATUS
  if (!b.node_ok)        return { healthy: false, reason: 'Node backend offline' }
  if (!b.ws_connected)   return { healthy: false, reason: 'WebSocket reconnecting' }
  if (!b.python_ok)      return { healthy: false, reason: 'Python LLM offline' }
  if (!b.llm_ok)         return { healthy: false, reason: 'LLM service unavailable' }
  return { healthy: true, reason: null }
}

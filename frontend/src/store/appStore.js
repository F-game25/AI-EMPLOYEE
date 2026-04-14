import { create } from 'zustand'

const MAX_ACTIVITY_ITEMS = 50
const MAX_EXECUTION_LOGS = 100

export const useAppStore = create((set) => ({
  // State machine
  appState: 'boot', // boot | connecting | login | dashboard | error
  setAppState: (s) => set({ appState: s }),

  // Navigation — 5 core sections
  activeSection: 'dashboard', // dashboard | ai-control | operations | agents | system
  setActiveSection: (s) => set({ activeSection: s }),

  // Context panel (slides in from right)
  contextPanel: null, // null or { type, data }
  setContextPanel: (panel) => set({ contextPanel: panel }),
  closeContextPanel: () => set({ contextPanel: null }),

  // Auth
  user: null,
  login: (username) => set({ user: { username }, appState: 'dashboard' }),
  logout: () => set({ user: null, appState: 'login' }),

  // WebSocket
  ws: null,
  wsConnected: false,
  setWs: (ws) => set({ ws }),
  setWsConnected: (v) => set({ wsConnected: v }),

  // Heartbeat logs
  heartbeatLogs: [],
  addHeartbeatLog: (log) => set((state) => ({
    heartbeatLogs: [...state.heartbeatLogs.slice(-199), log],
  })),

  // Agents
  agents: [],
  setAgents: (agents) => set({ agents }),

  // Chat
  chatMessages: [],
  addChatMessage: (msg) => set((state) => ({
    chatMessages: [...state.chatMessages, msg],
  })),
  updateLastAiMessage: (text) => set((state) => {
    const msgs = [...state.chatMessages]
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'ai') {
        msgs[i] = { ...msgs[i], content: text }
        break
      }
    }
    return { chatMessages: msgs }
  }),

  // Typing indicator — true while waiting for AI response
  isTyping: false,
  setTyping: (v) => set({ isTyping: v }),

  // System status
  systemStatus: {
    cpu: 0,
    memory: 0,
    uptime: 0,
    connections: 0,
    cpu_usage: 0,
    gpu_usage: 0,
    cpu_temperature: 0,
    gpu_temperature: 0,
    heartbeat: 0,
    running_agents: 0,
    total_agents: 0,
    mode: 'MANUAL',
    robot_location: 'idle',
    active_robot: 'none',
    active_subsystem: 'general',
    thinking_mode: '',
    money_template: null,
  },
  setSystemStatus: (s) => set({ systemStatus: s }),

  objectivePanels: {
    money_mode: {
      active: false,
      status: 'inactive',
      current_objective: null,
      active_tasks: [],
      progress: 0,
      agents_used: [],
      performance: {},
      result: null,
    },
    ascend_forge: {
      active: false,
      status: 'inactive',
      current_objective: null,
      plan: [],
      active_tasks: [],
      progress: 0,
      agents_used: [],
      results: [],
      result: null,
    },
  },
  setObjectivePanel: (system, payload) => set((state) => ({
    objectivePanels: {
      ...state.objectivePanels,
      [system]: {
        ...(state.objectivePanels?.[system] || {}),
        ...(payload || {}),
      },
    },
  })),

  // Neural Network status
  nnStatus: {
    available: true,
    active: true,
    mode: 'INITIALIZING',
    learn_step: 0,
    buffer_size: 0,
    max_buffer_size: 10000,
    last_loss: null,
    confidence: 0,
    device: 'cpu',
    total_actions: 8,
    experiences: 0,
    memory_size: 0,
    bg_running: false,
    recent_outputs: [],
    recent_learning_events: [],
    updated_at: null,
  },
  setNnStatus: (s) => set({ nnStatus: s }),

  // Memory Tree
  memoryTree: {
    total_entities: 0,
    nodes: [],
    recent_updates: [],
    updated_at: null,
  },
  setMemoryTree: (t) => set({ memoryTree: t }),

  // Doctor / System Health
  doctorStatus: {
    available: false,
    grade: null,
    overall_score: 0,
    scores: {},
    issues: [],
    strengths: [],
    last_run: null,
    updated_at: null,
  },
  setDoctorStatus: (d) => set({ doctorStatus: d }),

  brainInsights: {
    active: true,
    learned_strategies: [],
    task_patterns: [],
    recent_improvements: [],
    performance_metrics: {},
    decisions: [],
    updated_at: null,
  },
  setBrainInsights: (insights) => set({ brainInsights: insights }),

  brainStatus: {
    status: 'active',
    active: true,
    available: true,
    memory_size: 0,
    last_update: null,
    recent_decisions: [],
  },
  setBrainStatus: (status) => set({ brainStatus: status }),

  brainActivity: {
    status: 'active',
    memory_size: 0,
    last_update: null,
    recent_decisions: [],
    items: [],
  },
  setBrainActivity: (activity) => set({ brainActivity: activity }),

  // Self-improvement pipeline (HTTP-polled from Python runtime)
  selfImprovement: {
    active: false,
    total_tasks_processed: 0,
    queue_depth: 0,
    pass_rate: 0,
    fail_rate: 0,
    approval_ratio: 0,
    rejection_ratio: 0,
    rollback_ratio: 0,
    deployed: 0,
    rolled_back: 0,
    rejected: 0,
    test_failures: 0,
    policy_violations: 0,
    errors: 0,
    top_failure_causes: [],
    recent_events: [],
  },
  setSelfImprovement: (si) => set({ selfImprovement: si }),

  // Autonomy daemon state (WebSocket-driven)
  autonomyStatus: {
    mode: { mode: 'OFF', active: false, auto: false, limited: false, paused: true, emergency_stopped: false, changed_at: null },
    daemon: { running: false, started_at: null, cycles: 0, tasks_processed: 0, tasks_succeeded: 0, tasks_failed: 0, consecutive_errors: 0, last_cycle_at: null, last_task_id: null, current_task_id: null, cycle_interval_s: 2 },
    queue: { total: 0, active: 0, by_status: {} },
    data_source: 'initializing',
    updated_at: null,
  },
  setAutonomyStatus: (a) => set({ autonomyStatus: a }),

  // Error
  errorMessage: null,
  setError: (msg) => set({ errorMessage: msg, appState: 'error' }),

  // Product dashboard (HTTP-polled snapshot for KPIs)
  productMetrics: {
    mode: {},
    tasks: {},
    revenue: {},
    value: {},
    top_strategies: [],
    activity_feed: [],
    execution_logs: [],
    pipelines: {},
    pipeline_runs: [],
    pending_actions: [],
    learning: {},
  },
  setProductMetrics: (m) => set({ productMetrics: m }),

  automationStatus: '',
  setAutomationStatus: (v) => set({ automationStatus: v }),

  // Real-time activity feed — driven by WebSocket events
  activityFeed: [],
  addActivityItem: (item) => set((state) => ({
    activityFeed: [item, ...state.activityFeed].slice(0, MAX_ACTIVITY_ITEMS),
  })),
  setActivitySnapshot: (items) => set({ activityFeed: items.slice(0, MAX_ACTIVITY_ITEMS) }),

  // Real-time execution log — driven by WebSocket events
  executionLogs: [],
  addExecutionLog: (log) => set((state) => ({
    executionLogs: [log, ...state.executionLogs].slice(0, MAX_EXECUTION_LOGS),
  })),
  setExecutionSnapshot: (logs) => set({ executionLogs: logs.slice(0, MAX_EXECUTION_LOGS) }),

  workflowState: {
    active_run: null,
    runs: [],
  },
  setWorkflowSnapshot: (payload) => set({
    workflowState: {
      active_run: payload?.active_run ?? null,
      runs: Array.isArray(payload?.runs) ? payload.runs : [],
    },
  }),
  upsertWorkflowRun: (run) => set((state) => {
    const prevRuns = state.workflowState?.runs || []
    const nextRuns = [run, ...prevRuns.filter((r) => r.run_id !== run.run_id)].slice(0, 50)
    return {
      workflowState: {
        active_run: run?.run_id || state.workflowState?.active_run || null,
        runs: nextRuns,
      },
    }
  }),
}))

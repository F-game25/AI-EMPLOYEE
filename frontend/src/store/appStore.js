/**
 * BACKWARD COMPATIBILITY FACADE
 *
 * Re-exports all domain stores under the useAppStore interface.
 * Existing code importing from appStore continues to work without changes.
 *
 * NEW CODE should import domain stores directly:
 * - useSystemStore: appState, ws, systemStatus, debugMode, errors
 * - useCognitiveStore: brainState, avatarState, reasoningSteps, modelCalls
 * - useAgentStore: agents list + per-agent state
 * - useTaskStore: chatMessages, executionSteps, workflowState
 * - useEconomyStore: revenue, monetization pipelines, activityFeed
 * - useSecurityStore: threat_score, autonomyStatus, mode
 * - useEventFeedStore: universal event stream
 * - useBrainStore: graph data, nodes, links (unchanged)
 */

import { useMemo } from 'react'
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import { useSystemStore } from './systemStore'
import { useCognitiveStore } from './cognitiveStore'
import { useAgentStore } from './agentStore'
import { useTaskStore } from './taskStore'
import { useEconomyStore } from './economyStore'
import { useSecurityStore } from './securityStore'
import { useEventFeedStore } from './eventFeedStore'
import { useBrainStore } from './brainStore'

const NOOP = () => {}
const NOOP_MEMORY_TREE = { total_entities: 0, nodes: [], recent_updates: [] }
// Identity selector used with useShallow so whole-store subscriptions only
// re-render when any top-level field reference changes (not on every write).
const identity = s => s

const useLegacyAppStore = create((set, get) => ({
  user: null,
  identity: null,
  hermesGoal: '',
  alphaArchive: [],
  automationRules: [],
  contextPanel: null,
  inspectorEnabled: true,
  promptTraces: [],
  forgeQueue: [],
  observability: { system_health: {}, metrics: {}, events: [] },

  login: (user) => {
    useSystemStore.getState().setAppState('dashboard')
    set({ user, identity: user })
  },
  logout: () => {
    useSystemStore.getState().setAppState('login')
    set({ user: null, identity: null })
  },
  setIdentity: (identity) => set({ identity }),
  setHermesGoal: (hermesGoal) => set({ hermesGoal }),
  addAlphaEntry: (entry) => set((state) => ({
    alphaArchive: [...state.alphaArchive, entry].slice(-100),
  })),
  addAutomationRule: (rule) => set((state) => ({
    automationRules: [...state.automationRules, rule],
  })),
  removeAutomationRule: (id) => set((state) => ({
    automationRules: state.automationRules.filter(rule => rule.id !== id),
  })),
  addPromptTrace: (trace) => set((state) => ({
    promptTraces: [...state.promptTraces, trace].slice(-100),
  })),
  setPromptTraces: (promptTraces) => set({
    promptTraces: Array.isArray(promptTraces) ? promptTraces.slice(-100) : [],
  }),
  setInspectorEnabled: (inspectorEnabled) => set({ inspectorEnabled }),
  setForgeQueue: (forgeQueue) => set({
    forgeQueue: Array.isArray(forgeQueue) ? forgeQueue : [],
  }),
  upsertForgeItem: (item) => set((state) => {
    const id = item?.id || item?.name
    if (!id) return state
    const idx = state.forgeQueue.findIndex(existing => (existing.id || existing.name) === id)
    if (idx < 0) return { forgeQueue: [...state.forgeQueue, item] }
    const next = [...state.forgeQueue]
    next[idx] = { ...next[idx], ...item }
    return { forgeQueue: next }
  }),
  setObservability: (observability) => set({ observability }),
  setContextPanel: (contextPanel) => set({ contextPanel }),
  closeContextPanel: () => set({ contextPanel: null }),
}))

export const useAppStore = (selector) => {
  const sys = useSystemStore(useShallow(identity))
  const cog = useCognitiveStore(useShallow(identity))
  const agent = useAgentStore(useShallow(identity))
  const task = useTaskStore(useShallow(identity))
  const econ = useEconomyStore(useShallow(identity))
  const sec = useSecurityStore(useShallow(identity))
  const evt = useEventFeedStore(useShallow(identity))
  const brain = useBrainStore(useShallow(identity))
  const legacy = useLegacyAppStore(useShallow(identity))

  const composite = useMemo(
    () => buildCompositeState(sys, cog, agent, task, econ, sec, evt, brain, legacy),
    [sys, cog, agent, task, econ, sec, evt, brain, legacy]
  )

  if (selector) return selector(composite)
  return composite
}

// Merge all domain stores into single object
function buildCompositeState(sys, cog, agent, task, econ, sec, evt, brain, legacy) {
  return {
    // ── System Store ──────────────────────────────────
    appState: sys?.appState,
    setAppState: sys?.setAppState,
    pythonBackendReady: sys?.pythonBackendReady,
    setPythonBackendReady: sys?.setPythonBackendReady,
    readiness: sys?.readiness,
    setReadiness: sys?.setReadiness,
    backendStatus: sys?.backendStatus,
    setBackendStatus: sys?.setBackendStatus,
    activeSection: sys?.activeSection,
    setActiveSection: sys?.setActiveSection,
    sidebarCollapsed: sys?.sidebarCollapsed,
    setSidebarCollapsed: sys?.setSidebarCollapsed,
    ws: sys?.ws,
    wsConnected: sys?.wsConnected,
    setWs: sys?.setWs,
    setWsConnected: sys?.setWsConnected,
    heartbeatLogs: sys?.heartbeatLogs,
    addHeartbeatLog: sys?.addHeartbeatLog,
    systemStatus: sys?.systemStatus,
    setSystemStatus: sys?.setSystemStatus,
    systemHealth: sys?.systemHealth,
    setSystemHealth: sys?.setSystemHealth,
    errorMessage: sys?.errorMessage,
    setError: sys?.setError,
    debugMode: sys?.debugMode,
    setDebugMode: sys?.setDebugMode,
    toggleDebugMode: sys?.toggleDebugMode,
    selectedEventId: sys?.selectedEventId,
    setSelectedEventId: sys?.setSelectedEventId,

    // ── Cognitive Store ───────────────────────────────
    brainState: cog?.brainState,
    setBrainState: cog?.setBrainState,
    reasoningSteps: cog?.reasoningSteps,
    appendReasoningStep: cog?.appendReasoningStep,
    clearReasoningSteps: cog?.clearReasoningSteps,
    modelCalls: cog?.modelCalls,
    recordModelCall: cog?.recordModelCall,
    clearModelCalls: cog?.clearModelCalls,
    avatarState: cog?.avatarState,
    setAvatarState: cog?.setAvatarState,
    isAvatarActive: cog?.isAvatarActive,
    brainInsights: cog?.brainInsights,
    setBrainInsights: cog?.setBrainInsights,
    brainActivity: cog?.brainActivity,
    setBrainActivity: cog?.setBrainActivity,
    memoryWrites: cog?.memoryWrites,
    flashMemoryWrite: cog?.flashMemoryWrite,
    pulseMemory: cog?.pulseMemory,

    // ── Agent Store ───────────────────────────────────
    agents: agent?.agents ?? [],
    setAgents: agent?.setAgents,
    upsertAgent: agent?.upsertAgent,
    getAgent: agent?.getAgent,
    getActiveAgents: agent?.getActiveAgents,

    // ── Task Store ────────────────────────────────────
    chatMessages: task?.chatMessages,
    addChatMessage: task?.addChatMessage,
    updateLastAiMessage: task?.updateLastAiMessage,
    upsertTaskProgress: task?.upsertTaskProgress,
    isTyping: task?.isTyping,
    setTyping: task?.setTyping,
    executionSteps: task?.executionSteps,
    addExecutionStep: task?.addExecutionStep,
    clearExecutionSteps: task?.clearExecutionSteps,
    executionLogs: task?.executionLogs,
    addExecutionLog: task?.addExecutionLog,
    setExecutionSnapshot: task?.setExecutionSnapshot,
    workflowState: task?.workflowState,
    setWorkflowSnapshot: task?.setWorkflowSnapshot,
    upsertWorkflowRun: task?.upsertWorkflowRun,

    // ── Economy Store ─────────────────────────────────
    revenue: econ?.revenue,
    setRevenue: econ?.setRevenue,
    monetizationPipelines: econ?.monetizationPipelines,
    setPipeline: econ?.setPipeline,
    activityFeed: econ?.activityFeed,
    addActivityItem: econ?.addActivityItem,
    setActivitySnapshot: econ?.setActivitySnapshot,

    // ── Security Store ────────────────────────────────
    securityStatus: sec?.securityStatus,
    setSecurityStatus: sec?.setSecurityStatus,
    threatHistory: sec?.threatHistory,
    addThreat: sec?.addThreat,
    autonomyStatus: sec?.autonomyStatus,
    setAutonomyStatus: sec?.setAutonomyStatus,
    getThreatColor: sec?.getThreatColor,
    isCritical: sec?.isCritical,

    // ── Event Feed Store ──────────────────────────────
    events: evt?.events,
    addEvent: evt?.addEvent,
    setEventSnapshot: evt?.setEventSnapshot,
    getEventsByCategory: evt?.getEventsByCategory,
    getRecentEvents: evt?.getRecentEvents,

    // ── Brain Store (unchanged) ───────────────────────
    nodes: brain?.nodes,
    links: brain?.links,
    stats: brain?.stats,
    updatedAt: brain?.updatedAt,
    selectedNodeId: brain?.selectedNodeId,
    setSelectedNodeId: brain?.setSelectedNodeId,
    setGraph: brain?.setGraph,
    addNode: brain?.addNode,
    addLink: brain?.addLink,
    addNodesAndLinks: brain?.addNodesAndLinks,
    addFromPrompt: brain?.addFromPrompt,

    // ── Legacy/Composite properties ───────────────────
    objectivePanels: {
      money_mode: econ?.monetizationPipelines?.content_publish_track || {},
      ascend_forge: { active: false, status: 'inactive', plan: [], results: [] },
    },
    setObjectivePanel: (system, payload) => econ?.setPipeline(system, payload),
    nnStatus: {
      available: true,
      active: true,
      mode: 'INITIALIZING',
      confidence: 0,
      device: 'cpu',
    },
    setNnStatus: NOOP,
    memoryTree: NOOP_MEMORY_TREE,
    setMemoryTree: NOOP,
    doctorStatus: { available: false, grade: null, overall_score: 0 },
    setDoctorStatus: NOOP,
    selfImprovement: { active: false, queue_depth: 0, pass_rate: 0 },
    setSelfImprovement: NOOP,
    productMetrics: { mode: {}, tasks: {}, revenue: {}, value: {} },
    setProductMetrics: NOOP,
    automationStatus: '',
    setAutomationStatus: NOOP,
    promptTraces: legacy?.promptTraces || [],
    inspectorEnabled: legacy?.inspectorEnabled ?? true,
    addPromptTrace: legacy?.addPromptTrace || NOOP,
    setPromptTraces: legacy?.setPromptTraces || NOOP,
    setInspectorEnabled: legacy?.setInspectorEnabled || NOOP,
    forgeQueue: legacy?.forgeQueue || [],
    setForgeQueue: legacy?.setForgeQueue || NOOP,
    upsertForgeItem: legacy?.upsertForgeItem || NOOP,
    observability: legacy?.observability || { system_health: {}, metrics: {}, events: [] },
    setObservability: legacy?.setObservability || NOOP,

    // Legacy auth + identity
    user: legacy?.user ?? null,
    login: legacy?.login || NOOP,
    logout: legacy?.logout || NOOP,
    identity: legacy?.identity ?? null,
    setIdentity: legacy?.setIdentity || NOOP,
    hermesGoal: legacy?.hermesGoal || '',
    setHermesGoal: legacy?.setHermesGoal || NOOP,
    alphaArchive: legacy?.alphaArchive || [],
    addAlphaEntry: legacy?.addAlphaEntry || NOOP,
    automationRules: legacy?.automationRules || [],
    addAutomationRule: legacy?.addAutomationRule || NOOP,
    removeAutomationRule: legacy?.removeAutomationRule || NOOP,
    contextPanel: legacy?.contextPanel ?? null,
    setContextPanel: legacy?.setContextPanel || NOOP,
    closeContextPanel: legacy?.closeContextPanel || NOOP,
  }
}

function getCompositeState() {
  return buildCompositeState(
    useSystemStore.getState(),
    useCognitiveStore.getState(),
    useAgentStore.getState(),
    useTaskStore.getState(),
    useEconomyStore.getState(),
    useSecurityStore.getState(),
    useEventFeedStore.getState(),
    useBrainStore.getState(),
    useLegacyAppStore.getState(),
  )
}

const DOMAIN_KEY_TARGETS = new Map()
for (const key of [
  'appState', 'pythonBackendReady', 'activeSection', 'sidebarCollapsed', 'ws',
  'wsConnected', 'heartbeatLogs', 'systemStatus', 'systemHealth', 'errorMessage',
  'debugMode', 'selectedEventId', 'updateStatus', 'backendStatus',
]) DOMAIN_KEY_TARGETS.set(key, useSystemStore)
for (const key of [
  'brainState', 'reasoningSteps', 'modelCalls', 'avatarState', 'brainInsights',
  'brainActivity', 'memoryWrites', 'freshness_ms',
]) DOMAIN_KEY_TARGETS.set(key, useCognitiveStore)
for (const key of ['agents']) DOMAIN_KEY_TARGETS.set(key, useAgentStore)
for (const key of [
  'chatMessages', 'isTyping', 'executionSteps', 'executionLogs', 'workflowState',
]) DOMAIN_KEY_TARGETS.set(key, useTaskStore)
for (const key of ['revenue', 'monetizationPipelines', 'activityFeed']) DOMAIN_KEY_TARGETS.set(key, useEconomyStore)
for (const key of ['securityStatus', 'threatHistory', 'autonomyStatus']) DOMAIN_KEY_TARGETS.set(key, useSecurityStore)
for (const key of ['events']) DOMAIN_KEY_TARGETS.set(key, useEventFeedStore)
for (const key of ['nodes', 'links', 'stats', 'updatedAt', 'selectedNodeId']) DOMAIN_KEY_TARGETS.set(key, useBrainStore)

useAppStore.getState = getCompositeState
useAppStore.setState = (partial, replace = false) => {
  const patch = typeof partial === 'function' ? partial(getCompositeState()) : partial
  if (!patch || typeof patch !== 'object') return

  const grouped = new Map()
  const legacyPatch = {}
  for (const [key, value] of Object.entries(patch)) {
    const store = DOMAIN_KEY_TARGETS.get(key)
    if (!store) {
      legacyPatch[key] = value
      continue
    }
    const next = grouped.get(store) || {}
    next[key] = value
    grouped.set(store, next)
  }
  for (const [store, values] of grouped.entries()) store.setState(values, replace)
  if (Object.keys(legacyPatch).length) useLegacyAppStore.setState(legacyPatch, replace)
}
useAppStore.subscribe = (selector, listener, options = {}) => {
  const hasSelector = typeof listener === 'function'
  const select = hasSelector ? selector : identity
  const cb = hasSelector ? listener : selector
  let current = select(getCompositeState())

  if (options?.fireImmediately && hasSelector) cb(current, current)

  const emit = () => {
    const next = select(getCompositeState())
    if (Object.is(next, current)) return
    const prev = current
    current = next
    cb(next, prev)
  }

  const unsubs = [
    useSystemStore.subscribe(emit),
    useCognitiveStore.subscribe(emit),
    useAgentStore.subscribe(emit),
    useTaskStore.subscribe(emit),
    useEconomyStore.subscribe(emit),
    useSecurityStore.subscribe(emit),
    useEventFeedStore.subscribe(emit),
    useBrainStore.subscribe(emit),
    useLegacyAppStore.subscribe(emit),
  ]
  return () => unsubs.forEach(unsub => unsub())
}

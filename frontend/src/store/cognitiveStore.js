import { create } from 'zustand'

/**
 * Avatar state machine (9-state derived from reactive triggers):
 * idle → thinking → reasoning → recalling → integrating → synthesizing
 *     → deciding → executing → reflecting → idle
 */
const AVATAR_STATES = {
  idle: 'idle',
  thinking: 'thinking',
  reasoning: 'reasoning',
  recalling: 'recalling',
  integrating: 'integrating',
  synthesizing: 'synthesizing',
  deciding: 'deciding',
  executing: 'executing',
  reflecting: 'reflecting',
}

// ── localStorage hydrate/persist (metrics only — not event histories or memoryWrites) ──
const SNAPSHOT_KEY = 'nexus:snapshot:cognitive'
// Brain snapshots are metric-shaped; we don't persist raw reasoningSteps / modelCalls arrays.
const PERSIST_FIELDS = ['brainState', 'brainInsights', 'brainActivity']
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

export const useCognitiveStore = create((set, get) => ({
  // Brain state
  brainState: HYDRATED.brainState || {
    status: 'active', active: true, available: true,
    memory_size: 0, last_update: null, recent_decisions: [],
  },
  setBrainState: (state) => { set({ brainState: state, freshness_ms: Date.now() }); schedulePersist(get) },

  // Reasoning trace
  reasoningSteps: [],
  appendReasoningStep: (step) => set((state) => ({
    reasoningSteps: [...state.reasoningSteps, step].slice(-50),
  })),
  clearReasoningSteps: () => set({ reasoningSteps: [] }),

  // Model inference calls
  modelCalls: [],
  recordModelCall: (call) => set((state) => ({
    modelCalls: [...state.modelCalls, call].slice(-100),
  })),
  clearModelCalls: () => set({ modelCalls: [] }),

  // Avatar state
  avatarState: AVATAR_STATES.idle,
  setAvatarState: (state) => set({ avatarState: state }),
  isAvatarActive: () => get().avatarState !== AVATAR_STATES.idle,

  // Brain insights — metric snapshot, persisted
  brainInsights: HYDRATED.brainInsights || {
    active: true, learned_strategies: [], task_patterns: [],
    recent_improvements: [], performance_metrics: {}, decisions: [], updated_at: null,
  },
  setBrainInsights: (insights) => { set({ brainInsights: insights, freshness_ms: Date.now() }); schedulePersist(get) },

  // Brain activity — metric snapshot, persisted
  brainActivity: HYDRATED.brainActivity || {
    status: 'active', memory_size: 0, last_update: null,
    recent_decisions: [], items: [],
  },
  setBrainActivity: (activity) => { set({ brainActivity: activity, freshness_ms: Date.now() }); schedulePersist(get) },

  // Memory operations
  memoryWrites: [],
  flashMemoryWrite: (write) => set((state) => ({
    memoryWrites: [...state.memoryWrites, { ...write, ts: Date.now() }].slice(-20),
  })),
  pulseMemory: (memoryIds) => set((state) => ({
    memoryWrites: state.memoryWrites.map(w =>
      memoryIds.includes(w.id) ? { ...w, accessed_at: Date.now() } : w
    ),
  })),

  // Freshness — 0 = cold-boot, otherwise ms timestamp of last metric tick
  freshness_ms: 0,

  // ── Autonomous research loop ────────────────────────────────────────────
  // contextCheck is non-null when the system needs the user to choose
  // whether to research before executing a low-context task.
  contextCheck: null,
  setContextCheck: (payload) => set({ contextCheck: payload }),
  clearContextCheck: () => set({ contextCheck: null }),

  // researchSession reflects in-flight research progress.
  researchSession: null,
  setResearchSession: (session) => set({ researchSession: session }),
  clearResearchSession: () => set({ researchSession: null }),

  // researchHistory: last 20 completed sessions (for the activity panel).
  researchHistory: [],
  appendResearchSession: (session) => set((state) => ({
    researchHistory: [{ ...session, ts: Date.now() }, ...state.researchHistory].slice(0, 20),
  })),

  // Pipeline phase trace — updated on every cognition:pipeline WS event.
  phases: {},
  setPipelinePhases: (phases) => set({ phases }),
}))

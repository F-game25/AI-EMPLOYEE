import { create } from 'zustand'

const MAX_EXECUTION_LOGS = 100

// ── localStorage hydrate/persist (metric summaries only — never chat messages or full logs) ──
const SNAPSHOT_KEY = 'nexus:snapshot:task'
// We intentionally do NOT persist chatMessages, executionLogs, executionSteps, or workflowState.runs —
// those are conversation/event histories per the §2.4 constraint.
const PERSIST_FIELDS = ['opsSummary']
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

const DEFAULT_OPS_SUMMARY = {
  active_tasks: 0, queued_tasks: 0, success_rate: 0, avg_exec_time: 0,
}

export const useTaskStore = create((set, get) => ({
  // Chat messages (transient — never persisted)
  chatMessages: [],
  lastAiMessageIndex: -1,
  addChatMessage: (msg) => set((state) => ({
    chatMessages: msg.turn_id
      ? [
          ...state.chatMessages.filter(existing => existing.turn_id !== msg.turn_id),
          msg,
        ]
      : [...state.chatMessages, msg],
    lastAiMessageIndex: msg.role === 'ai' ? state.chatMessages.length : state.lastAiMessageIndex,
  })),
  upsertTurnMessage: (turn) => set((state) => {
    const turnId = turn?.turn_id || turn?.turnId
    if (!turnId) return state
    const content = turn.assistant_reply || turn.reply || turn.content || turn.response || ''
    const nextMsg = {
      role: 'ai',
      type: 'turn',
      turn_id: turnId,
      taskId: turn.task_id || turn.taskId,
      status: turn.status || 'running',
      content,
      raw_reply: turn.raw_reply || '',
      actions: Array.isArray(turn.actions) ? turn.actions : [],
      proof: Array.isArray(turn.proof) ? turn.proof : [],
      artifacts: Array.isArray(turn.artifacts) ? turn.artifacts : [],
      approvals: Array.isArray(turn.approvals) ? turn.approvals : [],
      degraded: turn.degraded === true,
      errors: Array.isArray(turn.errors) ? turn.errors : [],
      source: turn.source || null,
      trace_id: turn.trace_id || null,
      ts: turn.ts || Date.now(),
    }
    const idx = state.chatMessages.findIndex(m => m.turn_id === turnId)
    if (idx !== -1) {
      const msgs = [...state.chatMessages]
      msgs[idx] = { ...msgs[idx], ...nextMsg, ts: msgs[idx].ts || nextMsg.ts }
      return {
        chatMessages: msgs,
        lastAiMessageIndex: nextMsg.status === 'completed' || nextMsg.status === 'failed' ? idx : state.lastAiMessageIndex,
      }
    }
    return {
      chatMessages: [...state.chatMessages, nextMsg],
      lastAiMessageIndex: state.chatMessages.length,
    }
  }),
  updateLastAiMessage: (text) => set((state) => {
    let idx = state.lastAiMessageIndex
    if (idx === -1) {
      for (let i = state.chatMessages.length - 1; i >= 0; i--) {
        if (state.chatMessages[i].role === 'ai') { idx = i; break }
      }
    }
    if (idx === -1) return state
    const msgs = [...state.chatMessages]
    if (msgs[idx]?.content === text) return state
    msgs[idx] = { ...msgs[idx], content: text }
    return { chatMessages: msgs, lastAiMessageIndex: idx }
  }),

  // Task progress (in-chat task cards)
  upsertTaskProgress: (update) => set((state) => {
    const msgs = [...state.chatMessages]
    const idx = msgs.findIndex(m => m.type === 'task_progress' && m.taskId === update.taskId)
    if (idx !== -1) {
      msgs[idx] = { ...msgs[idx], ...update }
      return { chatMessages: msgs }
    }
    return { chatMessages: [...msgs, { role: 'ai', type: 'task_progress', ...update }] }
  }),

  // Typing indicator
  isTyping: false,
  setTyping: (v) => set({ isTyping: v }),

  // Execution steps
  executionSteps: [],
  addExecutionStep: (step) => set((state) => ({
    executionSteps: [...state.executionSteps.slice(-8), step],
  })),
  clearExecutionSteps: () => set({ executionSteps: [] }),

  // Execution logs
  executionLogs: [],
  addExecutionLog: (log) => set((state) => ({
    executionLogs: [log, ...state.executionLogs].slice(0, MAX_EXECUTION_LOGS),
  })),
  setExecutionSnapshot: (logs) => set({
    executionLogs: Array.isArray(logs) ? logs.slice(0, MAX_EXECUTION_LOGS) : [],
  }),

  // Workflow state
  workflowState: { active_run: null, runs: [] },
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

  // Ops summary — metric snapshot, persisted for offline-mode last-known-values
  opsSummary: { ...DEFAULT_OPS_SUMMARY, ...(HYDRATED.opsSummary || {}) },
  setOpsSummary: (partial) => {
    set(state => ({
      opsSummary: { ...state.opsSummary, ...(partial || {}) },
      freshness_ms: Date.now(),
    }))
    schedulePersist(get)
  },

  // Freshness — 0 = cold-boot, otherwise ms timestamp of last metric tick
  freshness_ms: 0,
}))

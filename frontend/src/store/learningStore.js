import { create } from 'zustand'

const MAX_RECENT_MEMORIES = 25
const MAX_LOG_PER_SESSION = 80

export const useLearningStore = create((set, get) => ({
  sessions: {},                // { [session_id]: { id, topic, depth, status, progress, log: [], started_at, completed_at? } }
  recentMemories: [],          // [{ id, claim, topic, confidence, ts }, ...]
  pendingReviewCount: 0,

  startSession: (session_id, topic, depth) => set(state => ({
    sessions: {
      ...state.sessions,
      [session_id]: {
        id: session_id, topic, depth,
        status: 'running', progress: 0, log: [],
        started_at: Date.now(),
      },
    },
  })),

  appendSessionLog: (session_id, entry) => set(state => {
    const s = state.sessions[session_id]
    if (!s) return state
    return {
      sessions: {
        ...state.sessions,
        [session_id]: {
          ...s,
          log: [...s.log, entry].slice(-MAX_LOG_PER_SESSION),
          progress: entry.progress ?? s.progress,
        },
      },
    }
  }),

  completeSession: (session_id, result = {}) => set(state => {
    const s = state.sessions[session_id]
    if (!s) return state
    return {
      sessions: {
        ...state.sessions,
        [session_id]: { ...s, status: 'completed', progress: 1.0, completed_at: Date.now(), result },
      },
    }
  }),

  failSession: (session_id, error) => set(state => {
    const s = state.sessions[session_id]
    if (!s) return state
    return {
      sessions: {
        ...state.sessions,
        [session_id]: { ...s, status: 'failed', error, completed_at: Date.now() },
      },
    }
  }),

  addRecentMemory: (memory) => set(state => ({
    recentMemories: [memory, ...state.recentMemories].slice(0, MAX_RECENT_MEMORIES),
  })),

  setPendingReviewCount: (n) => set({ pendingReviewCount: n }),
  bumpPendingReviewCount: () => set(state => ({ pendingReviewCount: state.pendingReviewCount + 1 })),
  decrementPendingReviewCount: () => set(state => ({ pendingReviewCount: Math.max(0, state.pendingReviewCount - 1) })),

  reset: () => set({ sessions: {}, recentMemories: [], pendingReviewCount: 0 }),

  // Computed selector
  getActiveSessionsCount: () => {
    const sessions = get().sessions
    return Object.values(sessions).filter(s => s.status === 'running').length
  },
}))

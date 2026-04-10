import { create } from 'zustand'

export const useAppStore = create((set) => ({
  // State machine
  appState: 'boot', // boot | connecting | login | dashboard | error
  setAppState: (s) => set({ appState: s }),

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
  systemStatus: { cpu: 0, memory: 0, uptime: 0, connections: 0 },
  setSystemStatus: (s) => set({ systemStatus: s }),

  // Neural Network status
  nnStatus: {
    available: false,
    active: false,
    mode: 'OFFLINE',
    learn_step: 0,
    buffer_size: 0,
    last_loss: null,
    confidence: 0,
    device: 'cpu',
    total_actions: 8,
    experiences: 0,
    bg_running: false,
    recent_outputs: [],
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

  // Error
  errorMessage: null,
  setError: (msg) => set({ errorMessage: msg, appState: 'error' }),
}))

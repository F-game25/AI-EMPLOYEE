import { create } from 'zustand'

export const useAppStore = create((set, get) => ({
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

  // System status
  systemStatus: { cpu: 0, memory: 0, uptime: 0, connections: 0 },
  setSystemStatus: (s) => set({ systemStatus: s }),

  // Error
  errorMessage: null,
  setError: (msg) => set({ errorMessage: msg, appState: 'error' }),
}))

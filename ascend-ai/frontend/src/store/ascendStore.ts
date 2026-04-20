import { create } from 'zustand'
import type { ChatMsg } from '../components/ChatWindow'

interface Agent {
  name: string
  status: string
  pid: number | null
  uptime?: number | null
  mock?: boolean
}

interface SystemStats {
  cpu_percent: number
  ram_used_gb: number
  ram_total_gb: number
  gpu_percent: number
  temp_celsius: number
  mock?: boolean
}

export interface LLMStatus {
  provider: string
  model: string | null
  ollama_available: boolean
}

export interface ActiveStream {
  context: string
  content: string
  fallback: boolean
}

interface AscendState {
  // Connection
  wsConnected: boolean
  setWsConnected: (v: boolean) => void
  mockMode: boolean
  setMockMode: (v: boolean) => void

  // Agents
  agents: Agent[]
  setAgents: (a: Agent[]) => void

  // System stats
  systemStats: SystemStats
  setSystemStats: (s: SystemStats) => void

  // LLM provider status
  llmStatus: LLMStatus
  setLlmStatus: (s: LLMStatus) => void

  // Streaming chat state (shared across all contexts)
  activeStream: ActiveStream | null
  startStream: (context: string, fallback: boolean) => void
  appendStream: (content: string) => void
  clearStream: () => void

  // Fallback toast (shown once when Anthropic fallback kicks in)
  showFallbackToast: boolean
  setShowFallbackToast: (v: boolean) => void
  fallbackNotified: boolean
  setFallbackNotified: (v: boolean) => void

  // Main chat
  mainChat: ChatMsg[]
  addMainChat: (m: ChatMsg) => void
  clearMainChat: () => void

  // Doctor chat
  doctorChat: ChatMsg[]
  addDoctorChat: (m: ChatMsg) => void

  // Forge chat
  forgeChat: ChatMsg[]
  addForgeChat: (m: ChatMsg) => void

  // Money chat
  moneyChat: ChatMsg[]
  addMoneyChat: (m: ChatMsg) => void

  // Blacklight chat
  blacklightChat: ChatMsg[]
  addBlacklightChat: (m: ChatMsg) => void

  // Hermes chat
  hermesChat: ChatMsg[]
  addHermesChat: (m: ChatMsg) => void

  // Unified chat add — routes to the correct array by context name
  addChatToContext: (context: string, msg: ChatMsg) => void

  // Forge
  forgeMode: string
  setForgeMode: (m: string) => void
  forgeLines: string[]
  addForgeLine: (l: string) => void

  // Money
  moneyMode: string
  setMoneyMode: (m: string) => void
  moneyLines: string[]
  addMoneyLine: (l: string) => void
  moneyRevenue: number
  setMoneyRevenue: (r: number) => void

  // Blacklight
  blacklightActive: boolean
  setBlacklightActive: (v: boolean) => void
  blacklightLines: string[]
  addBlacklightLine: (l: string) => void

  // Live feedback charts
  chartData: { ts: number; tokens: number; latency: number; activity: number }[]
  addChartPoint: (p: { tokens: number; latency: number; activity: number }) => void

  // Feed lines
  forgeFeed: string[]
  moneyFeed: string[]
  blacklightFeed: string[]
  addFeedLine: (channel: 'forge' | 'money' | 'blacklight', line: string) => void
}

export const useStore = create<AscendState>((set, get) => ({
  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),
  mockMode: false,
  setMockMode: (v) => set({ mockMode: v }),

  agents: [],
  setAgents: (a) => set({ agents: a }),

  systemStats: { cpu_percent: 0, ram_used_gb: 0, ram_total_gb: 0, gpu_percent: 0, temp_celsius: 0 },
  setSystemStats: (s) => set({ systemStats: s }),

  llmStatus: { provider: 'unknown', model: null, ollama_available: false },
  setLlmStatus: (s) => set({ llmStatus: s }),

  activeStream: null,
  startStream: (context, fallback) =>
    set({ activeStream: { context, content: '', fallback } }),
  appendStream: (content) =>
    set((s) =>
      s.activeStream
        ? { activeStream: { ...s.activeStream, content: s.activeStream.content + content } }
        : {}
    ),
  clearStream: () => set({ activeStream: null }),

  showFallbackToast: false,
  setShowFallbackToast: (v) => set({ showFallbackToast: v }),
  fallbackNotified: false,
  setFallbackNotified: (v) => set({ fallbackNotified: v }),

  mainChat: [{ role: 'system', content: 'Welcome to ASCEND AI. Type a message to begin.', tag: 'SYSTEM' }],
  addMainChat: (m) => set((s) => ({ mainChat: [...s.mainChat, m] })),
  clearMainChat: () => set({ mainChat: [] }),

  doctorChat: [{ role: 'system', content: 'Doctor mode active. Ask about system health or run diagnostics.', tag: 'DOCTOR' }],
  addDoctorChat: (m) => set((s) => ({ doctorChat: [...s.doctorChat, m] })),

  forgeChat: [{ role: 'system', content: 'Forge AI active. Describe what to improve in the ASCEND codebase.', tag: 'FORGE' }],
  addForgeChat: (m) => set((s) => ({ forgeChat: [...s.forgeChat, m] })),

  moneyChat: [{ role: 'system', content: 'Money Mode AI active. Assign revenue tasks here.', tag: 'MONEY' }],
  addMoneyChat: (m) => set((s) => ({ moneyChat: [...s.moneyChat, m] })),

  blacklightChat: [{ role: 'system', content: 'Blacklight Security AI active. Monitoring all connections.', tag: 'BLACKLIGHT' }],
  addBlacklightChat: (m) => set((s) => ({ blacklightChat: [...s.blacklightChat, m] })),

  hermesChat: [{ role: 'system', content: 'Hermes online. I coordinate all agents. How can I help?', tag: 'HERMES' }],
  addHermesChat: (m) => set((s) => ({ hermesChat: [...s.hermesChat, m] })),

  addChatToContext: (context, msg) => {
    const s = get()
    switch (context) {
      case 'main':       s.addMainChat(msg); break
      case 'forge':      s.addForgeChat(msg); break
      case 'money':      s.addMoneyChat(msg); break
      case 'blacklight': s.addBlacklightChat(msg); break
      case 'hermes':     s.addHermesChat(msg); break
      case 'doctor':     s.addDoctorChat(msg); break
      default:           s.addMainChat(msg); break
    }
  },

  forgeMode: 'off',
  setForgeMode: (m) => set({ forgeMode: m }),
  forgeLines: [],
  addForgeLine: (l) => set((s) => ({ forgeLines: [...s.forgeLines.slice(-200), l] })),

  moneyMode: 'off',
  setMoneyMode: (m) => set({ moneyMode: m }),
  moneyLines: [],
  addMoneyLine: (l) => set((s) => ({ moneyLines: [...s.moneyLines.slice(-200), l] })),
  moneyRevenue: 0,
  setMoneyRevenue: (r) => set({ moneyRevenue: r }),

  blacklightActive: false,
  setBlacklightActive: (v) => set({ blacklightActive: v }),
  blacklightLines: [],
  addBlacklightLine: (l) => set((s) => ({ blacklightLines: [...s.blacklightLines.slice(-200), l] })),

  chartData: [],
  addChartPoint: (p) => set((s) => {
    const now = Date.now()
    const cutoff = now - 60000
    const next = [...s.chartData.filter((d) => d.ts > cutoff), { ts: now, ...p }]
    return { chartData: next }
  }),

  forgeFeed: [],
  moneyFeed: [],
  blacklightFeed: [],
  addFeedLine: (channel, line) => set((s) => {
    const key = channel + 'Feed' as 'forgeFeed' | 'moneyFeed' | 'blacklightFeed'
    return { [key]: [line, ...s[key]].slice(0, 100) }
  }),
}))

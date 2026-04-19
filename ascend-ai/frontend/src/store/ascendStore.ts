import { create } from 'zustand'

interface ChatMessage {
  role: 'user' | 'ai' | 'system'
  content: string
  tag?: string
}

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

  // Main chat
  mainChat: ChatMessage[]
  addMainChat: (m: ChatMessage) => void
  clearMainChat: () => void

  // Doctor chat
  doctorChat: ChatMessage[]
  addDoctorChat: (m: ChatMessage) => void

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

export const useStore = create<AscendState>((set) => ({
  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),
  mockMode: true,
  setMockMode: (v) => set({ mockMode: v }),

  agents: [],
  setAgents: (a) => set({ agents: a }),

  systemStats: { cpu_percent: 0, ram_used_gb: 0, ram_total_gb: 0, gpu_percent: 0, temp_celsius: 0 },
  setSystemStats: (s) => set({ systemStats: s }),

  mainChat: [{ role: 'system', content: 'Welcome to ASCEND AI. Type a message to begin.', tag: 'SYSTEM' }],
  addMainChat: (m) => set((s) => ({ mainChat: [...s.mainChat, m] })),
  clearMainChat: () => set({ mainChat: [] }),

  doctorChat: [{ role: 'system', content: 'Doctor mode active. Ask about system health or run diagnostics.', tag: 'DOCTOR' }],
  addDoctorChat: (m) => set((s) => ({ doctorChat: [...s.doctorChat, m] })),

  forgeMode: 'off',
  setForgeMode: (m) => set({ forgeMode: m }),
  forgeLines: ['[FORGE STANDBY]', 'Awaiting improvement task...'],
  addForgeLine: (l) => set((s) => ({ forgeLines: [...s.forgeLines.slice(-200), l] })),

  moneyMode: 'off',
  setMoneyMode: (m) => set({ moneyMode: m }),
  moneyLines: ['[MONEY MODE ACTIVE]', 'Scanning business opportunities...', 'Revenue tracking: €0 today | €0 this week', 'Awaiting task input...'],
  addMoneyLine: (l) => set((s) => ({ moneyLines: [...s.moneyLines.slice(-200), l] })),
  moneyRevenue: 0,
  setMoneyRevenue: (r) => set({ moneyRevenue: r }),

  blacklightActive: false,
  setBlacklightActive: (v) => set({ blacklightActive: v }),
  blacklightLines: ['[BLACKLIGHT MODE]', 'Security monitoring standby', 'All connections encrypted', 'Awaiting scan...'],
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

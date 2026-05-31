import { create } from 'zustand'
import { api } from '../api/secureClient'

interface Agent {
  id: string; name: string; status: string; role: string; last_active?: string
}
interface Task {
  id: string; title: string; status: string; agent: string; progress: number; elapsed_ms: number
}
interface SystemHealth {
  cpu_percent: number; memory_percent: number; disk_percent: number
  agents_active: number; tasks_total: number; uptime_ms: number
}

interface DashboardState {
  systemHealth:  SystemHealth | null
  agents:        Agent[]
  activeTasks:   Task[]
  revenueStats:  { mtd: number; daily: number; projection: number } | null
  threatScore:   number
  pendingHITL:   number
  lastTick:      number
  loading:       boolean

  refresh:      () => Promise<void>
  updateFromWs: (type: string, data: unknown) => void
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  systemHealth:  null,
  agents:        [],
  activeTasks:   [],
  revenueStats:  null,
  threatScore:   0,
  pendingHITL:   0,
  lastTick:      0,
  loading:       false,

  refresh: async () => {
    set({ loading: true })
    try {
      const [health, agentsRes, tasksRes, revenue, security] = await Promise.allSettled([
        api.getSystemHealth(),
        api.getAgents(),
        api.getActiveTasks(),
        api.getRevenueStats(),
        api.getSecurityThreats(),
      ])

      set({
        systemHealth: health.status  === 'fulfilled' ? (health.value as unknown) as SystemHealth : null,
        agents:       agentsRes.status === 'fulfilled' ? ((agentsRes.value as { agents: Agent[] }).agents || []) : [],
        activeTasks:  tasksRes.status  === 'fulfilled' ? ((tasksRes.value  as { tasks:  Task[]  }).tasks  || []) : [],
        revenueStats: revenue.status   === 'fulfilled' ? revenue.value   as { mtd: number; daily: number; projection: number } : null,
        threatScore:  security.status  === 'fulfilled' ? ((security.value as { score?: number }).score || 0) : 0,
        lastTick:     Date.now(),
        loading:      false,
      })
    } catch {
      set({ loading: false })
    }
  },

  updateFromWs: (type, data) => {
    const d = data as Record<string, unknown>
    switch (type) {
      case 'system:tick':
        set({ lastTick: Date.now(), systemHealth: (data as unknown) as SystemHealth })
        break
      case 'agent:update': {
        const agent = d as unknown as Agent
        set(s => ({ agents: s.agents.map(a => a.id === agent.id ? { ...a, ...agent } : a) }))
        break
      }
      case 'task:update': {
        const task = d as unknown as Task
        set(s => ({ activeTasks: s.activeTasks.map(t => t.id === task.id ? { ...t, ...task } : t) }))
        break
      }
      case 'revenue:event':
        set(s => ({
          revenueStats: s.revenueStats
            ? { ...s.revenueStats, mtd: s.revenueStats.mtd + ((d.amount as number) || 0) }
            : s.revenueStats
        }))
        break
      case 'security:breach':
        set({ threatScore: 100 })
        break
    }
  },
}))

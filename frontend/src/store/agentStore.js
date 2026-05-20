import { create } from 'zustand'
import { subscribeWithSelector } from 'zustand/middleware'

const HEALTH_MAP = {
  healthy: 90,
  degraded: 55,
  warning: 55,
  warn: 55,
  error: 20,
  critical: 10,
  idle: 40,
  unknown: 50,
}

function normalizeAgent(a) {
  return {
    ...a,
    status: a.status || a.state || 'idle',
    health: typeof a.health === 'number' ? a.health : (HEALTH_MAP[a.health] ?? 50),
    task: a.task || a.currentTask || null,
  }
}

export const useAgentStore = create(subscribeWithSelector((set, get) => ({
  // Agents list
  agents: [],
  setAgents: (agents) => set({
    agents: Array.isArray(agents) ? agents.map(normalizeAgent) : [],
  }),

  // Upsert single agent (from agent:update events)
  upsertAgent: (agent) => set((state) => {
    const normalized = normalizeAgent(agent)
    const idx = state.agents.findIndex(a => a.id === normalized.id)
    if (idx >= 0) {
      const next = [...state.agents]
      next[idx] = { ...next[idx], ...normalized }
      return { agents: next }
    }
    return { agents: [...state.agents, normalized] }
  }),

  // Get agent by ID
  getAgent: (id) => get().agents.find(a => a.id === id),

  // Selector: active agents only
  getActiveAgents: () => get().agents.filter(a => a.status !== 'idle' && a.status !== 'unknown'),
})))

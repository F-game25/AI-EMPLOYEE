import { create } from 'zustand'

export const useSecurityStore = create((set, get) => ({
  // Security status (from Blacklight)
  securityStatus: {
    threat_score: 0,
    mode: 'NORMAL', // NORMAL | ALERT | CRITICAL | LOCKDOWN | OFFLINE
    active_threats: [],
    agents_paused: false,
    forge_disabled: false,
    updated_at: null,
  },
  setSecurityStatus: (patch) => set((state) => ({
    securityStatus: { ...state.securityStatus, ...patch },
  })),

  // Threat history
  threatHistory: [],
  addThreat: (threat) => set((state) => ({
    threatHistory: [threat, ...state.threatHistory].slice(0, 100),
  })),

  // Autonomy state (daemon + queue + mode)
  autonomyStatus: {
    mode: {
      mode: 'OFF',
      active: false,
      auto: false,
      limited: false,
      paused: true,
      emergency_stopped: false,
      changed_at: null,
    },
    daemon: {
      running: false,
      started_at: null,
      cycles: 0,
      tasks_processed: 0,
      tasks_succeeded: 0,
      tasks_failed: 0,
      consecutive_errors: 0,
      last_cycle_at: null,
      last_task_id: null,
      current_task_id: null,
      cycle_interval_s: 2,
    },
    queue: { total: 0, active: 0, by_status: {} },
    data_source: 'initializing',
    updated_at: null,
  },
  setAutonomyStatus: (a) => set({ autonomyStatus: a }),

  // Computer-Use mode — master switch for the teammate driving a browser/desktop.
  computerUseStatus: { enabled: false, desktop_available: false, updated_at: null },
  setComputerUseStatus: (s) => set({ computerUseStatus: { ...get().computerUseStatus, ...s } }),

  // Derived: threat level color
  getThreatColor: () => {
    const score = get().securityStatus.threat_score
    if (score >= 75) return '#ef4444' // red
    if (score >= 50) return '#f97316' // orange
    if (score >= 30) return '#eab308' // yellow
    return '#22c55e' // green
  },

  // Derived: is system in critical state
  isCritical: () => {
    const { threat_score, mode } = get().securityStatus
    return threat_score >= 75 || mode === 'LOCKDOWN'
  },
}))

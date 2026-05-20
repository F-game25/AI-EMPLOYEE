import { create } from 'zustand'

const MAX_ACTIVITY_ITEMS = 50

// ── localStorage hydrate/persist (metrics only — not activityFeed) ──
const SNAPSHOT_KEY = 'nexus:snapshot:economy'
const PERSIST_FIELDS = ['revenue', 'monetizationPipelines']
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

const DEFAULT_REVENUE = { total: 0, daily: 0, rate_per_min: 0, currency: 'USD' }
const DEFAULT_PIPELINE = {
  active: false, status: 'inactive', current_objective: null,
  active_tasks: [], progress: 0, agents_used: [], performance: {}, result: null,
}

export const useEconomyStore = create((set, get) => ({
  // Revenue metrics — hydrated
  revenue: { ...DEFAULT_REVENUE, ...(HYDRATED.revenue || {}) },
  setRevenue: (r) => { set({ revenue: r, freshness_ms: Date.now() }); schedulePersist(get) },

  // Monetization pipelines — hydrated
  monetizationPipelines: HYDRATED.monetizationPipelines || {
    content_publish_track: { ...DEFAULT_PIPELINE },
    data_scrape_filter_store: { ...DEFAULT_PIPELINE },
    outreach_response_conversion: { ...DEFAULT_PIPELINE },
  },
  setPipeline: (pipelineKey, payload) => {
    set((state) => ({
      monetizationPipelines: {
        ...state.monetizationPipelines,
        [pipelineKey]: {
          ...(state.monetizationPipelines?.[pipelineKey] || {}),
          ...(payload || {}),
        },
      },
      freshness_ms: Date.now(),
    }))
    schedulePersist(get)
  },

  // Activity feed (transient — not persisted)
  activityFeed: [],
  addActivityItem: (item) => set((state) => ({
    activityFeed: [item, ...state.activityFeed].slice(0, MAX_ACTIVITY_ITEMS),
  })),
  setActivitySnapshot: (items) => set({
    activityFeed: Array.isArray(items) ? items.slice(0, MAX_ACTIVITY_ITEMS) : [],
  }),

  // Freshness — 0 = cold-boot, otherwise ms timestamp of last metric tick
  freshness_ms: 0,
}))

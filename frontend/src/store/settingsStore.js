import { create } from 'zustand'
import { eventBus, EVENTS } from '../utils/eventBus'

const STORAGE_KEY = 'ai_employee_settings'

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    // ignore
  }
  return null
}

function saveToStorage(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // ignore
  }
}

const DEFAULT_SETTINGS = {
  // API Keys
  apiKeys: {
    openai: '',
    anthropic: '',
    local_model_url: 'http://localhost:11434',
  },

  // Webhook configuration
  webhooks: {
    on_task_complete: '',
    on_agent_error: '',
    on_revenue_event: '',
  },

  // Tool connectors
  tools: {
    web_search: false,
    code_executor: false,
    file_system: false,
    email_sender: false,
    calendar: false,
  },

  // Environment configuration
  environment: {
    log_level: 'INFO',
    max_agents: 10,
    task_timeout_s: 300,
    autonomy_cycle_s: 2,
    offline_mode: false,
  },

  // Memory backend
  memory: {
    backend: 'json', // json | sqlite | remote
    remote_url: '',
    max_entities: 10000,
    ttl_days: 90,
  },

  // LLM provider preference
  llm: {
    provider: 'openai', // openai | anthropic | local
    model: 'gpt-4o',
    temperature: 0.7,
    max_tokens: 4096,
  },
}

export const useSettingsStore = create((set, get) => {
  const saved = loadFromStorage()
  const initial = saved
    ? {
        ...DEFAULT_SETTINGS,
        ...saved,
        apiKeys: { ...DEFAULT_SETTINGS.apiKeys, ...(saved.apiKeys || {}) },
        webhooks: { ...DEFAULT_SETTINGS.webhooks, ...(saved.webhooks || {}) },
        tools: { ...DEFAULT_SETTINGS.tools, ...(saved.tools || {}) },
        environment: { ...DEFAULT_SETTINGS.environment, ...(saved.environment || {}) },
        memory: { ...DEFAULT_SETTINGS.memory, ...(saved.memory || {}) },
        llm: { ...DEFAULT_SETTINGS.llm, ...(saved.llm || {}) },
      }
    : { ...DEFAULT_SETTINGS }

  return {
    ...initial,

    /** Update a top-level settings section (partial merge). */
    updateSection(section, values) {
      set((state) => {
        const next = { ...state, [section]: { ...state[section], ...values } }
        saveToStorage({
          apiKeys: next.apiKeys,
          webhooks: next.webhooks,
          tools: next.tools,
          environment: next.environment,
          memory: next.memory,
          llm: next.llm,
        })
        return next
      })
      eventBus.emit(EVENTS.SETTINGS_SAVED, { section, values })
    },

    /** Update a single API key. */
    setApiKey(provider, value) {
      set((state) => {
        const next = { ...state, apiKeys: { ...state.apiKeys, [provider]: value } }
        saveToStorage({
          apiKeys: next.apiKeys,
          webhooks: next.webhooks,
          tools: next.tools,
          environment: next.environment,
          memory: next.memory,
          llm: next.llm,
        })
        return next
      })
      eventBus.emit(EVENTS.API_KEY_UPDATED, { provider })
    },

    /** Reset all settings to defaults. */
    resetAll() {
      localStorage.removeItem(STORAGE_KEY)
      set({ ...DEFAULT_SETTINGS })
      eventBus.emit(EVENTS.SETTINGS_RESET, {})
    },

    /** Push settings to backend (best-effort). */
    async syncToBackend(apiUrl) {
      const state = get()
      try {
        await fetch(`${apiUrl}/api/settings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            environment: state.environment,
            llm: state.llm,
            memory: state.memory,
            tools: state.tools,
          }),
        })
      } catch {
        // Backend offline — settings remain locally persisted.
      }
    },
  }
})

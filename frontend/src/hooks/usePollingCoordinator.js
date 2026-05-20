import { useState, useEffect } from 'react'

// Singleton state — one poller for each endpoint, shared across all consumers
const _state = {
  systemHealth: null,
  integrations: [],
}
const _listeners = new Set()
let _healthTimer = null
let _integrationsTimer = null
let _started = false

function notify() {
  _listeners.forEach(fn => fn({ ..._state }))
}

async function fetchHealth() {
  try {
    const r = await fetch('/api/health', { signal: AbortSignal.timeout(5000) })
    if (r.ok) {
      _state.systemHealth = await r.json()
      notify()
    }
  } catch (_) {}
}

async function fetchIntegrations() {
  try {
    const r = await fetch('/api/integrations', { signal: AbortSignal.timeout(5000) })
    if (r.ok) {
      _state.integrations = await r.json()
      notify()
    }
  } catch (_) {}
}

function start() {
  if (_started) return
  _started = true

  // Initial fetch
  fetchHealth()
  fetchIntegrations()

  // Schedule recurring polls — pause when tab is hidden
  function scheduleHealth() {
    _healthTimer = setTimeout(async () => {
      if (!document.hidden) await fetchHealth()
      scheduleHealth()
    }, 30000)
  }
  function scheduleIntegrations() {
    _integrationsTimer = setTimeout(async () => {
      if (!document.hidden) await fetchIntegrations()
      scheduleIntegrations()
    }, 60000)
  }

  scheduleHealth()
  scheduleIntegrations()

  // Resume on tab focus
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      fetchHealth()
      fetchIntegrations()
    }
  })
}

export function usePollingCoordinator() {
  const [data, setData] = useState({ ..._state })

  useEffect(() => {
    start()
    _listeners.add(setData)
    return () => _listeners.delete(setData)
  }, [])

  return data
}

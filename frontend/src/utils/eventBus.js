/**
 * Global Event Bus — pub/sub for cross-module state updates.
 * Components subscribe to events and dispatch actions without
 * tight coupling between modules.
 */

const _listeners = {}

export const eventBus = {
  /** Subscribe to an event. Returns an unsubscribe function. */
  on(event, handler) {
    if (!_listeners[event]) _listeners[event] = []
    _listeners[event].push(handler)
    return () => eventBus.off(event, handler)
  },

  /** Unsubscribe a specific handler from an event. */
  off(event, handler) {
    if (!_listeners[event]) return
    _listeners[event] = _listeners[event].filter((h) => h !== handler)
  },

  /** Dispatch an event with optional payload. */
  emit(event, payload) {
    if (!_listeners[event]) return
    _listeners[event].forEach((handler) => {
      try {
        handler(payload)
      } catch (e) {
        console.error(`[eventBus] Error in handler for "${event}"`, e)
      }
    })
  },

  /** Remove all listeners (useful for testing / cleanup). */
  clear(event) {
    if (event) {
      delete _listeners[event]
    } else {
      Object.keys(_listeners).forEach((k) => delete _listeners[k])
    }
  },
}

// Standard event names — import these constants rather than raw strings.
export const EVENTS = {
  // Mode transitions
  MODE_ACTIVATED: 'mode:activated',
  MODE_DEACTIVATED: 'mode:deactivated',

  // Agent lifecycle
  AGENT_STARTED: 'agent:started',
  AGENT_STOPPED: 'agent:stopped',
  AGENT_ERROR: 'agent:error',
  AGENT_TASK_QUEUED: 'agent:task_queued',

  // Settings
  SETTINGS_SAVED: 'settings:saved',
  SETTINGS_RESET: 'settings:reset',
  API_KEY_UPDATED: 'settings:api_key_updated',

  // Navigation
  NAVIGATE_TO: 'nav:navigate_to',

  // System
  EMERGENCY_STOP: 'system:emergency_stop',
  BACKEND_OFFLINE: 'system:backend_offline',
  BACKEND_ONLINE: 'system:backend_online',
}

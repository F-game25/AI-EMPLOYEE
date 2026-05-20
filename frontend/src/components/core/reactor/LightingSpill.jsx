import { useEffect } from 'react'

const STATE_COLOR = {
  IDLE:      { color: '#22d3ee', intensity: 0.05 },
  LISTENING: { color: '#22d3ee', intensity: 0.12 },
  THINKING:  { color: '#a855f7', intensity: 0.15 },
  EXECUTING: { color: '#fbbf24', intensity: 0.22 },
  ERROR:     { color: '#ef4444', intensity: 0.30 },
}

/**
 * LightingSpill
 * Headless component — writes --spill-color and --spill-intensity to :root
 * so surrounding panels (.snode, sidebar widgets) can react via CSS.
 * The actual visual rules live in LightingSpill.css.
 */
export default function LightingSpill({ state = 'IDLE' }) {
  useEffect(() => {
    const root = document.documentElement
    const cfg = STATE_COLOR[state] || STATE_COLOR.IDLE
    root.style.setProperty('--spill-color', cfg.color)
    root.style.setProperty('--spill-intensity', String(cfg.intensity))
    // Intentionally no cleanup — keep last value so unmount transitions stay graceful
  }, [state])
  return null
}

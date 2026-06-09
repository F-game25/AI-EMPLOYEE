import { useRef, useEffect } from 'react'
import * as THREE from 'three'

// Base pulse color (gold) when no activity
const COLOR_BASE  = new THREE.Color('#e5c76b')
const COLOR_CYAN  = new THREE.Color('#22d3ee')
const COLOR_GOLD  = new THREE.Color('#e5c76b')
const COLOR_GREEN = new THREE.Color('#22c55e')

const PULSE_DECAY  = 1.0 / 1.5  // intensity: back to 1.0 over 1.5 s
const COLOR_HOLD_MS = { 'ws:memory:added': 600, 'ws:task:completed': 800, 'ws:learning:completed': 800 }

const PULSE_MAP = {
  'ws:memory:added':       { intensity: 2.5, color: COLOR_CYAN  },
  'ws:task:completed':     { intensity: 2.5, color: COLOR_GOLD  },
  'ws:learning:completed': { intensity: 2.5, color: COLOR_GREEN },
}

/**
 * Returns refs { pulseIntensity, pulseColor } that the CoreSphere useFrame loop
 * reads each frame to drive u_pulseIntensity / u_pulseColor uniforms.
 *
 * pulseColor decays back toward COLOR_BASE after the hold window.
 */
export function useActivityPulse(reducedMotion = false) {
  const pulseIntensity = useRef(1.0)
  const pulseColor     = useRef(COLOR_BASE.clone())
  const colorTimer     = useRef(0)
  const activeColor    = useRef(COLOR_BASE.clone())

  useEffect(() => {
    if (reducedMotion) return

    function handle(e) {
      const cfg = PULSE_MAP[e.type]
      if (!cfg) return
      pulseIntensity.current = cfg.intensity
      activeColor.current.copy(cfg.color)
      pulseColor.current.copy(cfg.color)
      colorTimer.current = (COLOR_HOLD_MS[e.type] || 600) / 1000
    }

    const events = Object.keys(PULSE_MAP)
    events.forEach(ev => window.addEventListener(ev, handle))
    return () => events.forEach(ev => window.removeEventListener(ev, handle))
  }, [reducedMotion])

  // Called every frame from CoreSphere's useFrame
  function tick(delta) {
    if (reducedMotion) return

    // Decay intensity back toward 1.0
    if (pulseIntensity.current > 1.0) {
      pulseIntensity.current = Math.max(1.0, pulseIntensity.current - PULSE_DECAY * delta)
    }

    // Decay color timer then lerp back to base
    if (colorTimer.current > 0) {
      colorTimer.current = Math.max(0, colorTimer.current - delta)
    } else {
      pulseColor.current.lerp(COLOR_BASE, delta * 2.5)
    }
  }

  return { pulseIntensity, pulseColor, tick }
}

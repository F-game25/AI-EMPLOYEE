import { useEffect, useState, useRef } from 'react'
import { useAppStore } from '../store/appStore'

/**
 * Tracks freshness of a data source and returns 'LIVE' | 'STALE' | 'OFFLINE'.
 *
 * - OFFLINE: WS not connected at all.
 * - STALE:   WS connected but `value` reference hasn't changed in >staleAfterMs.
 * - LIVE:    `value` changed within staleAfterMs.
 *
 * Usage:
 *   const cpu = useSystemStore(s => s.systemStatus?.cpu)
 *   const state = useChannelState(cpu, 10_000)
 */
export function useChannelState(value, staleAfterMs = 10_000) {
  const wsConnected = useAppStore(s => s.wsConnected)
  const lastChangeRef = useRef(Date.now())
  const lastValueRef = useRef(value)
  const [tick, setTick] = useState(0)

  // Update last-change timestamp whenever the watched value reference changes
  if (value !== lastValueRef.current) {
    lastValueRef.current = value
    lastChangeRef.current = Date.now()
  }

  // Re-evaluate every 2s so STALE flips on without external updates
  useEffect(() => {
    const id = setInterval(() => setTick(t => (t + 1) % 1_000_000), 2_000)
    return () => clearInterval(id)
  }, [])

  if (!wsConnected) return 'OFFLINE'
  const age = Date.now() - lastChangeRef.current
  return age > staleAfterMs ? 'STALE' : 'LIVE'
}

/** Color mapping for state dots. */
export const STATE_COLOR = {
  LIVE:    '#00FFB4',
  STALE:   '#FFD93D',
  OFFLINE: '#FF4444',
}

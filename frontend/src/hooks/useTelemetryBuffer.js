import { useEffect, useRef } from 'react'

/**
 * useTelemetryBuffer
 *   Maintains a rolling buffer of the latest `maxLength` numeric samples
 *   for a continuously-changing scalar (e.g. CPU%, latency ms, tokens/sec).
 *   Mutates a ref so consumers can pass `buf` directly to canvas components
 *   without forcing extra renders on every push.
 */
export function useTelemetryBuffer(currentValue, maxLength = 120) {
  const buf = useRef([])
  useEffect(() => {
    if (currentValue == null || Number.isNaN(currentValue)) return
    buf.current.push(currentValue)
    if (buf.current.length > maxLength) {
      buf.current = buf.current.slice(-maxLength)
    }
  }, [currentValue, maxLength])
  return buf.current
}

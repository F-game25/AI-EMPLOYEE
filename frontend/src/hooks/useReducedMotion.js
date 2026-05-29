import { useEffect, useState } from 'react'
import { usePerformanceMode } from './usePerformanceMode'

/**
 * useReducedMotion
 *   Respects OS-level prefers-reduced-motion AND auto-engages on low-tier devices.
 *   Use this anywhere you'd otherwise run a continuous animation, transition,
 *   or drive a useFrame loop.
 *
 *   Returns: boolean — true means animations should be skipped.
 */
export function useReducedMotion() {
  const { tier } = usePerformanceMode()
  const [prefersReduced, setPrefersReduced] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const update = (e) => setPrefersReduced(e.matches)
    mq.addEventListener?.('change', update)
    return () => mq.removeEventListener?.('change', update)
  }, [])

  return prefersReduced || tier === 'low'
}

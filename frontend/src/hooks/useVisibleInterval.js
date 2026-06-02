import { useEffect, useRef } from 'react'

/**
 * useVisibleInterval — like setInterval, but pauses while the tab is hidden so
 * idle background tabs don't burn CPU on re-render ticks. Optionally scales the
 * period by a multiplier (e.g. the performance-tier pollMultiplier).
 *
 *   useVisibleInterval(() => setTick(t => t + 1), 600, pollMultiplier)
 */
export function useVisibleInterval(callback, ms, multiplier = 1) {
  const cb = useRef(callback)
  cb.current = callback

  useEffect(() => {
    if (!ms || ms <= 0) return
    const period = Math.max(16, Math.round(ms * (multiplier || 1)))
    let id = null
    const start = () => { if (id == null) id = setInterval(() => cb.current(), period) }
    const stop = () => { if (id != null) { clearInterval(id); id = null } }
    const onVis = () => (document.hidden ? stop() : start())

    if (!document.hidden) start()
    document.addEventListener('visibilitychange', onVis)
    return () => { stop(); document.removeEventListener('visibilitychange', onVis) }
  }, [ms, multiplier])
}

export default useVisibleInterval

import { useEffect, useState, useRef } from 'react'

/**
 * useIntersection
 *   Tracks whether an element is currently in the viewport. Use to pause
 *   animations / data updates when a panel is scrolled off-screen.
 *
 *   Usage:
 *     const ref = useRef(null)
 *     const visible = useIntersection(ref, { threshold: 0.1 })
 *     return <div ref={ref}>{visible ? <ExpensiveChart/> : null}</div>
 *
 *   Returns: boolean — true when the element intersects the viewport.
 */
export function useIntersection(ref, options = {}) {
  const [intersecting, setIntersecting] = useState(false)
  const observerRef = useRef(null)

  useEffect(() => {
    const el = ref?.current
    if (!el || typeof IntersectionObserver === 'undefined') {
      // Fallback: assume visible when IO is unavailable.
      setIntersecting(true)
      return
    }

    if (observerRef.current) observerRef.current.disconnect()

    observerRef.current = new IntersectionObserver(
      ([entry]) => setIntersecting(entry.isIntersecting),
      { threshold: 0, rootMargin: '0px', ...options }
    )

    observerRef.current.observe(el)
    return () => observerRef.current?.disconnect()
  }, [ref, options.threshold, options.rootMargin, options.root])

  return intersecting
}

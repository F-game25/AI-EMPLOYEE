import { useEffect, useState } from 'react'

/**
 * useVisibility
 *   Tracks document visibility (tab focused / minimised / locked).
 *   Use to pause polling, animations, or expensive renders when the user
 *   isn't looking. Critical for laptops on battery.
 *
 *   Returns: boolean — true when the page is visible.
 */
export function useVisibility() {
  const [visible, setVisible] = useState(() => {
    if (typeof document === 'undefined') return true
    return !document.hidden
  })

  useEffect(() => {
    if (typeof document === 'undefined') return
    const update = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])

  return visible
}

import { useEffect } from 'react'
import { ws } from '../api/secureClient'

/**
 * Subscribe to one or more WS event types. Cleans up on unmount.
 * Uses ws.on / ws.off from secureClient.
 */
export function useWebSocketEvents(
  events: string[],
  handler: (event: string, data: unknown) => void,
): void {
  useEffect(() => {
    const unsubs = events.map(ev => ws.on(ev, handler))
    return () => { unsubs.forEach(fn => fn()) }
  }, [events.join(',')]) // stable dep string — events array is typically static
}

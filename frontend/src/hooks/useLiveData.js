import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE } from '../config/api'

/**
 * useLiveData — generic REST + optional WS event refresh hook.
 *
 * Usage:
 *   const { data, loading, error, refresh, lastTick } = useLiveData({
 *     endpoint: '/api/agents/list',   // fetched via GET on mount + on wsEvent
 *     wsEvent:  'agent:update',       // optional — WS event name that triggers refresh
 *     pollMs:   5000,                 // optional — polling fallback interval
 *     transform: raw => raw.agents,  // optional — shape raw response
 *     skip:     false,                // set true to disable fetching
 *   })
 */
export function useLiveData({ endpoint, wsEvent, pollMs, transform, skip = false }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(!skip)
  const [error, setError]     = useState(null)
  const [lastTick, setTick]   = useState(null)
  const abortRef  = useRef(null)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    if (!endpoint || skip) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, { signal: ctrl.signal, credentials: 'include' })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const raw = await res.json()
      if (!mountedRef.current) return
      setData(transform ? transform(raw) : raw)
      setTick(Date.now())
    } catch (e) {
      if (e.name === 'AbortError') return
      if (!mountedRef.current) return
      setError(e.message || 'Request failed')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [endpoint, skip, transform])

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true
    if (!skip) refresh()
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [refresh, skip])

  // WS event subscription
  useEffect(() => {
    if (!wsEvent) return
    const handler = e => {
      if (e.detail?.type === wsEvent || e.type === wsEvent) refresh()
    }
    window.addEventListener('ws:event', handler)
    window.addEventListener(wsEvent, handler)
    return () => {
      window.removeEventListener('ws:event', handler)
      window.removeEventListener(wsEvent, handler)
    }
  }, [wsEvent, refresh])

  // Polling fallback
  useEffect(() => {
    if (!pollMs || skip) return
    const id = setInterval(refresh, pollMs)
    return () => clearInterval(id)
  }, [pollMs, skip, refresh])

  return { data, loading, error, refresh, lastTick }
}

export default useLiveData

import { useState, useEffect } from 'react'

const KEY = 'ai_devmode'

export function isDevModeActive() {
  try { return localStorage.getItem(KEY) === '1' } catch { return false }
}

export function useDevMode() {
  const [active, setActive] = useState(isDevModeActive)

  useEffect(() => {
    const onStorage = () => setActive(isDevModeActive())
    window.addEventListener('storage', onStorage)
    window.addEventListener('devmode:change', onStorage)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener('devmode:change', onStorage)
    }
  }, [])

  return active
}

export function enableDevMode() {
  try { localStorage.setItem(KEY, '1') } catch { /* ignore */ }
  window.dispatchEvent(new Event('devmode:change'))
}

export function disableDevMode() {
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
  window.dispatchEvent(new Event('devmode:change'))
}

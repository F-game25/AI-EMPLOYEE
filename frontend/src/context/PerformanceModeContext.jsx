import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { usePerformanceMode, setPerformanceTier } from '../hooks/usePerformanceMode'

const TIER_ORDER = { low: 0, medium: 1, high: 2 }
const TIER_CONFIG = {
  high:   { is3DAllowed: true,  animationsAllowed: true,  particleBudget: 2500, pollMultiplier: 1   },
  medium: { is3DAllowed: true,  animationsAllowed: true,  particleBudget: 800,  pollMultiplier: 1.5 },
  low:    { is3DAllowed: false, animationsAllowed: false, particleBudget: 0,    pollMultiplier: 2.5 },
}

const PerformanceModeContext = createContext(null)

export function PerformanceModeProvider({ children }) {
  const browser = usePerformanceMode()
  const [hardware, setHardware] = useState(null)
  const [hwError, setHwError] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt')
    if (!token) return
    fetch('/api/system/hardware', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setHardware(d) })
      .catch(() => setHwError(true))
  }, [])

  // Use the more conservative (lower) of the two tiers
  const serverTier = hardware?.ui_tier
  const effectiveTier = (() => {
    if (!serverTier) return browser.tier
    const b = TIER_ORDER[browser.tier] ?? 1
    const s = TIER_ORDER[serverTier] ?? 1
    return b <= s ? browser.tier : serverTier
  })()

  const setTierOverride = useCallback((tier) => setPerformanceTier(tier), [])

  const value = {
    ...TIER_CONFIG[effectiveTier],
    tier: effectiveTier,
    browserTier: browser.tier,
    serverTier: serverTier || null,
    hardware,
    hwError,
    setTierOverride,
  }

  return (
    <PerformanceModeContext.Provider value={value}>
      {children}
    </PerformanceModeContext.Provider>
  )
}

export function useAppPerformance() {
  const ctx = useContext(PerformanceModeContext)
  if (!ctx) {
    // Fallback when used outside provider (during initial load)
    return { tier: 'medium', is3DAllowed: true, animationsAllowed: true, particleBudget: 800, pollMultiplier: 1.5, hardware: null, setTierOverride: () => {} }
  }
  return ctx
}

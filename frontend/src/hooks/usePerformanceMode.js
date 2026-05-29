import { useEffect, useState } from 'react'

/**
 * usePerformanceMode
 *   Detects the device's performance tier so the UI can scale visual richness
 *   accordingly. Critical for running on weak laptops with external AI.
 *
 *   Tiers:
 *     'high'   — modern desktop / high-end laptop. Full effects, 3D, bloom, particles.
 *     'medium' — standard laptop. Reduced particle counts, simpler shaders, no bloom.
 *     'low'    — weak/old laptop, small screen. 2D fallbacks, no animations on idle pages,
 *                static glows, polling intervals doubled.
 *
 *   Detection signals (combined heuristic):
 *     - navigator.hardwareConcurrency  (CPU cores)
 *     - navigator.deviceMemory         (RAM in GB; Chrome/Edge only)
 *     - WebGL renderer fingerprint     (Intel HD / software = low)
 *     - prefers-reduced-motion         (forces low if user wants reduced)
 *     - screen size                    (small screens get medium)
 *     - localStorage override          (user-forced tier for testing/preference)
 *
 *   Returns { tier, is3DAllowed, animationsAllowed, particleBudget, pollMultiplier }.
 */

const STORAGE_KEY = 'nx_perf_tier'
const VALID_TIERS = ['high', 'medium', 'low']

function detectTier() {
  // 1. User override wins
  try {
    const override = localStorage.getItem(STORAGE_KEY)
    if (override && VALID_TIERS.includes(override)) return override
  } catch {}

  // 2. Reduced-motion preference forces low
  try {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return 'low'
  } catch {}

  // 3. Combine signals
  const cores = navigator.hardwareConcurrency || 4
  const memory = navigator.deviceMemory || 4 // GB; undefined on Firefox/Safari
  const smallScreen = window.innerWidth < 1280 || window.innerHeight < 720

  // 4. WebGL renderer check (cheap)
  let weakGPU = false
  try {
    const c = document.createElement('canvas')
    const gl = c.getContext('webgl') || c.getContext('experimental-webgl')
    if (!gl) {
      weakGPU = true
    } else {
      const dbg = gl.getExtension('WEBGL_debug_renderer_info')
      const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : ''
      if (typeof renderer === 'string') {
        const r = renderer.toLowerCase()
        if (r.includes('software') || r.includes('swiftshader') || r.includes('llvmpipe')) {
          weakGPU = true
        }
      }
    }
  } catch {
    weakGPU = true
  }

  // 5. Score
  if (weakGPU) return 'low'
  if (cores <= 2 || memory <= 2) return 'low'
  if (cores <= 4 || memory <= 4 || smallScreen) return 'medium'
  return 'high'
}

const TIER_CONFIG = {
  high:   { is3DAllowed: true,  animationsAllowed: true,  particleBudget: 2500, pollMultiplier: 1   },
  medium: { is3DAllowed: true,  animationsAllowed: true,  particleBudget: 800,  pollMultiplier: 1.5 },
  low:    { is3DAllowed: false, animationsAllowed: false, particleBudget: 0,    pollMultiplier: 2.5 },
}

let cachedTier = null

export function usePerformanceMode() {
  const [tier, setTier] = useState(() => {
    if (cachedTier) return cachedTier
    if (typeof window === 'undefined') return 'medium'
    cachedTier = detectTier()
    return cachedTier
  })

  // Listen for reduced-motion changes
  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const update = () => {
      cachedTier = detectTier()
      setTier(cachedTier)
    }
    mq.addEventListener?.('change', update)
    return () => mq.removeEventListener?.('change', update)
  }, [])

  return { tier, ...TIER_CONFIG[tier] }
}

/** Force a specific tier (for settings page / debugging). Pass null to clear. */
export function setPerformanceTier(tier) {
  try {
    if (tier === null) localStorage.removeItem(STORAGE_KEY)
    else if (VALID_TIERS.includes(tier)) localStorage.setItem(STORAGE_KEY, tier)
  } catch {}
  cachedTier = null
  // Force a reload — simplest reliable way to apply across all running components.
  if (typeof window !== 'undefined') window.location.reload()
}

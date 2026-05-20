// routeThemes.js — route-aware eye color palette + resolver hook.
//
// Each route maps to a (iris, halo) pair. Two overrides take priority over
// the route palette:
//   1. criticalAlert  → red    (system-wide critical event)
//   2. offline        → gray   (WS dead ≥5s — wsConnected=false OR stale lastTick)
//
// useRouteTheme() returns { iris, halo, key } where `key` is a stable token
// the consumer can use as a transition trigger or for testing.
//
// The eye reads the resolved theme as two CSS vars on its container:
//   --eye-iris-color, --eye-halo-color
// All sub-layers (iris gradient stops, spokes, particles, halo, orb grid)
// reference these vars, so a route change crossfades the entire eye.

import { useLocation } from 'react-router-dom'
import { useSystemStore } from '../store/systemStore'

export const PALETTE = Object.freeze({
  gold:   { iris: '#e5c76b', halo: '#fbbf24' },
  cyan:   { iris: '#22d3ee', halo: '#06b6d4' },
  green:  { iris: '#22c55e', halo: '#10b981' },
  purple: { iris: '#d946ef', halo: '#a855f7' },
  red:    { iris: '#dc2626', halo: '#991b1b' },
  gray:   { iris: '#6b7280', halo: '#4b5563' },
})

// Route → palette key. First match wins; default = gold.
const ROUTE_MAP = [
  { test: /^\/(memory|neural|research)(\/|$)/,                          key: 'cyan'   },
  { test: /^\/(cognition|money|system|learning)(\/|$)/,                 key: 'green'  },
  { test: /^\/(security|blacklight|recon|settings)(\/|$)/,              key: 'purple' },
  // Gold (default) — explicit list for documentation:
  { test: /^\/(agents|operations|forge|intelligence|knowledge|integrations|workflows)(\/|$)/, key: 'gold' },
  { test: /^\/?$/,                                                       key: 'gold'   },
]

export function resolveRouteKey(pathname) {
  if (typeof pathname !== 'string') return 'gold'
  for (const r of ROUTE_MAP) if (r.test.test(pathname)) return r.key
  return 'gold'
}

// Offline detection: wsConnected===false OR last heartbeat > 5s ago.
function isOffline(state) {
  const b = state?.backendStatus
  if (!b) return false
  if (b.ws_connected === false) return true
  const last = Number(b.last_seen || 0)
  if (last > 0 && Date.now() - last > 5000) return true
  return false
}

// Critical alert flag — may not exist on the store yet; treat missing as false.
function isCritical(state) {
  if (state?.criticalAlert === true) return true
  if (state?.systemHealth?.status === 'critical') return true
  return false
}

export function useRouteTheme() {
  const location = useLocation()
  // Subscribe only to the bits we read so the hook doesn't churn.
  const critical = useSystemStore(isCritical)
  const offline  = useSystemStore(isOffline)

  if (critical) return { ...PALETTE.red,  key: 'red'  }
  if (offline)  return { ...PALETTE.gray, key: 'gray' }
  const key = resolveRouteKey(location?.pathname)
  return { ...PALETTE[key], key }
}

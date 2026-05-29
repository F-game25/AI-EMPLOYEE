import { useMemo } from 'react'
import './EyeHalo.css'

/**
 * EyeHalo — TIGHT 3 px rim glow + inner iris bloom + soft bottom spill.
 *
 * Renders 3 absolutely-positioned div layers anchored to the eye container:
 *   - rim:   tight ring glow around the outer housing edge (NOT a diffuse cloud)
 *   - bloom: warm inner glow centered on the iris
 *   - spill: cone of warm light fading downward below the eye
 *
 * All layer colors derive from `--eye-halo-color` (route-aware), so a route
 * change crossfades the whole halo via the 600 ms color transition rule in
 * AvatarPersonality.css.
 *
 * Props:
 *   state      Eye state enum (drives breathe period + error-pulse).
 *   chatOpen   Boosts brightness when chat is engaged.
 *   intensity  0..1 brightness multiplier.
 */

const VALID_STATES = new Set([
  'IDLE', 'THINKING', 'EXECUTING', 'BUSY', 'ERROR', 'LISTENING',
])

function clamp01(v, f = 1) {
  if (typeof v !== 'number' || Number.isNaN(v)) return f
  return Math.max(0, Math.min(1, v))
}

function resolveState(s) {
  if (typeof s !== 'string') return 'IDLE'
  const u = s.toUpperCase()
  return VALID_STATES.has(u) ? u : 'IDLE'
}

export default function EyeHalo({
  state = 'IDLE',
  chatOpen = false,
  intensity = 1,
}) {
  const resolved = resolveState(state)
  const i = clamp01(intensity, 1)

  const containerStyle = useMemo(
    () => ({
      '--eh-intensity': i,
      '--eh-chat-boost': chatOpen ? 1.25 : 1.0,
    }),
    [i, chatOpen],
  )

  const className = useMemo(() => {
    const parts = ['eh-halo', `eh-state-${resolved}`]
    if (chatOpen) parts.push('eh-chat-open')
    return parts.join(' ')
  }, [resolved, chatOpen])

  return (
    <div className={className} style={containerStyle} aria-hidden="true">
      <div className="eh-rim" />
      <div className="eh-bloom" />
      <div className="eh-spill" />
    </div>
  )
}

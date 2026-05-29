import { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import './RoboticEye.css'
import './eye/AvatarPersonality.css'
import './eye/IrisShutter.css'
import './eye/IrisStriations.css'
import './eye/EyeRays.css'
import './eye/EyeHalo.css'
import './eye/EyeDataTicker.css'
import './eye/EyeMechanical.css'

import IrisShutter from './eye/IrisShutter'
import IrisStriations from './eye/IrisStriations'
import EyeFilters from './eye/EyeFilters'
import EyeRays from './eye/EyeRays'
import EyeHalo from './eye/EyeHalo'
import EyeDataTicker from './eye/EyeDataTicker'
import EyeMechanical from './eye/EyeMechanical'
import EyeAtmosphere from './eye/EyeAtmosphere'
import EyeCornea from './eye/EyeCornea'
import Pupil from './eye/Pupil'
import Eyelid from './eye/Eyelid'

import { useAvatarData } from '../../hooks/useAvatarData'
import { useAvatarPersonality } from '../../hooks/useAvatarPersonality'
import { useVoiceLipSync } from '../../hooks/useVoiceLipSync'
import { useRouteTheme } from '../../theme/routeThemes'

/**
 * Cinematic robotic eye — almond lens, 3-plate housing, molten amber iris,
 * cat-eye slit pupil with Pulse triangle mark, glass cornea with key+bounce
 * highlights, orb-grid atmospheric background.
 *
 * Composition (back → front):
 *   Z0  EyeAtmosphere      — orb-grid wireframe + 80 drifting particles
 *   Z1  EyeRays            — 4 cardinal + 8 diagonal energy spokes
 *   Z2  EyeMechanical      — 3-plate segmented brushed-steel housing (almond)
 *   Z3  IrisShutter        — static 24-notch decorative bezel ring (r=56)
 *   Z4  EyeDataTicker      — scrolling micro-text data ring
 *   Z5  almond <g>         — wraps iris + cornea + pupil at scale(1, 0.62)
 *        ├ iris base       — molten amber radial gradient (uses --eye-iris-color)
 *        ├ IrisStriations  — 96 vertical fibers with anisotropic mask
 *        ├ Pupil           — cat-eye slit + Pulse triangle pupil mark
 *        └ EyeCornea       — key/bounce highlights + crescent + crosshair
 *   Z6  EyeHalo            — tight rim glow + inner bloom + bottom spill (DOM)
 *   Z7  HUD                — telemetry text + cardinals
 *   Z8  state badge        — pill above the eye
 */

const R_IRIS = 53
const R_LENS_CAGE = 60

export default function RoboticEye({
  state = 'IDLE',
  tokensRate = 0,
  gpuTemp = 0,
  gpuUsage = 0,
  focusKeyword = 'NEXUS',
  size = 520,
  compact = false,
  chatOpen = false,
  gazeTracking,
  onClick,
  showStateBadge,
}) {
  // ── Route-driven theme ────────────────────────────────────────────────────
  const theme = useRouteTheme()

  // ── Wire to real system state via data hook ────────────────────────────────
  const data = useAvatarData()
  const dataTickerText = data?.tickerText ?? 'NEXUS · COGNITIVE CORE · v2.1.0 · OPERATIONAL'
  const dataCritical   = data?.criticalEvent ?? false
  const dataQueueDepth = data?.queueDepth ?? 0
  const dataTokensRate = data?.tokensRate ?? tokensRate

  // ── Derived intensities ───────────────────────────────────────────────────
  const isHot = gpuTemp > 75
  const heatLevel = Math.max(0, Math.min(1, (gpuTemp - 60) / 30))
  const flareIntensity = Math.min(1, gpuUsage / 100)

  const _gazeTracking = gazeTracking ?? !compact
  const _showStateBadge = showStateBadge ?? !compact
  const _showFullDetail = !compact

  // ── Personality (saccades, drowsy, surprise, wake, breath, tremor) ─────────
  const cursorActiveRef = useRef(Date.now())
  const [, setForceCursorTick] = useState(0)
  useEffect(() => {
    if (!_gazeTracking) return undefined
    const onMove = () => { cursorActiveRef.current = Date.now() }
    window.addEventListener('mousemove', onMove, { passive: true })
    const id = setInterval(() => setForceCursorTick(x => x + 1), 5000)
    return () => { window.removeEventListener('mousemove', onMove); clearInterval(id) }
  }, [_gazeTracking])

  const personality = useAvatarPersonality({
    state,
    chatOpen,
    cursorActiveAt: cursorActiveRef.current,
    criticalEvent: dataCritical,
    queueDepth: dataQueueDepth,
  })

  // ── Voice lip-sync ────────────────────────────────────────────────────────
  const voice = useVoiceLipSync({ enabled: !compact })

  // ── Gaze tracking ─────────────────────────────────────────────────────────
  const containerRef = useRef(null)
  const [gaze, setGaze] = useState({ x: 0, y: 0 })
  const gazeTargetRef = useRef({ x: 0, y: 0 })
  const gazeMaxOffset = compact ? 1.5 : 8

  useEffect(() => {
    if (!_gazeTracking || typeof window === 'undefined') return undefined
    if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined

    let rafId = null
    const onMove = (e) => {
      if (rafId) return
      rafId = requestAnimationFrame(() => {
        rafId = null
        const el = containerRef.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        const cx = rect.left + rect.width / 2
        const cy = rect.top + rect.height / 2
        const dx = e.clientX - cx
        const dy = e.clientY - cy
        const dist = Math.hypot(dx, dy)
        const k = dist === 0 ? 0 : Math.min(1, dist / 600)
        gazeTargetRef.current = {
          x: (dx / (dist || 1)) * gazeMaxOffset * k,
          y: (dy / (dist || 1)) * gazeMaxOffset * k,
        }
      })
    }
    window.addEventListener('mousemove', onMove, { passive: true })

    let animId = null
    const tick = () => {
      setGaze(prev => ({
        x: prev.x + (gazeTargetRef.current.x - prev.x) * 0.12,
        y: prev.y + (gazeTargetRef.current.y - prev.y) * 0.12,
      }))
      animId = requestAnimationFrame(tick)
    }
    animId = requestAnimationFrame(tick)

    return () => {
      window.removeEventListener('mousemove', onMove)
      if (rafId) cancelAnimationFrame(rafId)
      if (animId) cancelAnimationFrame(animId)
    }
  }, [_gazeTracking, gazeMaxOffset])

  const combinedGaze = {
    x: gaze.x + (personality?.microSaccade?.x ?? 0),
    y: gaze.y + (personality?.microSaccade?.y ?? 0),
  }

  // ── Blink ─────────────────────────────────────────────────────────────────
  const [blinking, setBlinking] = useState(false)
  const [blinkPhase, setBlinkPhase] = useState(0)
  const blink = useCallback((closeMs = 60) => {
    setBlinking(true)
    setBlinkPhase(1)
    setTimeout(() => { setBlinking(false); setBlinkPhase(0) }, closeMs)
  }, [])
  useEffect(() => {
    if (compact || state === 'EXECUTING') return undefined
    if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined
    let timeoutId = null
    const scheduleBlink = () => {
      const nextDelay = 4000 + Math.random() * 3000 // 4–7 s jitter
      timeoutId = setTimeout(() => { blink(60); scheduleBlink() }, nextDelay)
    }
    timeoutId = setTimeout(() => { blink(60); scheduleBlink() }, 2000 + Math.random() * 2000)
    return () => { if (timeoutId) clearTimeout(timeoutId) }
  }, [state, compact, blink])

  // State-transition blink (80 ms close on any state change).
  const prevStateRef = useRef(state)
  useEffect(() => {
    if (prevStateRef.current !== state) {
      blink(80)
      prevStateRef.current = state
    }
  }, [state, blink])

  const handleEnter = useCallback(() => { if (!compact) blink(60) }, [compact, blink])

  // ── Pupil dilation ────────────────────────────────────────────────────────
  let pupilScale = 1.0
  if (chatOpen) pupilScale *= 1.5
  if (dataCritical) pupilScale *= 1.2
  if (state === 'EXECUTING') pupilScale *= 0.75
  if (blinking) pupilScale *= 0.2

  // ── State badge label ─────────────────────────────────────────────────────
  const stateBadge =
    chatOpen                  ? 'LISTENING'  :
    state === 'EXECUTING'     ? 'EXECUTING'  :
    state === 'BUSY'          ? 'BUSY'       :
    state === 'THINKING'      ? 'THINKING'   :
    state === 'ERROR'         ? 'ERROR'      :
    voice?.active             ? 'SPEAKING'   :
    _gazeTracking             ? 'WATCHING'   :
                                'IDLE'

  const tickerSpeed = Math.min(1, dataTokensRate / 10000)
  const flareBoost = (voice?.bassEnergy ?? 0) * 0.4
  const finalFlareIntensity = Math.min(1, flareIntensity + flareBoost)
  const breathScale = 1 + (personality?.breath ?? 0) * 0.03
  const cardinals = ['N', 'E', 'S', 'W']
  // brainActivity proxy 0..1 — drives halo brightness modulation
  const brainActivity = useMemo(() => {
    const tps = Math.min(1, dataTokensRate / 5000)
    const queue = Math.min(1, dataQueueDepth / 20)
    return Math.max(0.2, Math.min(1, 0.4 * tps + 0.4 * queue + 0.2 * finalFlareIntensity))
  }, [dataTokensRate, dataQueueDepth, finalFlareIntensity])

  const personalityClasses = (personality?.classNames ?? []).join(' ')
  const containerClasses = [
    're',
    `re--${state.toLowerCase()}`,
    `re--theme-${theme.key}`,
    isHot ? 're--hot' : '',
    compact ? 're--compact' : '',
    chatOpen ? 're--listening' : '',
    blinking ? 're--blinking' : '',
    voice?.active ? 're--speaking' : '',
    dataCritical ? 're--critical' : '',
    theme.key === 'gray' ? 're--offline' : '',
    personalityClasses,
  ].filter(Boolean).join(' ')

  return (
    <div
      ref={containerRef}
      className={containerClasses}
      style={{
        width: size,
        height: size,
        '--eye-iris-color': theme.iris,
        '--eye-halo-color': theme.halo,
        '--brain-activity': brainActivity,
        '--flare-intensity': finalFlareIntensity,
        '--breath-scale': breathScale,
        '--voice-bass': voice?.bassEnergy ?? 0,
        '--voice-mid': voice?.midEnergy ?? 0,
        '--voice-treble': voice?.trebleEnergy ?? 0,
      }}
      onMouseEnter={handleEnter}
      onClick={onClick}
      role="img"
      aria-label={`Cognitive Core, ${stateBadge.toLowerCase()}, ${Math.round(dataTokensRate)} tokens per second`}
    >
      {_showStateBadge && (
        <div className={`re__state-badge re__state-badge--${stateBadge.toLowerCase()}`}>
          <span className="re__state-dot" />
          {stateBadge}
        </div>
      )}

      <svg viewBox="-120 -120 240 240" className="re__svg">
        <defs>
          <EyeFilters />

          {/* Iris molten amber base — 4-stop gradient for cinematic depth.
              Bright cream core → rich amber (route var) → deep amber → bronze rim.
              The --eye-iris-color mid stop preserves molten look while tinting on route. */}
          <radialGradient id="re-iris-base" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%"   stopColor="#fef9ec" />
            <stop offset="35%"  stopColor="var(--eye-iris-color, #f59e0b)" />
            <stop offset="70%"  stopColor="#b45309" />
            <stop offset="100%" stopColor="#78350f" />
          </radialGradient>
          <radialGradient id="re-iris-vignette" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%"  stopColor="rgba(0,0,0,0)" />
            <stop offset="70%" stopColor="rgba(0,0,0,0)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0.5)" />
          </radialGradient>
        </defs>

        {/* ─── Z0: Atmosphere — orb grid + particle field ─── */}
        {_showFullDetail && <EyeAtmosphere />}

        {/* ─── Z1: Energy spokes ─── */}
        {_showFullDetail && (
          <EyeRays state={state} flareIntensity={finalFlareIntensity} />
        )}

        {/* ─── Z2: 3-plate segmented housing (slight oval socket) ─── */}
        <g className="re__housing" transform="scale(1, 0.85)">
          {_showFullDetail && <EyeMechanical heatLevel={heatLevel} />}
        </g>

        {/* ─── Z3: Static decorative bezel ─── */}
        <IrisShutter />

        {/* ─── Z4: Data ticker ─── */}
        {_showFullDetail && (
          <EyeDataTicker text={dataTickerText} speed={tickerSpeed} />
        )}

        {/* ─── Z5: Almond lens group (iris + pupil + cornea) ───
            Wrap in scale(1, 0.62) so the iris reads horizontal/almond
            inside the housing. */}
        <g className="re__almond" transform="scale(1, 0.62)">
          {/* Lens cage bezel — thin dark ring */}
          <circle cx="0" cy="0" r={R_LENS_CAGE} fill="#0A0200" />
          <circle cx="0" cy="0" r={R_LENS_CAGE - 1.5} fill="none" stroke="rgba(0,0,0,0.7)" strokeWidth="1" />

          {/* Iris base */}
          <circle cx="0" cy="0" r={R_IRIS} fill="url(#re-iris-base)" />
          {/* Iris fibers (96 vertical strands, anisotropic) */}
          {_showFullDetail && <IrisStriations />}
          {/* Iris rim vignette */}
          <circle cx="0" cy="0" r={R_IRIS} fill="url(#re-iris-vignette)" />

          {/* Cornea highlights (mix-blend-mode: screen) */}
          {_showFullDetail && <EyeCornea />}

          {/* Pupil — cat-eye slit + Pulse triangle (tracks gaze) */}
          <Pupil pupilScale={pupilScale} gaze={combinedGaze} />
        </g>

        {/* ─── Z7: HUD ─── */}
        {_showFullDetail && (
          <g className="re__hud">
            {cardinals.map((label, i) => {
              const angle = i * 90
              const rad = ((angle - 90) * Math.PI) / 180
              const x = Math.cos(rad) * 128
              const y = Math.sin(rad) * 128
              return (
                <g key={label}>
                  <polygon points="0,-3 3,0 0,3 -3,0" transform={`translate(${x},${y}) rotate(${angle})`} fill="var(--eye-halo-color, #FFD27A)" />
                  <text x={x * 1.05} y={y * 1.05} className="re__cardinal" textAnchor="middle" dominantBaseline="middle">
                    {label}
                  </text>
                </g>
              )
            })}
            <text x="0" y="-104" textAnchor="middle" className="re__tele re__tele--top">FOCUS · {focusKeyword.slice(0, 12).toUpperCase()}</text>
            <text x="98" y="3"   textAnchor="end"    className="re__tele">RATE · {dataTokensRate >= 1000 ? `${(dataTokensRate/1000).toFixed(1)}K` : Math.round(dataTokensRate)}</text>
            <text x="0" y="108"  textAnchor="middle" className="re__tele re__tele--bot">TEMP · {Math.round(gpuTemp)}°C</text>
            <text x="-98" y="3"  textAnchor="start"  className="re__tele">LOAD · {Math.round(gpuUsage)}%</text>
          </g>
        )}

        {/* ─── Z7.5: Eyelids — close vertically on blink (covers all SVG layers) ─── */}
        <Eyelid blinkPhase={blinkPhase} />
      </svg>

      {/* ─── Z6: Halo (DOM overlay, sits above SVG so screen-blend works) ─── */}
      {_showFullDetail && (
        <EyeHalo state={state} chatOpen={chatOpen} intensity={finalFlareIntensity} />
      )}
      {compact && <div className="re__halo" />}
    </div>
  )
}

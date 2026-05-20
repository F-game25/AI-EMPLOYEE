import { useEffect, useRef, useState } from 'react'
import { useEventFeedStore } from '../store/eventFeedStore'

/**
 * useAvatarPersonality
 * --------------------
 * Personality animation layer for RoboticEye. Orchestrates state-specific
 * micro-behaviors (saccades, drowsiness, wake pulse, surprise, breathing,
 * tremor) and returns CSS-var-ready offsets + class names the eye component
 * can consume without coupling to internal timers.
 *
 * Returns:
 *   {
 *     microSaccade: { x, y },   // px offsets to ADD to gaze
 *     drowsy: boolean,          // lids partially closed
 *     wakePulseKey: number,     // bump → retrigger wake pulse keyframe
 *     surpriseKey: number,      // bump → retrigger surprise keyframe
 *     breath: 0..1,             // sin-based 4s oscillation
 *     tremor: 0|1,              // 1 when queueDepth threshold exceeded
 *     classNames: string[]      // descriptors for parent .re element
 *   }
 */

// State → saccade interval (ms). null disables saccades for that state.
const SACCADE_INTERVALS = {
  IDLE: 2000,
  WATCHING: 1500,
  LISTENING: 3000,
  THINKING: 1000,
  EXECUTING: null,
  BUSY: 500,
  ERROR: 300,
  WAKE: null,
}

const DROWSY_THRESHOLD_MS = 60_000
const TREMOR_QUEUE_THRESHOLD = 20
const SURPRISE_DURATION_MS = 1500
const WAKE_DURATION_MS = 800
const BREATH_PERIOD_MS = 4000
const SACCADE_MAX_PX = 3

// Detect reduced-motion preference once (re-evaluated on mount).
const prefersReducedMotion = () => {
  if (typeof window === 'undefined') return false
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

export function useAvatarPersonality({
  state = 'IDLE',
  chatOpen = false,
  cursorActiveAt = Date.now(),
  criticalEvent = false,
  queueDepth = 0,
} = {}) {
  const [reduced, setReduced] = useState(prefersReducedMotion)
  const [microSaccade, setMicroSaccade] = useState({ x: 0, y: 0 })
  const [drowsy, setDrowsy] = useState(false)
  const [breath, setBreath] = useState(0)
  const [wakePulseKey, setWakePulseKey] = useState(0)
  const [surpriseKey, setSurpriseKey] = useState(0)
  const [surpriseActive, setSurpriseActive] = useState(false)
  const [wakeActive, setWakeActive] = useState(false)

  // Rising-edge trackers for triggers.
  const prevState = useRef(state)
  const prevCritical = useRef(criticalEvent)

  // Watch reduced-motion changes live.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const update = (e) => setReduced(e.matches)
    mq.addEventListener?.('change', update)
    return () => mq.removeEventListener?.('change', update)
  }, [])

  // ── Micro-saccades ─────────────────────────────────────────────────────
  // Schedule a saccade per state interval. Pupil jumps 1–3 px in a random
  // direction, then snaps back to 0 after 40 ms hold.
  useEffect(() => {
    if (reduced) {
      setMicroSaccade({ x: 0, y: 0 })
      return
    }
    const interval = SACCADE_INTERVALS[state]
    if (!interval) {
      setMicroSaccade({ x: 0, y: 0 })
      return
    }
    let snapBack
    const tick = () => {
      const angle = Math.random() * Math.PI * 2
      const mag = 1 + Math.random() * (SACCADE_MAX_PX - 1)
      setMicroSaccade({ x: Math.cos(angle) * mag, y: Math.sin(angle) * mag })
      snapBack = setTimeout(() => setMicroSaccade({ x: 0, y: 0 }), 40)
    }
    // Jitter the first tick so multiple instances desync.
    const initial = setTimeout(tick, Math.random() * interval)
    const id = setInterval(tick, interval)
    return () => {
      clearTimeout(initial)
      clearTimeout(snapBack)
      clearInterval(id)
    }
  }, [state, reduced])

  // ── Drowsy lid ─────────────────────────────────────────────────────────
  // If no cursor activity for > 60s, partially close aperture. Any update to
  // cursorActiveAt instantly cancels.
  useEffect(() => {
    const elapsed = Date.now() - cursorActiveAt
    if (elapsed >= DROWSY_THRESHOLD_MS) {
      setDrowsy(true)
      return
    }
    setDrowsy(false)
    const remaining = DROWSY_THRESHOLD_MS - elapsed
    const id = setTimeout(() => setDrowsy(true), remaining)
    return () => clearTimeout(id)
  }, [cursorActiveAt])

  // ── Wake pulse trigger (rising edge on state === 'WAKE') ───────────────
  useEffect(() => {
    if (state === 'WAKE' && prevState.current !== 'WAKE') {
      setWakePulseKey((k) => k + 1)
      setWakeActive(true)
      const id = setTimeout(() => setWakeActive(false), WAKE_DURATION_MS)
      prevState.current = state
      return () => clearTimeout(id)
    }
    prevState.current = state
  }, [state])

  // ── Surprise trigger (rising edge on criticalEvent) ────────────────────
  useEffect(() => {
    if (criticalEvent && !prevCritical.current) {
      setSurpriseKey((k) => k + 1)
      setSurpriseActive(true)
      const id = setTimeout(() => setSurpriseActive(false), SURPRISE_DURATION_MS)
      prevCritical.current = criticalEvent
      return () => clearTimeout(id)
    }
    prevCritical.current = criticalEvent
  }, [criticalEvent])

  // ── Breathing ──────────────────────────────────────────────────────────
  // 4s sin-based oscillation 0..1. Disabled in ERROR or reduced-motion.
  useEffect(() => {
    if (reduced || state === 'ERROR') {
      setBreath(0)
      return
    }
    let raf
    const start = performance.now()
    const loop = (t) => {
      const phase = ((t - start) % BREATH_PERIOD_MS) / BREATH_PERIOD_MS
      // sin → -1..1; remap to 0..1
      setBreath((Math.sin(phase * Math.PI * 2) + 1) / 2)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [reduced, state])

  // ── Event-driven saccade (CRITICAL / SUCCESS) ──────────────────────────
  // Watches the global event feed; on rising edge of a critical/success
  // event, snaps the gaze ±15 px on a random axis for ~120 ms. Also fires a
  // window-level 'eye:saccade-trigger' CustomEvent for any future listeners.
  const latestEvent = useEventFeedStore((s) => s.events?.[0])
  const lastEventIdRef = useRef(null)
  useEffect(() => {
    if (reduced || !latestEvent?.id) return
    if (lastEventIdRef.current === latestEvent.id) return
    lastEventIdRef.current = latestEvent.id
    const p = String(latestEvent.priority || '').toUpperCase()
    const k = String(latestEvent.kind || '').toLowerCase()
    const isCritical = p === 'CRITICAL' || latestEvent.data?.severity === 'critical'
    const isSuccess  = k.includes('success') || k.includes('completed') || latestEvent.data?.severity === 'success'
    if (!isCritical && !isSuccess) return
    const dir = Math.random() < 0.5 ? -1 : 1
    const axis = Math.random() < 0.5 ? 'x' : 'y'
    const mag = 15 * dir
    setMicroSaccade(axis === 'x' ? { x: mag, y: 0 } : { x: 0, y: mag })
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('eye:saccade-trigger', {
        detail: { eventId: latestEvent.id, priority: p, axis, mag },
      }))
    }
    const id = setTimeout(() => setMicroSaccade({ x: 0, y: 0 }), 120)
    return () => clearTimeout(id)
  }, [latestEvent, reduced])

  // ── Tremor ─────────────────────────────────────────────────────────────
  const tremor = !reduced && queueDepth > TREMOR_QUEUE_THRESHOLD ? 1 : 0

  // ── Class names assembled for parent `.re` element ─────────────────────
  const classNames = []
  if (!reduced && SACCADE_INTERVALS[state]) classNames.push('re--saccade-active')
  if (drowsy) classNames.push('re--drowsy')
  if (surpriseActive) classNames.push('re--surprise')
  if (wakeActive) classNames.push('re--wake-active')
  if (tremor) classNames.push('re--tremor-on')
  if (!reduced && state !== 'ERROR') classNames.push('re--breath-on')
  if (chatOpen) classNames.push('re--chat-open')

  return {
    microSaccade,
    drowsy,
    wakePulseKey,
    surpriseKey,
    breath,
    tremor,
    classNames,
  }
}

export default useAvatarPersonality

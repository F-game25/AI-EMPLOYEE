import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * useVoiceLipSync
 *   Reads from a global Web Audio AnalyserNode and produces frequency-band
 *   modulators that an avatar (e.g. RoboticEye) can consume in its render loop.
 *
 * Producer contract:
 *   The voice subsystem should set `window.__nexusVoiceAnalyser = analyser`
 *   when TTS is playing and unset (or set to null) when finished. This hook
 *   is consumer-only — it never creates or owns the AnalyserNode.
 *
 *   The analyser can be attached to any audio source (HTMLAudioElement,
 *   MediaStream, OscillatorNode, etc). Recommended fftSize: 64 or 128.
 *
 * Returns (stable ref-like object, also mirrored to throttled React state):
 *   {
 *     active:       boolean   — true while speaking (+ 200ms tail)
 *     bassEnergy:   0..1      — bins 0-3   (vowels)     → ray flare
 *     midEnergy:    0..1      — bins 4-9   (consonants) → fin wobble
 *     trebleEnergy: 0..1      — bins 10-15 (sibilants)  → particle boost
 *     spectrum:     number[]  — 16 normalized bands (debug/visualization)
 *   }
 *
 * Performance:
 *   - RAF-driven, < 1ms/frame.
 *   - Internal ref updates every frame; React state is throttled to ~30 Hz
 *     so parents that read via state don't re-render at 60+ fps.
 *   - Parents preferring zero re-renders can read the returned `liveRef`
 *     directly inside their own useFrame / RAF loop.
 *
 * Reduced-motion:
 *   - If `prefers-reduced-motion: reduce` is set, returns constant zeros.
 */

const BAND_COUNT = 16
const BASS_END = 4        // bins [0..3]
const MID_END = 10        // bins [4..9]
                          // treble: bins [10..15]
const SMOOTHING = 0.7     // prev weight
const ACTIVE_THRESHOLD = 0.15
const ACTIVE_TAIL_MS = 200
const STATE_THROTTLE_MS = 1000 / 30 // ~30 Hz

const ZERO_SPECTRUM = Object.freeze(new Array(BAND_COUNT).fill(0))
const ZERO_STATE = Object.freeze({
  active: false,
  bassEnergy: 0,
  midEnergy: 0,
  trebleEnergy: 0,
  spectrum: ZERO_SPECTRUM,
})

/** Set the global analyser from anywhere in the app. Pass null to clear. */
export function setVoiceAnalyser(node) {
  if (typeof window === 'undefined') return
  window.__nexusVoiceAnalyser = node || null
}

function prefersReducedMotion() {
  if (typeof window === 'undefined') return false
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

export function useVoiceLipSync({ enabled = true } = {}) {
  const reduced = prefersReducedMotion()
  const shouldRun = enabled && !reduced && typeof window !== 'undefined'

  // Live values — mutated every frame, safe to read from parent RAF loops.
  const liveRef = useRef({
    active: false,
    bassEnergy: 0,
    midEnergy: 0,
    trebleEnergy: 0,
    spectrum: new Array(BAND_COUNT).fill(0),
  })

  // Throttled React state mirror so the hook can also be consumed declaratively.
  const [snapshot, setSnapshot] = useState(ZERO_STATE)

  useEffect(() => {
    if (!shouldRun) {
      liveRef.current.active = false
      liveRef.current.bassEnergy = 0
      liveRef.current.midEnergy = 0
      liveRef.current.trebleEnergy = 0
      liveRef.current.spectrum.fill(0)
      setSnapshot(ZERO_STATE)
      return undefined
    }

    let rafId = 0
    let lastEnergyAt = 0
    let lastEmitAt = 0
    let byteBuf = null
    let lastFftSize = 0

    const tick = () => {
      rafId = requestAnimationFrame(tick)
      const analyser = window.__nexusVoiceAnalyser
      const live = liveRef.current

      if (!analyser || typeof analyser.getByteFrequencyData !== 'function') {
        // No analyser — decay smoothly to zero so the avatar settles.
        live.bassEnergy *= SMOOTHING
        live.midEnergy *= SMOOTHING
        live.trebleEnergy *= SMOOTHING
        const now = performance.now()
        if (now - lastEnergyAt > ACTIVE_TAIL_MS) live.active = false
        maybeEmit(now)
        return
      }

      const fftSize = analyser.fftSize | 0
      const binCount = analyser.frequencyBinCount || (fftSize >> 1)
      if (!byteBuf || lastFftSize !== fftSize) {
        byteBuf = new Uint8Array(binCount)
        lastFftSize = fftSize
      }

      analyser.getByteFrequencyData(byteBuf)

      // Bin into BAND_COUNT equal-width bands, normalize 0..1.
      const perBand = binCount / BAND_COUNT
      const spec = live.spectrum
      for (let b = 0; b < BAND_COUNT; b++) {
        const start = (b * perBand) | 0
        const end = b === BAND_COUNT - 1 ? binCount : ((b + 1) * perBand) | 0
        let sum = 0
        const span = Math.max(1, end - start)
        for (let i = start; i < end; i++) sum += byteBuf[i]
        spec[b] = sum / (span * 255)
      }

      // Aggregate energy bands.
      let bass = 0
      for (let i = 0; i < BASS_END; i++) bass += spec[i]
      bass /= BASS_END

      let mid = 0
      for (let i = BASS_END; i < MID_END; i++) mid += spec[i]
      mid /= MID_END - BASS_END

      let treble = 0
      for (let i = MID_END; i < BAND_COUNT; i++) treble += spec[i]
      treble /= BAND_COUNT - MID_END

      // Smooth.
      live.bassEnergy = SMOOTHING * live.bassEnergy + (1 - SMOOTHING) * bass
      live.midEnergy = SMOOTHING * live.midEnergy + (1 - SMOOTHING) * mid
      live.trebleEnergy = SMOOTHING * live.trebleEnergy + (1 - SMOOTHING) * treble

      const now = performance.now()
      const total = live.bassEnergy + live.midEnergy + live.trebleEnergy
      if (total > ACTIVE_THRESHOLD) {
        lastEnergyAt = now
        live.active = true
      } else if (now - lastEnergyAt > ACTIVE_TAIL_MS) {
        live.active = false
      }

      maybeEmit(now)
    }

    const maybeEmit = (now) => {
      if (now - lastEmitAt < STATE_THROTTLE_MS) return
      lastEmitAt = now
      const live = liveRef.current
      setSnapshot({
        active: live.active,
        bassEnergy: live.bassEnergy,
        midEnergy: live.midEnergy,
        trebleEnergy: live.trebleEnergy,
        // Shallow copy so React detects change; cheap for 16 floats.
        spectrum: live.spectrum.slice(),
      })
    }

    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [shouldRun])

  // Expose the live ref alongside the throttled snapshot for advanced consumers.
  const getLive = useCallback(() => liveRef.current, [])

  return {
    active: snapshot.active,
    bassEnergy: snapshot.bassEnergy,
    midEnergy: snapshot.midEnergy,
    trebleEnergy: snapshot.trebleEnergy,
    spectrum: snapshot.spectrum,
    liveRef,
    getLive,
  }
}

export default useVoiceLipSync

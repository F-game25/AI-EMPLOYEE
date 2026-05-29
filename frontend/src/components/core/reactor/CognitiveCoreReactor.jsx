/* ─────────────────────────────────────────────────────────────────────────
 * CognitiveCoreReactor.jsx
 * ------------------------
 * Parent component for the AI-EMPLOYEE Cognitive Core rebuild. Mounts all 11
 * z-layers of the reactor scene in strict z-order. Sibling layer components
 * are lazy-loaded so the build stays green even if other parallel agents have
 * not shipped their files yet (Suspense fallback = null).
 *
 * Layer map (z-index → component):
 *   0  EnergyField        — animated radial energy gradient backdrop
 *   1  ParticleStarfield  — WebGL/Canvas starfield
 *   2  NebulaFog          — colored fog wisps
 *   3  TacticalGrid       — polar tactical grid overlay
 *   4  OuterOrbits        — rotating orbital rings
 *   5  TacticalGeometry   — angular HUD geometry
 *   6  ScanSweep          — radar-style sweep line
 *   7  EnergyConnections  — neural connection paths + pulses
 *   8  OrbitalKPICards    — floating KPI tiles in orbit
 *   9  MechanicalIris     — the iris itself (own file, always rendered)
 *  10  Eyelid             — blink overlay
 *  11  CoreOverlay        — state badge + focus caption (DOM)
 * ──────────────────────────────────────────────────────────────────────── */

import { lazy, Suspense } from 'react'
import { useAvatarPersonality } from '../../../hooks/useAvatarPersonality'
import { useRouteTheme } from '../../../theme/routeThemes'

// Lazy siblings — built by parallel agents. .catch fallback keeps build green.
const EnergyField       = lazy(() => import('./EnergyField').catch(() => ({ default: () => null })))
const ParticleStarfield = lazy(() => import('./ParticleStarfield').catch(() => ({ default: () => null })))
const NebulaFog         = lazy(() => import('./NebulaFog').catch(() => ({ default: () => null })))
const TacticalGrid      = lazy(() => import('./TacticalGrid').catch(() => ({ default: () => null })))
const OuterOrbits       = lazy(() => import('./OuterOrbits').catch(() => ({ default: () => null })))
const TacticalGeometry  = lazy(() => import('./TacticalGeometry').catch(() => ({ default: () => null })))
const ScanSweep         = lazy(() => import('./ScanSweep').catch(() => ({ default: () => null })))
const EnergyConnections = lazy(() => import('./EnergyConnections').catch(() => ({ default: () => null })))
const OrbitalKPICards   = lazy(() => import('./OrbitalKPICards').catch(() => ({ default: () => null })))

import MechanicalIris from './MechanicalIris'
import Eyelid from './Eyelid'
import CoreOverlay from './CoreOverlay'
import './CognitiveCoreReactor.css'

export default function CognitiveCoreReactor({
  state = 'IDLE',
  tokensRate = 0,
  reasoningCount = 0,
  contextDepth = 0,
  memoryRate = 0,
  agentActivity = 0,
  taskActivity = 0,
  gpuTemp = 0,
  gpuUsage = 0,
  focusKeyword = '',
  eyeSize = 580,
}) {
  const persona = useAvatarPersonality({ state }) || {}
  useRouteTheme() // side effect: sets --eye-iris-color, --eye-halo-color

  const stateLower = String(state || 'idle').toLowerCase()
  const stageSize = Math.round(eyeSize * 1.5)

  // Pull motion knobs with safe fallbacks — the hook may return a subset.
  const pupilScale = typeof persona.pupilScale === 'number' ? persona.pupilScale : 1
  const gazeX = typeof persona.gazeX === 'number'
    ? persona.gazeX
    : (persona.microSaccade?.x ?? 0) / 15
  const gazeY = typeof persona.gazeY === 'number'
    ? persona.gazeY
    : (persona.microSaccade?.y ?? 0) / 15
  const blinkPhase = typeof persona.blinkPhase === 'number' ? persona.blinkPhase : 0

  return (
    <div
      className={`ccr-reactor ccr-reactor--${stateLower}`}
      data-state={stateLower}
      style={{
        width: stageSize,
        height: stageSize,
        '--reactor-size': `${stageSize}px`,
        '--iris-size': `${eyeSize}px`,
      }}
    >
      <Suspense fallback={null}>
        {/* Z0 — Energy field bg */}
        <div className="ccr-layer ccr-layer--0">
          <EnergyField state={state} />
        </div>
        {/* Z1 — WebGL particle starfield */}
        <div className="ccr-layer ccr-layer--1">
          <ParticleStarfield size={stageSize} />
        </div>
        {/* Z2 — Nebula fog */}
        <div className="ccr-layer ccr-layer--2">
          <NebulaFog />
        </div>
        {/* Z3 — Tactical polar grid */}
        <div className="ccr-layer ccr-layer--3">
          <TacticalGrid />
        </div>
        {/* Z4 — Outer orbital rings */}
        <div className="ccr-layer ccr-layer--4">
          <OuterOrbits state={state} />
        </div>
        {/* Z5 — Tactical geometry */}
        <div className="ccr-layer ccr-layer--5">
          <TacticalGeometry />
        </div>
        {/* Z6 — Scan sweep */}
        <div className="ccr-layer ccr-layer--6">
          <ScanSweep state={state} />
        </div>
        {/* Z7 — Energy connections */}
        <div className="ccr-layer ccr-layer--7">
          <EnergyConnections />
        </div>
        {/* Z8 — Orbital KPI cards */}
        <div className="ccr-layer ccr-layer--8">
          <OrbitalKPICards
            reasoningCount={reasoningCount}
            tokensRate={tokensRate}
            contextDepth={contextDepth}
            memoryRate={memoryRate}
          />
        </div>
      </Suspense>

      {/* Z9 — Mechanical iris (own file, always rendered) */}
      <div className="ccr-layer ccr-layer--9">
        <MechanicalIris
          state={state}
          pupilScale={pupilScale}
          gazeX={gazeX}
          gazeY={gazeY}
          tokensRate={tokensRate}
          gpuTemp={gpuTemp}
          gpuUsage={gpuUsage}
          size={eyeSize}
        />
      </div>

      {/* Z10 — Eyelid */}
      <div className="ccr-layer ccr-layer--10">
        <Eyelid blinkPhase={blinkPhase} />
      </div>

      {/* Z11 — Overlay (state badge, focus caption) */}
      <div className="ccr-layer ccr-layer--11">
        <CoreOverlay state={state} focusKeyword={focusKeyword} />
      </div>
    </div>
  )
}

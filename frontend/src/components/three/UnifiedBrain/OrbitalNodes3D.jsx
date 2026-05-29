import { useRef, useEffect, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const SUBSYSTEMS = [
  { id: 'memory',    label: 'MEM', color: '#22d3ee', event: 'ws:memory:added',        angle: 0   },
  { id: 'agents',    label: 'AGT', color: '#a855f7', event: 'ws:task:completed',       angle: 60  },
  { id: 'research',  label: 'RSC', color: '#22c55e', event: 'ws:learning:started',     angle: 120 },
  { id: 'security',  label: 'SEC', color: '#ef4444', event: 'ws:notification',         angle: 180 },
  { id: 'economy',   label: 'ECO', color: '#fbbf24', event: 'ws:task:completed',       angle: 240 },
  { id: 'knowledge', label: 'KNW', color: '#e5c76b', event: 'ws:topic:skill_updated',  angle: 300 },
]

const ORBIT_RADIUS  = 7
const ORBIT_SPEED   = 0.15      // rad / s
const ORBIT_TILT    = 15 * (Math.PI / 180)
const PULSE_PEAK    = 3.0
const PULSE_DECAY   = PULSE_PEAK / 1.2  // back to base in 1.2 s
const BASE_INTENSITY = 0.8

function OrbitalNode({ cfg, reducedMotion }) {
  const meshRef  = useRef()
  const lightRef = useRef()
  const phaseRef = useRef(cfg.angle * (Math.PI / 180))
  const pulse    = useRef(BASE_INTENSITY)

  const color = useMemo(() => new THREE.Color(cfg.color), [cfg.color])

  useEffect(() => {
    if (reducedMotion) return
    function handle() {
      pulse.current = PULSE_PEAK
    }
    window.addEventListener(cfg.event, handle)
    return () => window.removeEventListener(cfg.event, handle)
  }, [cfg.event, reducedMotion])

  useFrame((_, delta) => {
    if (!meshRef.current || document.hidden) return

    // Advance orbital phase
    if (!reducedMotion) phaseRef.current += ORBIT_SPEED * delta

    const phase = phaseRef.current
    const x = Math.cos(phase) * ORBIT_RADIUS
    const y = Math.sin(phase) * ORBIT_RADIUS * Math.sin(ORBIT_TILT)
    const z = Math.sin(phase) * ORBIT_RADIUS * Math.cos(ORBIT_TILT)
    meshRef.current.position.set(x, y, z)

    // Decay pulse
    if (pulse.current > BASE_INTENSITY) {
      pulse.current = Math.max(BASE_INTENSITY, pulse.current - PULSE_DECAY * delta)
    }
    const intensity = pulse.current
    meshRef.current.material.emissiveIntensity = intensity
    const scale = 0.12 + (intensity - BASE_INTENSITY) * 0.06
    meshRef.current.scale.setScalar(scale)

    if (lightRef.current) {
      lightRef.current.position.copy(meshRef.current.position)
      lightRef.current.intensity = intensity * 0.6
    }
  })

  return (
    <>
      <mesh ref={meshRef}>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial
          color={cfg.color}
          emissive={cfg.color}
          emissiveIntensity={BASE_INTENSITY}
          roughness={0.3}
          metalness={0.7}
        />
      </mesh>
      <pointLight ref={lightRef} color={cfg.color} intensity={BASE_INTENSITY * 0.6} distance={4} />
    </>
  )
}

export default function OrbitalNodes3D() {
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
    []
  )

  return (
    <group>
      {SUBSYSTEMS.map(cfg => (
        <OrbitalNode key={cfg.id} cfg={cfg} reducedMotion={reducedMotion} />
      ))}
    </group>
  )
}

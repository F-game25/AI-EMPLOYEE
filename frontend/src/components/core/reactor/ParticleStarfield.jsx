/**
 * ParticleStarfield — Z1 WebGL particle field via R3F.
 * 1000 particles (500 on low-end), additive blend, slow drift + global Z rotation.
 * Pauses on tab hidden; skipped entirely on prefers-reduced-motion.
 */
import { Canvas, useFrame } from '@react-three/fiber'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'

const LOW_END = typeof navigator !== 'undefined' && (navigator.hardwareConcurrency ?? 8) <= 4
const PARTICLE_COUNT = LOW_END ? 500 : 1000

function ParticleField() {
  const ref = useRef()
  const phasesRef = useRef(null)

  const { positions, sizes, colors } = useMemo(() => {
    const positions = new Float32Array(PARTICLE_COUNT * 3)
    const sizes = new Float32Array(PARTICLE_COUNT)
    const colors = new Float32Array(PARTICLE_COUNT * 3)
    const phases = new Float32Array(PARTICLE_COUNT)
    const goldColor = new THREE.Color('#e5c76b')
    const cyanColor = new THREE.Color('#22d3ee')
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const r = 80 + Math.random() * 320
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(Math.random() * 2 - 1)
      positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      positions[i * 3 + 2] = (Math.random() - 0.5) * 300
      sizes[i] = 0.4 + Math.random() * 1.6
      const isAccent = Math.random() < 0.1
      const c = isAccent ? cyanColor : goldColor
      colors[i * 3]     = c.r
      colors[i * 3 + 1] = c.g
      colors[i * 3 + 2] = c.b
      phases[i] = Math.random() * Math.PI * 2
    }
    phasesRef.current = phases
    return { positions, sizes, colors }
  }, [])

  useFrame(({ clock }) => {
    if (!ref.current) return
    const t = clock.getElapsedTime() * 0.04
    const pos = ref.current.geometry.attributes.position
    const arr = pos.array
    const phases = phasesRef.current
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      arr[i * 3]     += Math.sin(t + phases[i]) * 0.03
      arr[i * 3 + 1] += Math.cos(t * 0.7 + phases[i]) * 0.02
    }
    pos.needsUpdate = true
    ref.current.rotation.z = t * 0.05
  })

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-size"     args={[sizes, 1]} />
        <bufferAttribute attach="attributes-color"    args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={1.4}
        sizeAttenuation
        vertexColors
        transparent
        opacity={0.7}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

export default function ParticleStarfield() {
  const reducedMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches

  const [frameloop, setFrameloop] = useState('always')

  useEffect(() => {
    if (typeof document === 'undefined') return
    const onVis = () => setFrameloop(document.hidden ? 'never' : 'always')
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])

  const onCreated = useCallback(({ gl }) => {
    gl.domElement.addEventListener('webglcontextlost', e => e.preventDefault())
    gl.domElement.addEventListener('webglcontextrestored', () => gl.forceContextRestore?.())
  }, [])

  if (reducedMotion) return null

  return (
    <Canvas
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
      camera={{ position: [0, 0, 400], fov: 50 }}
      gl={{ antialias: false, alpha: true, powerPreference: 'low-power' }}
      frameloop={frameloop}
      dpr={[1, LOW_END ? 1 : 1.5]}
      onCreated={onCreated}
    >
      <ParticleField />
    </Canvas>
  )
}

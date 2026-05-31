/**
 * FiberStreamParticles — dense glowing fiber-optic particle streams.
 * Creates the "Kronos brain" aesthetic: streaming trails radiating
 * from cluster centers, colored by region.
 */
import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const STREAM_COUNT   = 400  // number of streaming fibers
const POINTS_PER_FIBER = 20 // trail length

// Region colors matching brain architecture
const REGION_COLORS = [
  new THREE.Color('#22d3ee'),  // cyan  — memory
  new THREE.Color('#fbbf24'),  // gold  — cognition
  new THREE.Color('#a855f7'),  // purple — reasoning
  new THREE.Color('#22c55e'),  // green  — execution
  new THREE.Color('#f472b6'),  // pink   — language
  new THREE.Color('#60a5fa'),  // blue   — input/output
]

// Cluster origins — the "brain regions"
const REGIONS = [
  { pos: [-6, 1, 0],   radius: 3.5, color: 0 },  // cognitive — cyan
  { pos: [0, 0, 0],    radius: 2.5, color: 1 },   // memory — gold
  { pos: [6, -1, 0],   radius: 3,   color: 2 },   // agent — purple
  { pos: [-2, 3, 2],   radius: 2,   color: 3 },   // execution — green
  { pos: [3, 2, -3],   radius: 2.5, color: 4 },   // language — pink
  { pos: [-4, -2, 2],  radius: 2,   color: 5 },   // io — blue
]

function createFibers() {
  // Each fiber: origin in a region, direction outward, speed, color
  return Array.from({ length: STREAM_COUNT }, (_, i) => {
    const region = REGIONS[i % REGIONS.length]
    const theta  = Math.random() * Math.PI * 2
    const phi    = Math.acos(2 * Math.random() - 1)
    // Start near region center with small offset
    const startX = region.pos[0] + (Math.random() - 0.5) * region.radius
    const startY = region.pos[1] + (Math.random() - 0.5) * region.radius * 0.6
    const startZ = region.pos[2] + (Math.random() - 0.5) * region.radius
    // Stream direction — mostly outward from region, with some curl
    const speed = 0.02 + Math.random() * 0.04
    const dx = Math.sin(phi) * Math.cos(theta) * speed
    const dy = Math.sin(phi) * Math.sin(theta) * speed * 0.5
    const dz = Math.cos(phi) * speed
    const maxDist = region.radius * (1.5 + Math.random() * 2)
    return {
      x: startX, y: startY, z: startZ,
      ox: startX, oy: startY, oz: startZ,
      dx, dy, dz, maxDist,
      t: Math.random(), // phase offset
      colorIdx: region.color,
    }
  })
}

export default function FiberStreamParticles() {
  const fibersRef = useRef(createFibers())
  const pointsRef = useRef()

  // Pre-allocate positions + colors for all trail points
  const totalPoints = STREAM_COUNT * POINTS_PER_FIBER
  const positions = useMemo(() => new Float32Array(totalPoints * 3), [])
  const colors    = useMemo(() => new Float32Array(totalPoints * 3), [])

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('color',    new THREE.BufferAttribute(colors,    3))
    return geo
  }, [positions, colors])

  useFrame((_, delta) => {
    if (!pointsRef.current) return
    const fibers = fibersRef.current
    const posAttr = pointsRef.current.geometry.attributes.position
    const colAttr = pointsRef.current.geometry.attributes.color

    for (let fi = 0; fi < STREAM_COUNT; fi++) {
      const f = fibers[fi]
      f.t += delta

      // Advance fiber head position
      const dist = Math.sqrt(
        (f.x - f.ox) ** 2 + (f.y - f.oy) ** 2 + (f.z - f.oz) ** 2
      )
      if (dist > f.maxDist) {
        // Reset to origin with new direction
        const region = REGIONS[fi % REGIONS.length]
        f.x = region.pos[0] + (Math.random() - 0.5) * region.radius
        f.y = region.pos[1] + (Math.random() - 0.5) * region.radius * 0.5
        f.z = region.pos[2] + (Math.random() - 0.5) * region.radius
        f.ox = f.x; f.oy = f.y; f.oz = f.z
        const theta = Math.random() * Math.PI * 2
        const phi   = Math.acos(2 * Math.random() - 1)
        const speed = 0.02 + Math.random() * 0.04
        f.dx = Math.sin(phi) * Math.cos(theta) * speed
        f.dy = Math.sin(phi) * Math.sin(theta) * speed * 0.5
        f.dz = Math.cos(phi) * speed
        f.maxDist = region.radius * (1.5 + Math.random() * 2)
      } else {
        f.x += f.dx
        f.y += f.dy
        f.z += f.dz
      }

      const baseColor = REGION_COLORS[f.colorIdx]
      const base = fi * POINTS_PER_FIBER

      // Write trail points (head → tail, fading opacity via alpha-in-color)
      for (let pi = 0; pi < POINTS_PER_FIBER; pi++) {
        const frac = 1 - pi / POINTS_PER_FIBER  // 1 at head, 0 at tail
        const idx  = (base + pi) * 3
        const back = pi * 0.8 / POINTS_PER_FIBER
        posAttr.array[idx]     = f.x - f.dx * (pi * 0.8)
        posAttr.array[idx + 1] = f.y - f.dy * (pi * 0.8)
        posAttr.array[idx + 2] = f.z - f.dz * (pi * 0.8)
        colAttr.array[idx]     = baseColor.r * frac
        colAttr.array[idx + 1] = baseColor.g * frac
        colAttr.array[idx + 2] = baseColor.b * frac
      }
    }

    posAttr.needsUpdate = true
    colAttr.needsUpdate = true
  })

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial
        size={0.08}
        vertexColors
        transparent
        opacity={0.85}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  )
}

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const COUNT = 2000

export default function BrainParticles() {
  const pointsRef = useRef()

  const { positions, velocities } = useMemo(() => {
    const positions = new Float32Array(COUNT * 3)
    const velocities = new Float32Array(COUNT * 3)
    for (let i = 0; i < COUNT; i++) {
      const theta = Math.random() * Math.PI * 2
      const phi   = Math.acos(2 * Math.random() - 1)
      const r     = 5 + Math.random() * 9
      positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.5
      positions[i * 3 + 2] = r * Math.cos(phi)
      velocities[i * 3]     = (Math.random() - 0.5) * 0.003
      velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.003
      velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.003
    }
    return { positions, velocities }
  }, [])

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions.slice(), 3))
    return geo
  }, [positions])

  useFrame(() => {
    if (!pointsRef.current) return
    const posAttr = pointsRef.current.geometry.attributes.position
    for (let i = 0; i < COUNT; i++) {
      posAttr.array[i * 3]     += velocities[i * 3]
      posAttr.array[i * 3 + 1] += velocities[i * 3 + 1]
      posAttr.array[i * 3 + 2] += velocities[i * 3 + 2]
      // Boundary wrap
      const dx = posAttr.array[i * 3]
      const dy = posAttr.array[i * 3 + 1]
      const dz = posAttr.array[i * 3 + 2]
      if (Math.abs(dx) > 14) posAttr.array[i * 3]     *= -0.9
      if (Math.abs(dy) > 7)  posAttr.array[i * 3 + 1] *= -0.9
      if (Math.abs(dz) > 14) posAttr.array[i * 3 + 2] *= -0.9
    }
    posAttr.needsUpdate = true
  })

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial
        color="#20D6C7"
        size={0.04}
        sizeAttenuation
        transparent
        opacity={0.35}
        depthWrite={false}
      />
    </points>
  )
}

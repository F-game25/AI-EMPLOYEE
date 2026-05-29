import { useRef, useEffect, forwardRef, useImperativeHandle } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const NODES = [
  { id: 'classify',   label: 'CLASSIFY',   pos: [-2.4, 0, 0] },
  { id: 'retrieve',   label: 'RETRIEVE',   pos: [-1.2, 0, 0] },
  { id: 'plan',       label: 'PLAN',       pos: [0,    0, 0] },
  { id: 'act',        label: 'ACT',        pos: [1.2,  0, 0] },
  { id: 'synthesize', label: 'SYNTHESIZE', pos: [2.4,  0, 0] },
]

const STATUS_COLOR = {
  idle:   new THREE.Color('#20D6C7').multiplyScalar(0.4),
  active: new THREE.Color('#20D6C7'),
  done:   new THREE.Color('#22C55E'),
  error:  new THREE.Color('#EF4444'),
}

const CognitiveNetwork = forwardRef(function CognitiveNetwork(_, ref) {
  const groupRef = useRef()
  const meshRefs = useRef({})
  const pulseValues = useRef({})

  NODES.forEach(n => { pulseValues.current[n.id] = 0 })

  useImperativeHandle(ref, () => ({
    dispatchEvent(e) {
      if (e.type === 'pulse') {
        const nodeId = e.nodeId?.toLowerCase?.() || 'classify'
        const matched = NODES.find(n => n.id === nodeId || nodeId.includes(n.id))
        if (matched) pulseValues.current[matched.id] = 1.0
      }
    }
  }))

  useFrame((_, delta) => {
    if (document.hidden) return
    NODES.forEach(n => {
      const mesh = meshRefs.current[n.id]
      if (!mesh) return
      const pulse = pulseValues.current[n.id]
      if (pulse > 0.01) {
        pulseValues.current[n.id] = Math.max(0, pulse - delta * 1.2)
        const col = STATUS_COLOR.active.clone().lerp(STATUS_COLOR.idle, 1 - pulse)
        mesh.material.emissive.copy(col)
        mesh.material.emissiveIntensity = 0.3 + pulse * 1.2
        mesh.scale.setScalar(1 + pulse * 0.25)
      } else {
        mesh.material.emissiveIntensity = 0.15
        mesh.scale.setScalar(1)
      }
    })
  })

  return (
    <group ref={groupRef}>
      {/* Edges between nodes */}
      {NODES.slice(0, -1).map((n, i) => {
        const next = NODES[i + 1]
        const mid = new THREE.Vector3(
          (n.pos[0] + next.pos[0]) / 2,
          (n.pos[1] + next.pos[1]) / 2,
          0
        )
        const len = next.pos[0] - n.pos[0]
        return (
          <mesh key={`edge-${i}`} position={[n.pos[0] + len / 2, n.pos[1], n.pos[2]]}>
            <boxGeometry args={[len * 0.85, 0.015, 0.015]} />
            <meshBasicMaterial color="#20D6C7" transparent opacity={0.25} />
          </mesh>
        )
      })}

      {/* Nodes */}
      {NODES.map(n => (
        <mesh
          key={n.id}
          ref={el => { meshRefs.current[n.id] = el }}
          position={n.pos}
        >
          <icosahedronGeometry args={[0.22, 1]} />
          <meshStandardMaterial
            color="#0E1020"
            emissive={STATUS_COLOR.idle}
            emissiveIntensity={0.15}
            roughness={0.4}
            metalness={0.8}
          />
        </mesh>
      ))}
    </group>
  )
})

export default CognitiveNetwork

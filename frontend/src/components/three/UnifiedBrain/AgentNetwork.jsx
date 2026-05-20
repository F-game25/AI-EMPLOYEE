import { useRef, useMemo, forwardRef, useImperativeHandle } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const MAX_AGENTS = 50

const STATUS_COLOR = {
  running: new THREE.Color('#E5C76B'),
  active:  new THREE.Color('#E5C76B'),
  idle:    new THREE.Color('#20D6C7').multiplyScalar(0.4),
  error:   new THREE.Color('#EF4444'),
  paused:  new THREE.Color('#9A9AA5'),
}

function agentColor(status) {
  return STATUS_COLOR[status] || STATUS_COLOR.idle
}

const AgentNetwork = forwardRef(function AgentNetwork(_, ref) {
  const meshRef = useRef()
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const agentsRef = useRef([])

  useImperativeHandle(ref, () => ({
    dispatchEvent(e) {
      if (e.type === 'sync' && Array.isArray(e.agents)) {
        agentsRef.current = e.agents.slice(0, MAX_AGENTS)
      }
    }
  }))

  useFrame((state, delta) => {
    if (!meshRef.current) return
    const agents = agentsRef.current
    const count = Math.min(agents.length, MAX_AGENTS)
    const t = state.clock.elapsedTime

    agents.slice(0, count).forEach((agent, i) => {
      const col = (i % 3) - 1
      const row = Math.floor(i / 3)
      const x = col * 0.8 + Math.sin(t * 0.3 + i) * 0.05
      const y = -row * 0.6 + 1.2 + Math.cos(t * 0.2 + i * 0.5) * 0.05
      dummy.position.set(x, y, 0)
      const isActive = agent.status === 'running' || agent.status === 'active'
      dummy.scale.setScalar(isActive ? 0.18 + Math.sin(t * 2 + i) * 0.02 : 0.13)
      dummy.updateMatrix()
      meshRef.current.setMatrixAt(i, dummy.matrix)
      meshRef.current.setColorAt(i, agentColor(agent.status || agent.state))
    })

    meshRef.current.count = Math.max(count, 1)
    meshRef.current.instanceMatrix.needsUpdate = true
    if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true
  })

  return (
    <instancedMesh ref={meshRef} args={[null, null, MAX_AGENTS]}>
      <octahedronGeometry args={[1, 0]} />
      <meshStandardMaterial
        vertexColors
        roughness={0.3}
        metalness={0.9}
        emissive="#E5C76B"
        emissiveIntensity={0.2}
      />
    </instancedMesh>
  )
})

export default AgentNetwork

import { useRef, useEffect, forwardRef, useImperativeHandle, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useBrainStore } from '../../../store/brainStore'

const reducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const MAX_NODES = 80
const TYPE_COLOR = {
  money:      '#FFD700',
  learning:   '#60A5FA',
  automation: '#20D6C7',
  memory:     '#9333EA',
  system:     '#9A9AA5',
  concept:    '#20D6C7',
  agent:      '#E5C76B',
  task:       '#60A5FA',
}

function typeColor(type) {
  return new THREE.Color(TYPE_COLOR[type] || '#9A9AA5')
}

const GOLD_FLASH_DECAY = 4.0 / 0.8  // 4.0 → 0 in 0.8 s

const MemoryNetwork = forwardRef(function MemoryNetwork(_, ref) {
  const meshRef       = useRef()
  const dummy         = useMemo(() => new THREE.Object3D(), [])
  const flashValues   = useRef({})
  const nodeFlash     = useRef({})    // per-node gold flash: { [nodeId]: 0-4 }
  const lastFlashId   = useRef(null)
  const rm            = useMemo(reducedMotion, [])
  const nodeData      = useRef([])

  const initialNodes = useBrainStore.getState().nodes.slice(0, MAX_NODES)
  nodeData.current = initialNodes

  // Listen for ws:memory:added — flash the newest node gold
  useEffect(() => {
    if (rm) return
    function handle() {
      const nodes = useBrainStore.getState().nodes
      if (!nodes.length) return
      const newest = nodes[nodes.length - 1]
      if (!newest) return
      lastFlashId.current = newest.id
      nodeFlash.current[newest.id] = 4.0
    }
    window.addEventListener('ws:memory:added', handle)
    return () => window.removeEventListener('ws:memory:added', handle)
  }, [rm])

  useImperativeHandle(ref, () => ({
    dispatchEvent(e) {
      if (e.type === 'flash') {
        flashValues.current[e.clusterId] = 1.0
        flashValues.current['_global'] = 0.8
      }
      if (e.type === 'add_node' && e.node) {
        if (nodeData.current.length < MAX_NODES) {
          nodeData.current = [...nodeData.current, e.node]
        } else {
          nodeData.current = [...nodeData.current.slice(1), e.node]
        }
      }
    }
  }))

  const goldColor = useMemo(() => new THREE.Color('#e5c76b'), [])

  useFrame((_, delta) => {
    if (!meshRef.current) return
    const nodes = nodeData.current
    const count = Math.min(nodes.length, MAX_NODES)
    const globalFlash = flashValues.current['_global'] || 0

    nodes.slice(0, count).forEach((n, i) => {
      // Orbital positioning — 3 rings
      const ring = Math.floor(i / 12)
      const theta = (i % 12) * (Math.PI * 2 / 12)
      const radius = 1.0 + ring * 0.6
      const x = Math.cos(theta) * radius
      const y = Math.sin(theta) * radius * 0.5

      dummy.position.set(x, y, 0)
      const nf = nodeFlash.current[n.id] || 0
      const scale = 0.08 + (n.weight || 0.5) * 0.12 + globalFlash * 0.06 + nf * 0.015
      dummy.scale.setScalar(scale)
      dummy.updateMatrix()
      meshRef.current.setMatrixAt(i, dummy.matrix)

      // Color: gold flash overrides type color when flashing
      const col = nf > 0.1
        ? typeColor(n.type || n.group).clone().lerp(goldColor, nf / 4.0)
        : typeColor(n.type || n.group)
      meshRef.current.setColorAt(i, col)
    })

    meshRef.current.count = count
    meshRef.current.instanceMatrix.needsUpdate = true
    if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true

    // Decay global flash values
    Object.keys(flashValues.current).forEach(k => {
      if (flashValues.current[k] > 0)
        flashValues.current[k] = Math.max(0, flashValues.current[k] - delta * 1.5)
    })
    // Decay per-node gold flash
    Object.keys(nodeFlash.current).forEach(k => {
      if (nodeFlash.current[k] > 0)
        nodeFlash.current[k] = Math.max(0, nodeFlash.current[k] - GOLD_FLASH_DECAY * delta)
    })
  })

  return (
    <instancedMesh ref={meshRef} args={[null, null, MAX_NODES]}>
      <sphereGeometry args={[1, 8, 6]} />
      <meshStandardMaterial
        vertexColors
        emissive="#20D6C7"
        emissiveIntensity={0.3}
        roughness={0.5}
        metalness={0.6}
        transparent
        opacity={0.85}
      />
    </instancedMesh>
  )
})

export default MemoryNetwork

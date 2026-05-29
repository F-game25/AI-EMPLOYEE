import { useRef, useMemo, forwardRef, useImperativeHandle } from 'react'
import { useFrame } from '@react-three/fiber'
import { Line } from '@react-three/drei'
import * as THREE from 'three'

const NETWORK_ORIGINS = {
  cognitive: new THREE.Vector3(-6, 0, 0),
  memory:    new THREE.Vector3(0, 0, 0),
  agents:    new THREE.Vector3(6, 0, 0),
}

const PACKET_COLOR = {
  cognitive: '#20D6C7',
  memory:    '#9333EA',
  agents:    '#E5C76B',
}

const MAX_PACKETS = 8

const STATIC_EDGES = [
  { from: 'cognitive', to: 'memory' },
  { from: 'memory',    to: 'agents' },
]

function buildCurve(from, to) {
  const a = NETWORK_ORIGINS[from].clone().add(new THREE.Vector3(3, 0, 0))
  const b = NETWORK_ORIGINS[to].clone().add(new THREE.Vector3(-3, 0, 0))
  const mid = a.clone().lerp(b, 0.5).add(new THREE.Vector3(0, 1.5, 1))
  return new THREE.CatmullRomCurve3([a, mid, b])
}

const CrossNetworkEdges = forwardRef(function CrossNetworkEdges(_, ref) {
  const packets = useRef([])
  const sphereGroupRef = useRef()

  const curves = useMemo(() => STATIC_EDGES.map(e => ({
    ...e,
    curve: buildCurve(e.from, e.to),
    points: buildCurve(e.from, e.to).getPoints(40),
  })), [])

  useImperativeHandle(ref, () => ({
    dispatchEvent(e) {
      if (e.type === 'packet' && packets.current.length < MAX_PACKETS) {
        packets.current.push({
          from: e.from,
          to: e.to,
          t: 0,
          speed: 0.4 + Math.random() * 0.3,
          color: PACKET_COLOR[e.from] || '#20D6C7',
          curveKey: `${e.from}-${e.to}`,
        })
      }
    }
  }))

  useFrame((_, delta) => {
    if (document.hidden) return
    // Advance packets
    packets.current = packets.current.filter(p => {
      p.t += delta * p.speed
      return p.t < 1.0
    })
  })

  return (
    <group>
      {/* Static edge tubes */}
      {curves.map(edge => (
        <Line
          key={`${edge.from}-${edge.to}`}
          points={edge.points}
          color="#20D6C7"
          lineWidth={0.6}
          transparent
          opacity={0.15}
        />
      ))}

      {/* Traveling packets */}
      {packets.current.map((p, i) => {
        const curve = curves.find(c => c.curveKey === `${p.from}-${p.to}`)?.curve
          || curves[0].curve
        const pos = curve.getPoint(Math.min(p.t, 1))
        return (
          <mesh key={i} position={pos}>
            <sphereGeometry args={[0.08, 6, 6]} />
            <meshBasicMaterial color={p.color} />
          </mesh>
        )
      })}
    </group>
  )
})

export default CrossNetworkEdges

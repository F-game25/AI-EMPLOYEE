import { useRef, useEffect, useCallback, Suspense, useMemo } from 'react'
import { useAppPerformance } from '../../../context/PerformanceModeContext'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import { BlendFunction } from 'postprocessing'
import CognitiveNetwork from './CognitiveNetwork'
import MemoryNetwork from './MemoryNetwork'
import AgentNetwork from './AgentNetwork'
import CrossNetworkEdges from './CrossNetworkEdges'
import BrainParticles from './BrainParticles'
import FiberStreamParticles from './FiberStreamParticles'
import OrbitalNodes3D from './OrbitalNodes3D'
import { CoreSphere } from '../NeuralCore/CoreSphere'
import { useBrainScene } from './useBrainScene'
import { useBrainStore } from '../../../store/brainStore'
import { useAgentStore } from '../../../store/agentStore'

const WS_ACTIVITY_EVENTS = [
  'ws:memory:added', 'ws:task:completed', 'ws:learning:completed',
  'ws:learning:started', 'ws:notification', 'ws:topic:skill_updated',
]
const ACTIVE_TTL_MS = 8000

// Bloom params for idle / active states
const BLOOM_IDLE   = { threshold: 0.35, intensity: 0.8 }
const BLOOM_ACTIVE = { threshold: 0.20, intensity: 1.6 }

const VIEW_CAMERA = {
  TOP:   [0, 30, 0.001],  // tiny z offset avoids degenerate up-vector
  SIDE:  [30, 0, 0],
  FRONT: [0, 2, 18],
}

function CameraController({ activeView }) {
  const { camera } = useThree()
  useEffect(() => {
    const [x, y, z] = VIEW_CAMERA[activeView] || VIEW_CAMERA.FRONT
    camera.position.set(x, y, z)
    camera.lookAt(0, 0, 0)
  }, [activeView, camera])
  return null
}

function NetworkLabels() {
  return (
    <group>
      {/* Labels are rendered as DOM overlay, not in 3D — see parent */}
    </group>
  )
}

// ── Vault Network — Obsidian-style notes as 3D nodes + wikilink edges ──
const FOLDER_COLOR = {
  concepts: '#22d3ee',
  people:   '#a855f7',
  projects: '#fbbf24',
  topics:   '#22c55e',
  daily:    '#9ca3af',
}
const FOLDER_OFFSET = {
  concepts: [0, 1.2, 0],
  people:   [-0.8, 0, 0],
  projects: [0.8, 0, 0],
  topics:   [0, -1.2, 0],
  daily:    [0, 0, -0.8],
}

function _positionForNode(node, idx, total) {
  const folder = node.folder || 'concepts'
  const base = FOLDER_OFFSET[folder] || [0, 0, 0]
  const angle = (idx / Math.max(total, 1)) * Math.PI * 2
  const r = 1.6 + (idx % 3) * 0.4
  return [
    base[0] + Math.cos(angle) * r,
    base[1] + Math.sin(angle) * r * 0.6,
    base[2] + (Math.sin(angle * 2) * 0.5),
  ]
}

function VaultNode({ node, position }) {
  const meshRef = useRef()
  useFrame(({ clock }) => {
    if (!meshRef.current || document.hidden) return
    const t = clock.getElapsedTime()
    meshRef.current.scale.setScalar(1 + Math.sin(t * 1.5 + node.id?.length || 0) * 0.06)
  })
  const color = FOLDER_COLOR[node.folder] || '#22d3ee'
  return (
    <mesh ref={meshRef} position={position}>
      <sphereGeometry args={[0.18, 12, 12]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.8} roughness={0.35} />
    </mesh>
  )
}

function VaultLink({ from, to, color }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current || document.hidden) return
    const t = clock.getElapsedTime()
    ref.current.material.opacity = 0.25 + Math.sin(t * 1.2) * 0.08
  })
  const dx = to[0] - from[0], dy = to[1] - from[1], dz = to[2] - from[2]
  const len = Math.sqrt(dx*dx + dy*dy + dz*dz) || 0.001
  const mx = (from[0] + to[0]) / 2
  const my = (from[1] + to[1]) / 2
  const mz = (from[2] + to[2]) / 2
  // Compute Euler rotation from y-axis (cylinder default) to direction vector
  const phi = Math.atan2(Math.sqrt(dx*dx + dz*dz), dy)
  const theta = Math.atan2(dz, dx)
  return (
    <mesh ref={ref} position={[mx, my, mz]} rotation={[0, -theta, phi]}>
      <cylinderGeometry args={[0.015, 0.015, len, 6]} />
      <meshBasicMaterial color={color} transparent opacity={0.3} />
    </mesh>
  )
}

function VaultNetwork() {
  const nodes = useBrainStore(s => s.vaultNodes) ?? []
  const links = useBrainStore(s => s.vaultLinks) ?? []
  if (!nodes.length) return null

  // Build position map
  const positions = new Map()
  nodes.forEach((n, i) => positions.set(n.id, _positionForNode(n, i, nodes.length)))

  return (
    <group position={[0, 0, 6]}>
      {nodes.map((n, i) => (
        <VaultNode key={n.id || i} node={n} position={positions.get(n.id)} />
      ))}
      {links.map((l, i) => {
        const a = positions.get(l.source || l.from)
        const b = positions.get(l.target || l.to)
        if (!a || !b) return null
        const sourceNode = nodes.find(n => n.id === (l.source || l.from))
        const color = FOLDER_COLOR[sourceNode?.folder] || '#22d3ee'
        return <VaultLink key={i} from={a} to={b} color={color} />
      })}
    </group>
  )
}

/**
 * Tracks brain active state and smoothly lerps Bloom params.
 * Rendered inside Canvas so useFrame is available.
 */
function AdaptiveBloom() {
  const lastActiveRef    = useRef(0)
  const bloomRef         = useRef()
  const currentIntensity = useRef(BLOOM_IDLE.intensity)
  const currentThreshold = useRef(BLOOM_IDLE.threshold)
  const reducedMotion    = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
    []
  )

  useEffect(() => {
    if (reducedMotion) return
    function markActive() { lastActiveRef.current = Date.now() }
    WS_ACTIVITY_EVENTS.forEach(ev => window.addEventListener(ev, markActive))
    return () => WS_ACTIVITY_EVENTS.forEach(ev => window.removeEventListener(ev, markActive))
  }, [reducedMotion])

  useFrame((_, delta) => {
    if (!bloomRef.current || reducedMotion || document.hidden) return
    const isActive = Date.now() - lastActiveRef.current < ACTIVE_TTL_MS
    const target = isActive ? BLOOM_ACTIVE : BLOOM_IDLE
    const speed = delta * 2.0

    currentIntensity.current += (target.intensity - currentIntensity.current) * speed
    currentThreshold.current += (target.threshold - currentThreshold.current) * speed

    bloomRef.current.intensity        = currentIntensity.current
    bloomRef.current.luminancePass.threshold = currentThreshold.current
  })

  return (
    <EffectComposer>
      <Bloom
        ref={bloomRef}
        blendFunction={BlendFunction.SCREEN}
        luminanceThreshold={BLOOM_IDLE.threshold}
        luminanceSmoothing={0.9}
        intensity={BLOOM_IDLE.intensity}
        mipmapBlur
      />
    </EffectComposer>
  )
}

function BrainScene({ showKnowledgeNodes, showAgentConnections, showVaultNetwork, density, particleBudget }) {
  const cognitiveRef = useRef()
  const memoryRef = useRef()
  const agentsRef = useRef()
  const edgesRef = useRef()
  const { drainQueue } = useBrainScene()

  const refs = { cognitiveRef, memoryRef, agentsRef, edgesRef }

  // Drain command queue each frame (skip when tab hidden)
  useFrame(() => {
    if (document.hidden) return
    drainQueue(refs)
  })

  const allNodes = useBrainStore(s => s.nodes) ?? []
  const agents = useAgentStore(s => s.agents) ?? []

  // Apply density slice — density is 0.2–1.0
  const densityFactor = Math.max(0.1, Math.min(1, density ?? 1))
  const nodes = allNodes.slice(0, Math.ceil(allNodes.length * densityFactor))

  // Apply agent connections filter
  const visibleAgents = showAgentConnections === false ? [] : agents

  const metrics = {
    rotationSpeed: 0.04,
    taskRate: Math.min(visibleAgents.filter(a => a.status === 'running').length / 10, 1),
    load: Math.min(nodes.length / 100, 1),
    errorMix: 0,
    thinking: 0,
  }

  return (
    <>
      {/* Cognitive Network — LangGraph reasoning */}
      <group position={[-6, 0, 0]}>
        <CognitiveNetwork ref={cognitiveRef} />
        {/* Network label plane */}
        <mesh position={[0, -1.2, 0]}>
          <planeGeometry args={[3.5, 0.3]} />
          <meshBasicMaterial color="#0A0C18" transparent opacity={0.6} />
        </mesh>
      </group>

      {/* Memory Network — Mem0 + Neo4j; hidden when showKnowledgeNodes=false */}
      <group position={[0, 0, 0]}>
        <CoreSphere metrics={metrics} />
        {showKnowledgeNodes !== false && (
          <group position={[0, 0, 0]}>
            <MemoryNetwork ref={memoryRef} />
          </group>
        )}
      </group>

      {/* Agent Execution Network; hidden when showAgentConnections=false */}
      <group position={[6, 0, 0]}>
        {showAgentConnections !== false && <AgentNetwork ref={agentsRef} />}
      </group>

      {/* Cross-network connection edges + traveling packets */}
      <CrossNetworkEdges ref={edgesRef} />

      {/* Vault Network — Obsidian-style notes from ~/.ai-employee/vault */}
      {showVaultNetwork !== false && <VaultNetwork />}

      {/* Ambient particles */}
      {particleBudget > 0 && <BrainParticles maxCount={particleBudget} />}

      {/* Fiber-optic streaming trails — cinematic Kronos brain aesthetic */}
      {particleBudget > 0 && <FiberStreamParticles maxCount={Math.floor(particleBudget / 2)} />}

      {/* WS-reactive orbital subsystem nodes */}
      <OrbitalNodes3D />

      {/* Scene lighting */}
      <ambientLight intensity={0.05} />
      <pointLight position={[-6, 3, 2]} color="#20D6C7" intensity={1.2} />
      <pointLight position={[0, 3, 2]} color="#9333EA" intensity={0.8} />
      <pointLight position={[6, 3, 2]} color="#E5C76B" intensity={1.0} />
    </>
  )
}

export default function UnifiedBrain({
  showKnowledgeNodes = true,
  showMemoryLinks = true,
  showAgentConnections = true,
  showVaultNetwork = true,
  activeView = 'FRONT',
  density = 1.0,
} = {}) {
  const { tier, is3DAllowed, particleBudget } = useAppPerformance()

  const onCreated = useCallback(({ gl, setFrameloop }) => {
    const canvas = gl.domElement
    // On context loss: preventDefault (lets the browser/SwiftShader restore) and
    // stop the render loop so we don't spam drawArrays against a dead context.
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault()
      try { setFrameloop?.('never') } catch { /* */ }
    })
    canvas.addEventListener('webglcontextrestored', () => {
      try { setFrameloop?.('demand') } catch { /* */ }
    })
  }, [])

  if (!is3DAllowed) {
    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.3)', borderRadius: 12 }}>
        <div style={{ textAlign: 'center', color: '#4ade80', opacity: 0.7 }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>◉</div>
          <div style={{ fontSize: 13, letterSpacing: 2 }}>NEURAL CORE</div>
          <div style={{ fontSize: 11, opacity: 0.5, marginTop: 4 }}>3D disabled — low performance mode</div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* Network labels — DOM overlay */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0,
        display: 'flex', justifyContent: 'space-around',
        padding: '12px 40px',
        zIndex: 10, pointerEvents: 'none',
      }}>
        {[
          { label: 'COGNITIVE', sub: 'LangGraph Reasoning', color: '#20D6C7' },
          { label: 'MEMORY',    sub: 'Mem0 + Neo4j',        color: '#9333EA' },
          { label: 'AGENTS',    sub: 'Execution Network',    color: '#E5C76B' },
          { label: 'VAULT',     sub: 'Obsidian Notes',       color: '#22d3ee' },
        ].map(n => (
          <div key={n.label} style={{ textAlign: 'center', fontFamily: 'monospace' }}>
            <div style={{ color: n.color, fontSize: '11px', fontWeight: 600, letterSpacing: '0.12em' }}>{n.label}</div>
            <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: '9px', marginTop: 2 }}>{n.sub}</div>
          </div>
        ))}
      </div>

      <Canvas
        camera={{ position: VIEW_CAMERA[activeView] || VIEW_CAMERA.FRONT, fov: 55 }}
        dpr={tier === 'high' ? [1, 1.5] : [1, 1]}
        frameloop="demand"
        gl={{ antialias: true, alpha: false, powerPreference: 'high-performance', failIfMajorPerformanceCaveat: false }}
        style={{ background: '#000000' }}
        onCreated={onCreated}
      >
        <Suspense fallback={null}>
          <CameraController activeView={activeView} />
          <BrainScene
            showKnowledgeNodes={showKnowledgeNodes}
            showAgentConnections={showAgentConnections}
            showVaultNetwork={showVaultNetwork}
            density={density}
            particleBudget={particleBudget}
          />
          <OrbitControls
            enablePan={false}
            minDistance={8}
            maxDistance={30}
            autoRotate
            autoRotateSpeed={0.3}
          />
          {tier === 'high' && <AdaptiveBloom />}
        </Suspense>
      </Canvas>
    </div>
  )
}

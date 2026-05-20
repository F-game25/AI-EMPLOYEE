import { useRef, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import { useAgentStore } from '../../../store/agentStore'
import { useBrainStore } from '../../../store/brainStore'

// Command queue — populated by Zustand subscriptions, drained by useFrame
// Commands never trigger React re-renders; all mutations go through refs

const COMMAND_TYPES = {
  PULSE_NODE:   'PULSE_NODE',
  FLASH_MEMORY: 'FLASH_MEMORY',
  ADD_NODE:     'ADD_NODE',
  FIRE_PACKET:  'FIRE_PACKET',
  SYNC_AGENTS:  'SYNC_AGENTS',
}

export { COMMAND_TYPES }

export function useBrainScene() {
  const commandQueue = useRef([])
  const lastFlush = useRef(0)
  const lastAddNode = useRef(0)

  // Push command without triggering re-render
  const push = (cmd) => {
    commandQueue.current.push(cmd)
  }

  // Subscribe to brainStore outside React render cycle
  useEffect(() => {
    const unsubReasoning = useBrainStore.subscribe(
      s => s.reasoningSteps,
      (steps, prev) => {
        if (!steps.length) return
        const latest = steps[steps.length - 1]
        if (latest === prev?.[prev.length - 1]) return
        push({
          type: COMMAND_TYPES.PULSE_NODE,
          nodeId: latest.node || latest.step || 'classify',
          status: latest.status,
          latency: latest.latency_ms,
        })
        // Fire packet from cognitive → memory on active steps
        if (latest.status === 'active' || latest.status === 'done') {
          push({ type: COMMAND_TYPES.FIRE_PACKET, from: 'cognitive', to: 'memory' })
        }
      }
    )

    const unsubMemory = useBrainStore.subscribe(
      s => s.memoryWrites,
      (writes, prev) => {
        if (!writes.length) return
        const latest = writes[writes.length - 1]
        if (latest === prev?.[prev.length - 1]) return
        push({ type: COMMAND_TYPES.FLASH_MEMORY, clusterId: latest.type || 'default' })
        push({ type: COMMAND_TYPES.FIRE_PACKET, from: 'memory', to: 'agents' })
      }
    )

    const unsubGraph = useBrainStore.subscribe(
      s => s.nodes,
      (nodes, prev) => {
        if (nodes.length <= (prev?.length ?? 0)) return
        const newNodes = nodes.slice(prev?.length ?? 0)
        newNodes.forEach(n => push({ type: COMMAND_TYPES.ADD_NODE, node: n }))
      }
    )

    const unsubAgents = useAgentStore.subscribe(
      s => s.agents,
      (agents) => {
        push({ type: COMMAND_TYPES.SYNC_AGENTS, agents })
      }
    )

    return () => {
      unsubReasoning()
      unsubMemory()
      unsubGraph()
      unsubAgents()
    }
  }, [])

  // Drain queue in useFrame — throttled to 100ms windows
  function drainQueue(refs) {
    const now = performance.now()
    if (now - lastFlush.current < 100) return
    lastFlush.current = now

    const batch = commandQueue.current.splice(0, 30)
    batch.forEach(cmd => {
      if (cmd.type === COMMAND_TYPES.PULSE_NODE && refs.cognitiveRef?.current) {
        refs.cognitiveRef.current.dispatchEvent({ type: 'pulse', nodeId: cmd.nodeId, status: cmd.status })
      }
      if (cmd.type === COMMAND_TYPES.FLASH_MEMORY && refs.memoryRef?.current) {
        refs.memoryRef.current.dispatchEvent({ type: 'flash', clusterId: cmd.clusterId })
      }
      if (cmd.type === COMMAND_TYPES.FIRE_PACKET && refs.edgesRef?.current) {
        refs.edgesRef.current.dispatchEvent({ type: 'packet', from: cmd.from, to: cmd.to })
      }
      if (cmd.type === COMMAND_TYPES.ADD_NODE && refs.memoryRef?.current) {
        const t = performance.now()
        if (t - lastAddNode.current > 100) {
          lastAddNode.current = t
          refs.memoryRef.current.dispatchEvent({ type: 'add_node', node: cmd.node })
        }
      }
      if (cmd.type === COMMAND_TYPES.SYNC_AGENTS && refs.agentsRef?.current) {
        refs.agentsRef.current.dispatchEvent({ type: 'sync', agents: cmd.agents })
      }
    })
  }

  return { commandQueue, drainQueue }
}

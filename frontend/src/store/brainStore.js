import { create } from 'zustand'
import { subscribeWithSelector } from 'zustand/middleware'

const MAX_NODES = 300
const MAX_LINKS = 600

/**
 * Color map per group.
 * Money = gold, Learning = blue, Automation = teal, Memory = purple, default = grey
 */
export const GROUP_COLORS = {
  money: '#FFD700',
  learning: '#60A5FA',
  automation: '#20D6C7',
  memory: '#9333EA',
  system: '#9A9AA5',
  agent: '#E5C76B',
}

/**
 * Derive group from node type or source context.
 */
function endpointId(value) {
  if (value && typeof value === 'object') return value.id || value.key || value.name || value.label || ''
  return value || ''
}

function deriveGroup(node) {
  const rawGroup = String(node.group || '').toLowerCase()
  if (GROUP_COLORS[rawGroup]) return rawGroup
  const t = (node.type || '').toLowerCase()
  if (rawGroup === 'strategy' || rawGroup === 'skill' || rawGroup === 'concept') return 'money'
  if (rawGroup === 'task' || rawGroup === 'output') return 'automation'
  if (rawGroup === 'input' || rawGroup === 'hidden') return 'learning'
  if (t === 'strategy' || t === 'skill' || t === 'concept') return 'money'
  if (t === 'memory') return 'memory'
  if (t === 'task' || t === 'output') return 'automation'
  if (t === 'input' || t === 'hidden') return 'learning'
  if (t === 'agent') return 'agent'
  return 'system'
}

export function normalizeGraphNode(raw, index = 0) {
  if (!raw || typeof raw !== 'object') return null
  const id = String(raw.id || raw.key || raw.name || raw.label || `node-${index}`).trim()
  if (!id) return null
  const group = deriveGroup(raw)
  return {
    id,
    label: String(raw.label || raw.name || id),
    type: String(raw.type || raw.node_type || 'skill').toLowerCase(),
    group,
    weight: Number.isFinite(Number(raw.weight)) ? Number(raw.weight) : 1,
    confidence: Number.isFinite(Number(raw.confidence)) ? Number(raw.confidence) : 0,
    activation: Number.isFinite(Number(raw.activation)) ? Number(raw.activation) : 0,
    source: String(raw.source || 'system'),
    tag: String(raw.tag || ''),
    color: GROUP_COLORS[group] || GROUP_COLORS.system,
  }
}

export function normalizeGraphLink(raw) {
  if (!raw || typeof raw !== 'object') return null
  const source = String(endpointId(raw.source ?? raw.from)).trim()
  const target = String(endpointId(raw.target ?? raw.to)).trim()
  if (!source || !target) return null
  return {
    source,
    target,
    strength: Number.isFinite(Number(raw.strength ?? raw.weight ?? raw.confidence))
      ? Number(raw.strength ?? raw.weight ?? raw.confidence)
      : 0.5,
  }
}

export function normalizeGraphPayload(data = {}) {
  const rawNodes = Array.isArray(data?.nodes) ? data.nodes.slice(0, MAX_NODES) : []
  const nodes = []
  const ids = new Set()
  rawNodes.forEach((raw, index) => {
    const node = normalizeGraphNode(raw, index)
    if (!node || ids.has(node.id)) return
    ids.add(node.id)
    nodes.push(node)
  })

  const rawLinks = Array.isArray(data?.links)
    ? data.links
    : Array.isArray(data?.connections)
      ? data.connections
      : []
  const linkSet = new Set()
  const links = []
  rawLinks.slice(0, MAX_LINKS).forEach(raw => {
    const link = normalizeGraphLink(raw)
    if (!link || !ids.has(link.source) || !ids.has(link.target)) return
    const key = `${link.source}→${link.target}`
    if (linkSet.has(key)) return
    linkSet.add(key)
    links.push(link)
  })

  return {
    nodes,
    links,
    stats: {
      ...(data?.stats || {}),
      node_count: nodes.length,
      link_count: links.length,
    },
    updated_at: data?.updated_at || data?.updatedAt || new Date().toISOString(),
  }
}

export const useBrainStore = create(subscribeWithSelector((set, get) => ({
  // ── Graph data ────────────────────────────────────────────────────────
  nodes: [],
  links: [],
  stats: {},
  updatedAt: null,

  // ── Vault (Obsidian-style notes) — separate layer ────────────────────
  vaultNodes: [],
  vaultLinks: [],
  vaultUpdatedAt: null,

  setVaultGraph: (nodes, links) => set({
    vaultNodes: (nodes || []).slice(0, 200),
    vaultLinks: (links || []).slice(0, 400),
    vaultUpdatedAt: new Date().toISOString(),
  }),

  upsertVaultNode: (node) => set((state) => {
    if (!node || !node.id) return state
    const existing = state.vaultNodes.findIndex(n => n.id === node.id)
    const next = [...state.vaultNodes]
    if (existing >= 0) next[existing] = { ...next[existing], ...node }
    else next.push(node)
    return { vaultNodes: next.slice(-200), vaultUpdatedAt: new Date().toISOString() }
  }),

  removeVaultNode: (id) => set((state) => ({
    vaultNodes: state.vaultNodes.filter(n => n.id !== id),
    vaultLinks: state.vaultLinks.filter(l => l.source !== id && l.target !== id),
    vaultUpdatedAt: new Date().toISOString(),
  })),

  // ── Selected node (for inspector panel) ───────────────────────────────
  selectedNodeId: null,
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  // ── Bulk replace from backend ─────────────────────────────────────────
  setGraph: (data) => {
    const graph = normalizeGraphPayload(data)
    set({
      nodes: graph.nodes,
      links: graph.links,
      stats: graph.stats,
      updatedAt: graph.updated_at,
    })
  },

  // ── Add / update a single node (from mode actions) ────────────────────
  addNode: (raw) => {
    const node = normalizeGraphNode(raw)
    if (!node) return
    set((state) => {
      const existing = state.nodes.findIndex((n) => n.id === node.id)
      let next
      if (existing >= 0) {
        next = [...state.nodes]
        next[existing] = { ...next[existing], ...node }
      } else {
        next = [...state.nodes, node].slice(-MAX_NODES)
      }
      return { nodes: next, updatedAt: new Date().toISOString() }
    })
  },

  // ── Add a link between two nodes ──────────────────────────────────────
  addLink: (raw) => {
    const link = normalizeGraphLink(raw)
    if (!link) return
    set((state) => {
      const ids = new Set(state.nodes.map(n => n.id))
      if (!ids.has(link.source) || !ids.has(link.target)) return state
      const dup = state.links.some(
        (l) =>
          (l.source === link.source || l.source?.id === link.source) &&
          (l.target === link.target || l.target?.id === link.target),
      )
      if (dup) return state
      return { links: [...state.links, link].slice(-MAX_LINKS), updatedAt: new Date().toISOString() }
    })
  },

  // ── Batch add from a mode action ──────────────────────────────────────
  addNodesAndLinks: (nodes, links) => {
    const normalizedNodes = (nodes || []).map(normalizeGraphNode).filter(Boolean)
    const normalizedLinks = (links || []).map(normalizeGraphLink).filter(Boolean)
    set((state) => {
      const nodeMap = new Map(state.nodes.map((n) => [n.id, n]))
      normalizedNodes.forEach((n) => nodeMap.set(n.id, { ...(nodeMap.get(n.id) || {}), ...n }))
      const nextNodes = Array.from(nodeMap.values()).slice(-MAX_NODES)

      const ids = new Set(nextNodes.map(n => n.id))
      const linkSet = new Set(state.links.map((l) => `${l.source?.id || l.source}→${l.target?.id || l.target}`))
      const newLinks = normalizedLinks.filter((l) => ids.has(l.source) && ids.has(l.target) && !linkSet.has(`${l.source}→${l.target}`))
      const nextLinks = [...state.links, ...newLinks].slice(-MAX_LINKS)

      return { nodes: nextNodes, links: nextLinks, updatedAt: new Date().toISOString() }
    })
  },

  // ── Convenience: add a node from a chat/command ───────────────────────
  addFromPrompt: (text, type = 'task', group = 'automation') => {
    const id = `prompt-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    get().addNode({ id, label: text.slice(0, 60), type, group, weight: 1, confidence: 0.5 })
    return id
  },

  // ── Neural Brain integration ──────────────────────────────────────────
  reasoningSteps: [],
  appendReasoningStep: (step) => {
    set((state) => ({
      reasoningSteps: [...state.reasoningSteps, step].slice(-50),
      updatedAt: new Date().toISOString(),
    }))
  },

  memoryWrites: [],
  flashMemoryWrite: (write) => {
    set((state) => ({
      memoryWrites: [...state.memoryWrites, { ...write, ts: Date.now() }].slice(-20),
      updatedAt: new Date().toISOString(),
    }))
  },

  pulseMemory: (memoryIds) => {
    // Mark memory chunks as recently accessed for visual feedback
    set((state) => ({
      updatedAt: new Date().toISOString(),
      // Could highlight memory nodes here if we track them
    }))
  },

  mergeGraphDelta: (delta) => {
    // Merge graph delta (new/updated nodes/links) from Neural Brain
    if (delta?.nodes && Array.isArray(delta.nodes)) {
      delta.nodes.forEach((n) => get().addNode({ ...n, source: 'neural_brain' }))
    }
    if (delta?.links && Array.isArray(delta.links)) {
      delta.links.forEach((l) => get().addLink(l))
    }
  },

  modelCalls: [],
  recordModelCall: (call) => {
    set((state) => ({
      modelCalls: [...state.modelCalls, call].slice(-100),
      updatedAt: new Date().toISOString(),
    }))
  },
})))

import { create } from 'zustand'

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
}

/**
 * Derive group from node type or source context.
 */
function deriveGroup(node) {
  if (node.group) return node.group
  const t = (node.type || '').toLowerCase()
  if (t === 'strategy' || t === 'skill') return 'money'
  if (t === 'memory') return 'memory'
  if (t === 'task' || t === 'output') return 'automation'
  if (t === 'input' || t === 'hidden') return 'learning'
  return 'system'
}

function normalizeNode(raw) {
  const group = deriveGroup(raw)
  return {
    id: raw.id,
    label: raw.label || raw.id,
    type: raw.type || 'skill',
    group,
    weight: raw.weight ?? 1,
    confidence: raw.confidence ?? 0,
    activation: raw.activation ?? 0,
    source: raw.source || 'system',
    tag: raw.tag || '',
    color: GROUP_COLORS[group] || GROUP_COLORS.system,
  }
}

function normalizeLink(raw) {
  return {
    source: raw.source || raw.from,
    target: raw.target || raw.to,
    strength: raw.strength ?? raw.weight ?? raw.confidence ?? 0.5,
  }
}

export const useBrainStore = create((set, get) => ({
  // ── Graph data ────────────────────────────────────────────────────────
  nodes: [],
  links: [],
  stats: {},
  updatedAt: null,

  // ── Selected node (for inspector panel) ───────────────────────────────
  selectedNodeId: null,
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  // ── Bulk replace from backend ─────────────────────────────────────────
  setGraph: (data) => {
    const rawNodes = (data?.nodes || []).slice(0, MAX_NODES)
    const rawLinks = (data?.links || data?.connections || []).slice(0, MAX_LINKS)
    set({
      nodes: rawNodes.map(normalizeNode),
      links: rawLinks.map(normalizeLink),
      stats: data?.stats || {},
      updatedAt: data?.updated_at || new Date().toISOString(),
    })
  },

  // ── Add / update a single node (from mode actions) ────────────────────
  addNode: (raw) => {
    const node = normalizeNode(raw)
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
    const link = normalizeLink(raw)
    set((state) => {
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
    const normalizedNodes = (nodes || []).map(normalizeNode)
    const normalizedLinks = (links || []).map(normalizeLink)
    set((state) => {
      const nodeMap = new Map(state.nodes.map((n) => [n.id, n]))
      normalizedNodes.forEach((n) => nodeMap.set(n.id, { ...(nodeMap.get(n.id) || {}), ...n }))
      const nextNodes = Array.from(nodeMap.values()).slice(-MAX_NODES)

      const linkSet = new Set(state.links.map((l) => `${l.source?.id || l.source}→${l.target?.id || l.target}`))
      const newLinks = normalizedLinks.filter((l) => !linkSet.has(`${l.source}→${l.target}`))
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
}))

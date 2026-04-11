import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const TYPE_COLORS = {
  user: 'var(--gold)',
  lead: '#60a5fa',
  customer: '#34d399',
  agent: '#a78bfa',
  task: '#fb923c',
  unknown: 'var(--text-muted)',
}

const TYPE_ICONS = {
  user: '👤',
  lead: '🎯',
  customer: '⭐',
  agent: '🤖',
  task: '📋',
  unknown: '◆',
}

function MemoryNode({ node }) {
  const color = TYPE_COLORS[node.type] || TYPE_COLORS.unknown
  const icon = TYPE_ICONS[node.type] || TYPE_ICONS.unknown

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2 }}
      className="flex items-center justify-between py-1 px-2 rounded"
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.04)',
        marginBottom: '3px',
      }}
    >
      <div className="flex items-center gap-1.5 min-w-0">
        <span style={{ fontSize: '10px' }} aria-hidden="true">{icon}</span>
        <span
          className="font-mono truncate"
          style={{ fontSize: '10px', color: 'var(--text-secondary)' }}
          title={node.id}
        >
          {node.id}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0 ml-2">
        <span
          className="font-mono"
          style={{ fontSize: '9px', color, opacity: 0.85, letterSpacing: '0.03em' }}
        >
          {node.type}
        </span>
        <span className="font-mono" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
          {node.facts}f
        </span>
      </div>
    </motion.div>
  )
}

export default function MemoryTreePanel() {
  const mem = useAppStore(s => s.memoryTree)
  const [expanded, setExpanded] = useState(true)

  const recentUpdate = mem.recent_updates && mem.recent_updates[0]

  return (
    <div
      className="flex flex-col flex-shrink-0"
      style={{ borderBottom: '1px solid var(--border-gold-dim)' }}
    >
      {/* Header */}
      <button
        className="flex items-center justify-between px-3 py-2 w-full text-left"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls="memory-panel-body"
      >
        <div className="flex items-center gap-2">
          <motion.div
            animate={mem.total_entities > 0 ? { opacity: [1, 0.4, 1] } : { opacity: 0.3 }}
            transition={{ duration: 2, repeat: Infinity }}
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            aria-hidden="true"
            style={{ background: 'var(--gold)' }}
          />
          <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
            MEMORY TREE
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="font-mono"
            style={{ fontSize: '10px', color: 'var(--text-muted)' }}
          >
            {mem.total_entities} nodes
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </button>

      {/* Body */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="memory-panel-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div className="px-3 pb-2">
              {/* Recent activity */}
              {recentUpdate && (
                <div
                  className="flex items-center gap-1 mb-2 px-2 py-1 rounded"
                  style={{ background: 'rgba(212,175,55,0.05)', border: '1px solid rgba(212,175,55,0.1)' }}
                  aria-label={`Recent update: ${recentUpdate.entity_id} modified ${recentUpdate.key}`}
                >
                  <span style={{ fontSize: '9px', color: 'var(--gold)' }}>● LIVE</span>
                  <span
                    className="font-mono truncate"
                    style={{ fontSize: '9px', color: 'var(--text-muted)' }}
                  >
                    {recentUpdate.entity_id} &#8594; {recentUpdate.key}
                  </span>
                </div>
              )}

              {/* Nodes list */}
              <div
                role="list"
                aria-label="Memory tree nodes"
                style={{ maxHeight: '120px', overflowY: 'auto' }}
              >
                <AnimatePresence>
                  {mem.nodes.length === 0 ? (
                    <p
                      className="font-mono text-center"
                      style={{ fontSize: '10px', color: 'var(--text-muted)', padding: '8px 0' }}
                    >
                      No entities in memory
                    </p>
                  ) : (
                    mem.nodes.slice(0, 8).map((node) => (
                      <MemoryNode key={node.id} node={node} />
                    ))
                  )}
                </AnimatePresence>
              </div>

              {mem.nodes.length > 8 && (
                <p
                  className="font-mono text-center"
                  style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px' }}
                >
                  +{mem.nodes.length - 8} more
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

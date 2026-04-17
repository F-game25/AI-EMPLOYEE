import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

const MAX_VISIBLE_FACTS = 5

function MemoryNode({ node, depth = 0, expanded, onToggle }) {
  const typeIcons = { user: '👤', agent: '🤖', task: '📋', concept: '💡', system: '⚙️', default: '◆' }
  const icon = typeIcons[node.type] || typeIcons.default
  const hasFacts = node.facts && node.facts.length > 0
  const hasRelations = node.relations && node.relations.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ marginLeft: depth * 20 }}
    >
      <div
        onClick={() => onToggle(node.entity_id || node.id)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: 'var(--space-2) var(--space-3)',
          borderRadius: 'var(--radius-sm)',
          cursor: hasFacts || hasRelations ? 'pointer' : 'default',
          transition: 'background 150ms',
          userSelect: 'none',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-card)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
      >
        <span style={{ fontSize: '14px' }}>{icon}</span>
        <span style={{ fontSize: '13px', color: 'var(--text-primary)', flex: 1 }}>
          {node.entity_id || node.id}
        </span>
        {node.type && (
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', padding: '1px 6px', background: 'var(--bg-base)', borderRadius: '4px' }}>
            {node.type}
          </span>
        )}
        {hasFacts && (
          <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{node.facts.length} facts</span>
        )}
        {(hasFacts || hasRelations) && (
          <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{expanded ? '▲' : '▼'}</span>
        )}
      </div>

      {expanded && (
        <div style={{ marginLeft: 24, marginBottom: 'var(--space-1)' }}>
          {hasFacts && (
            <div style={{ marginBottom: 'var(--space-1)' }}>
              {node.facts.slice(0, MAX_VISIBLE_FACTS).map((fact, i) => (
                <div key={i} style={{
                  fontSize: '12px',
                  color: 'var(--text-muted)',
                  padding: '3px var(--space-3)',
                  borderLeft: '2px solid var(--border-subtle)',
                  marginBottom: '2px',
                }}>
                  {typeof fact === 'string' ? fact : fact.value || JSON.stringify(fact)}
                </div>
              ))}
              {node.facts.length > MAX_VISIBLE_FACTS && (
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', paddingLeft: 'var(--space-3)' }}>
                  +{node.facts.length - MAX_VISIBLE_FACTS} more facts
                </div>
              )}
            </div>
          )}
          {hasRelations && (
            <div>
              {node.relations.slice(0, 3).map((rel, i) => (
                <div key={i} style={{
                  fontSize: '12px',
                  color: 'var(--info)',
                  padding: '3px var(--space-3)',
                  borderLeft: '2px solid rgba(96,165,250,0.3)',
                  marginBottom: '2px',
                }}>
                  {typeof rel === 'string' ? rel : `${rel.type || 'relates_to'} → ${rel.target}`}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
}

function MemoryStats({ tree }) {
  const stats = [
    { label: 'Total Entities', value: tree?.total_entities ?? 0, color: 'var(--gold)' },
    { label: 'Nodes Loaded', value: (tree?.nodes || []).length, color: 'var(--info)' },
    { label: 'Recent Updates', value: (tree?.recent_updates || []).length, color: 'var(--success)' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
      {stats.map(({ label, value, color }) => (
        <div key={label} className="ds-card" style={{ padding: 'var(--space-3) var(--space-4)' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{label}</div>
          <div style={{ fontSize: '22px', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
        </div>
      ))}
    </div>
  )
}

export default function MemoryPage() {
  const memoryTree = useAppStore(s => s.memoryTree)
  const setMemoryTree = useAppStore(s => s.setMemoryTree)
  const [expanded, setExpanded] = useState({})
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [offlineMode, setOfflineMode] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      setLoading(true)
      try {
        const res = await fetch(`${BASE}/api/memory/tree`, { signal: controller.signal })
        if (res.ok) {
          const data = await res.json()
          setMemoryTree(data)
          setOfflineMode(false)
        } else {
          setOfflineMode(true)
        }
      } catch {
        if (!controller.signal.aborted) setOfflineMode(true)
      }
      setLoading(false)
    }
    load()
    const i = setInterval(load, 10000)
    return () => { clearInterval(i); controller.abort() }
  }, [setMemoryTree, refreshKey])

  const toggleNode = useCallback((id) => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }))
  }, [])

  const filteredNodes = (memoryTree?.nodes || []).filter(node => {
    if (!search) return true
    const id = (node.entity_id || node.id || '').toLowerCase()
    const type = (node.type || '').toLowerCase()
    return id.includes(search.toLowerCase()) || type.includes(search.toLowerCase())
  })

  return (
    <div className="page-enter">
      <PageHeader
        title="Memory"
        subtitle="Agent memory graph — entities, facts, and relationships"
      />

      {offlineMode && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)',
          marginBottom: 'var(--space-4)',
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.2)',
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: 'var(--warning)',
        }}>
          ⚠ OFFLINE MODE — Backend unreachable. Displaying last known memory state.
        </div>
      )}

      {memoryTree?.data_source === 'simulated' && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)',
          marginBottom: 'var(--space-4)',
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.2)',
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: 'var(--warning)',
        }}>
          SIMULATED DATA — Python backend offline
        </div>
      )}

      <MemoryStats tree={memoryTree} />

      {/* Controls */}
      <div style={{ display: 'flex', gap: 'var(--space-3)', marginBottom: 'var(--space-4)', alignItems: 'center' }}>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search entities..."
          style={{
            flex: 1,
            padding: 'var(--space-3)',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            fontFamily: 'inherit',
            outline: 'none',
          }}
        />
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => setRefreshKey(k => k + 1)}
          disabled={loading}
          style={{
            padding: 'var(--space-3) var(--space-4)',
            background: 'transparent',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-secondary)',
            fontSize: '13px',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          {loading ? 'Refreshing...' : '↻ Refresh'}
        </motion.button>
      </div>

      {/* Memory tree */}
      <div className="ds-card" style={{ padding: 'var(--space-2)' }}>
        {filteredNodes.length === 0 ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
            {search ? `No entities matching "${search}"` : 'No memory entities loaded'}
          </div>
        ) : (
          filteredNodes.map((node) => (
            <MemoryNode
              key={node.entity_id || node.id}
              node={node}
              expanded={!!expanded[node.entity_id || node.id]}
              onToggle={toggleNode}
            />
          ))
        )}
      </div>

      {/* Recent updates */}
      {(memoryTree?.recent_updates || []).length > 0 && (
        <div className="ds-card" style={{ padding: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Recent Updates
          </h3>
          {(memoryTree.recent_updates || []).slice(0, 10).map((update, i) => (
            <div key={i} style={{
              padding: 'var(--space-2) 0',
              borderBottom: '1px solid var(--border-subtle)',
              fontSize: '12px',
              display: 'flex',
              gap: 'var(--space-2)',
            }}>
              <span style={{ color: 'var(--text-dim)', flexShrink: 0 }}>
                {update.ts ? new Date(update.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
              </span>
              <span style={{ color: 'var(--text-secondary)', flex: 1 }}>
                {typeof update === 'string' ? update : update.message || update.entity_id || JSON.stringify(update)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

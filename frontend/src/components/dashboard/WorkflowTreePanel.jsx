import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import TertiaryPanel from '../ui/TertiaryPanel'

const STATUS_STYLE = {
  pending: { color: 'var(--text-muted)', dot: '#6b7280' },
  active: { color: 'var(--gold)', dot: 'var(--gold)' },
  completed: { color: 'var(--success)', dot: 'var(--success)' },
  failed: { color: 'var(--error)', dot: 'var(--error)' },
}

function percent(value) {
  return `${Math.max(0, Math.min(100, Number(value) || 0))}%`
}

function NodeCard({ node, selected, onSelect }) {
  const state = STATUS_STYLE[node.status] || STATUS_STYLE.pending
  return (
    <button
      type="button"
      onClick={() => onSelect(node.task_id)}
      className="w-full text-left"
      style={{
        background: selected ? 'rgba(245,196,0,0.08)' : 'rgba(255,255,255,0.02)',
        border: selected ? '1px solid rgba(245,196,0,0.4)' : '1px solid var(--border-subtle)',
        borderRadius: '8px',
        padding: '8px',
      }}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span
            aria-hidden="true"
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '999px',
              background: state.dot,
              boxShadow: node.status === 'active' ? '0 0 8px rgba(245,196,0,.7)' : 'none',
              flexShrink: 0,
            }}
          />
          <span className="font-mono truncate" style={{ fontSize: '11px', color: 'var(--text-primary)' }}>
            {node.task_name || node.task_id}
          </span>
        </div>
        <span className="font-mono uppercase" style={{ fontSize: '10px', color: state.color }}>
          {node.status}
        </span>
      </div>
      <div className="flex items-center justify-between font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
        <span>{node.agent || 'pending'}</span>
        <span>{percent(node.progress_percent)}</span>
      </div>
      <div
        style={{
          marginTop: '6px',
          height: '3px',
          borderRadius: '99px',
          background: 'rgba(255,255,255,0.08)',
          overflow: 'hidden',
        }}
      >
        <motion.div
          animate={{ width: percent(node.progress_percent) }}
          transition={{ duration: 0.25 }}
          style={{ height: '100%', background: state.dot }}
        />
      </div>
    </button>
  )
}

export default function WorkflowTreePanel() {
  const workflow = useAppStore((s) => s.workflowState)
  const [expanded, setExpanded] = useState(true)
  const [selectedTask, setSelectedTask] = useState(null)
  const activeRun = useMemo(() => {
    const runs = workflow?.runs || []
    if (!runs.length) return null
    return runs.find((r) => r.run_id === workflow.active_run) || runs[0]
  }, [workflow])

  const selectedNode = useMemo(() => {
    if (!activeRun || !selectedTask) return activeRun?.nodes?.[0] || null
    return activeRun.nodes.find((n) => n.task_id === selectedTask) || activeRun.nodes[0] || null
  }, [activeRun, selectedTask])

  return (
    <article className="ds-card p-3 min-h-0 flex flex-col">
      <button
        type="button"
        className="flex items-center justify-between mb-2"
        onClick={() => setExpanded((v) => !v)}
        style={{ border: 'none', background: 'transparent', padding: 0, cursor: 'pointer' }}
      >
        <h2 className="font-mono text-xs" style={{ color: 'var(--gold)' }}>LIVE WORKFLOW TREE</h2>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {!activeRun && (
        <p className="font-mono text-[11px] text-center mt-4" style={{ color: 'var(--text-muted)' }}>
          Start automation to see pending, active, and completed tasks.
        </p>
      )}

      {expanded && activeRun && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 min-h-0 flex-1">
          <div className="space-y-2 overflow-y-auto pr-1">
            <div className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
              {activeRun.name} • {activeRun.status?.toUpperCase()} • {percent(activeRun.progress_percent)}
            </div>
            {(activeRun.nodes || []).map((node, idx) => (
              <div key={node.task_id} style={{ position: 'relative' }}>
                {idx > 0 && (
                  <div
                    aria-hidden="true"
                    style={{
                      position: 'absolute',
                      left: '11px',
                      top: '-10px',
                      width: '1px',
                      height: '10px',
                      background: 'rgba(245,196,0,0.25)',
                    }}
                  />
                )}
                <NodeCard node={node} selected={selectedNode?.task_id === node.task_id} onSelect={setSelectedTask} />
              </div>
            ))}
          </div>

          <TertiaryPanel className="p-3 min-h-0 overflow-y-auto">
            {selectedNode ? (
              <div className="space-y-2">
                <div className="font-mono text-[11px]" style={{ color: 'var(--gold)' }}>
                  TASK INSPECTOR
                </div>
                <div className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {selectedNode.task_name || selectedNode.task_id}
                </div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  Brain-assisted: {selectedNode.brain ? 'Yes' : 'No'} • Confidence: {percent((selectedNode.confidence || 0) * 100)}
                </div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  Strategy: {selectedNode.strategy || 'default'} • Agent: {selectedNode.agent || 'pending'}
                </div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  Flow: Task → Strategy → Agent → Action → Result
                </div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  {selectedNode.reasoning || 'Brain reasoning will appear when strategy is chosen.'}
                </div>
                {selectedNode.result && (
                  <div className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                    Result: {selectedNode.result.summary}
                  </div>
                )}
              </div>
            ) : (
              <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Select a task to inspect decision details.
              </div>
            )}
          </TertiaryPanel>
        </div>
      )}
    </article>
  )
}

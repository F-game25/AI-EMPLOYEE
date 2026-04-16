import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const NODE_ORDER = ['User Input', 'Intent', 'Brain Decision', 'Agent', 'Task Steps', 'Result']
const GOLD_BORDER = 'rgba(212,175,55,0.35)'
const GOLD_GLOW = 'rgba(212,175,55,0.2)'
const ACTIVE_EDGE_GRADIENT = `linear-gradient(90deg, ${GOLD_BORDER}, rgba(32,214,199,0.45))`

function buildFlow(run) {
  if (!run) return { nodes: [], edges: [] }
  const firstNode = run.nodes?.[0] || {}
  const recentDecision = run.decision_log?.[0] || {}
  const strategy = firstNode.strategy || firstNode.brain?.strategy || 'default'
  const confidence = firstNode.confidence ?? firstNode.brain?.confidence ?? 0
  const reasoning = firstNode.reasoning || firstNode.brain?.reasoning || recentDecision.summary || 'No reasoning recorded'
  const resultNode = run.nodes?.find((n) => n.status === 'completed' || n.status === 'failed') || run.nodes?.[run.nodes.length - 1] || {}

  const nodes = [
    { id: 'user', label: 'User Input', input: run.goal || run.name || 'Task', output: run.goal || '', reasoning: 'Original request entrypoint', confidence: 1 },
    { id: 'intent', label: 'Intent', input: run.goal || '', output: firstNode.subsystem || 'general', reasoning: 'Intent classified from user request', confidence: confidence || 0.5 },
    { id: 'decision', label: 'Brain Decision', input: firstNode.task_name || run.goal || '', output: strategy, reasoning, confidence: confidence || 0 },
    { id: 'agent', label: 'Agent', input: strategy, output: firstNode.agent || 'core_brain_agent', reasoning: `Selected agent ${firstNode.agent || 'core_brain_agent'} from strategy`, confidence: confidence || 0 },
    { id: 'steps', label: 'Task Steps', input: run.nodes?.length || 0, output: `${run.nodes?.length || 0} steps`, reasoning: `Workflow executed through ${run.nodes?.length || 0} steps`, confidence: 1 },
    { id: 'result', label: 'Result', input: resultNode.task_name || 'execution', output: resultNode.result?.summary || run.status || 'pending', reasoning: resultNode.result?.summary || `Run status is ${run.status || 'pending'}`, confidence: resultNode.status === 'completed' ? 1 : resultNode.status === 'failed' ? 0 : 0.5 },
  ]

  const edges = NODE_ORDER.slice(0, NODE_ORDER.length - 1).map((_, idx) => ({
    id: `edge-${idx}`,
    from: idx,
    to: idx + 1,
    active: idx < Math.max(0, run.nodes?.findIndex((node) => node.status === 'active' || node.status === 'completed') + 1),
  }))

  return { nodes, edges }
}

export default function NeuralGraphPanel() {
  const workflow = useAppStore((s) => s.workflowState)
  const [selectedNode, setSelectedNode] = useState(null)
  const run = useMemo(() => workflow?.runs?.find((item) => item.run_id === workflow?.active_run) || workflow?.runs?.[0] || null, [workflow])
  const { nodes, edges } = useMemo(() => buildFlow(run), [run])

  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
        <div style={{ color: 'var(--text-secondary)', fontSize: '13px', fontWeight: 500 }}>Neural Decision Graph</div>
        <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{run?.run_id || 'No active run'}</div>
      </div>

      {nodes.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Run a task to visualize decision flow.</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
            {nodes.map((node, idx) => (
              <motion.button
                key={node.id}
                onClick={() => setSelectedNode(node)}
                animate={{ boxShadow: idx <= (run?.nodes?.length || 0) ? `0 0 0 1px ${GOLD_BORDER}, 0 0 14px ${GOLD_GLOW}` : 'none' }}
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 'var(--space-2)',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{idx + 1}</div>
                <div style={{ fontSize: '12px', fontWeight: 500 }}>{node.label}</div>
              </motion.button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '6px', marginBottom: 'var(--space-3)' }}>
            {edges.map((edge) => (
              <motion.div
                key={edge.id}
                animate={{ opacity: edge.active ? 1 : 0.3 }}
                style={{
                  flex: 1,
                  height: '4px',
                  borderRadius: '999px',
                  background: edge.active ? ACTIVE_EDGE_GRADIENT : 'rgba(255,255,255,0.08)',
                }}
              />
            ))}
          </div>

          <div className="ds-card" style={{ padding: 'var(--space-3)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ color: 'var(--gold)', fontSize: '12px', marginBottom: 'var(--space-1)' }}>WHY THIS HAPPENED</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Intent: {nodes.find((n) => n.id === 'intent')?.output || 'general'}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Reason: {(selectedNode || nodes.find((n) => n.id === 'decision'))?.reasoning || 'No reasoning available'}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Agent chosen: {nodes.find((n) => n.id === 'agent')?.output || 'core_brain_agent'}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Confidence: {Math.round(((selectedNode || nodes.find((n) => n.id === 'decision'))?.confidence || 0) * 100)}%
            </div>
          </div>

          {selectedNode && (
            <div style={{ marginTop: 'var(--space-2)', fontSize: '12px', color: 'var(--text-secondary)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{selectedNode.label}</strong> · input: {String(selectedNode.input)} · output: {String(selectedNode.output)}
            </div>
          )}
        </>
      )}
    </div>
  )
}

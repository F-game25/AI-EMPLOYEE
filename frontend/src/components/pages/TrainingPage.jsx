import { useState, useEffect } from 'react'
import { Panel, Badge, StatCard } from '../ui/primitives'

export default function TrainingPage() {
  const [agents, setAgents] = useState([])
  const [selected, setSelected] = useState(null)
  const [grade, setGrade] = useState(null)
  const [tab, setTab] = useState('tasks')
  const [taskInput, setTaskInput] = useState('')
  const [reward, setReward] = useState(0.5)
  const [context, setContext] = useState('')
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)

  // Load agents on mount
  useEffect(() => {
    fetch('/api/agents/list').then(r => r.json())
      .then(d => setAgents(d.agents || []))
      .catch(() => {})
  }, [])

  // Load grade when agent selected
  useEffect(() => {
    if (!selected) return
    fetch(`/api/agents/${selected}/grade`).then(r => r.json())
      .then(d => setGrade(d))
      .catch(() => {})
  }, [selected])

  const gradeMap = { 'Ungraded': 0, 'Beginner': 1, 'Basic': 2, 'Mature': 3, 'Advanced': 4, 'Pro': 5 }
  const gradeName = grade?.grade || 'Ungraded'
  const gradeValue = gradeMap[gradeName] || 0
  const maxGrade = 5

  const handleSubmitTask = async () => {
    if (!selected || !taskInput.trim()) return
    setLoading(true)
    try {
      const res = await fetch(`/api/agents/${selected}/ladder/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: taskInput, success: true }),
      })
      const data = await res.json()
      setLogs([...logs, { type: 'task', agent: selected, task: taskInput, ts: new Date().toLocaleTimeString() }])
      setTaskInput('')
      // Reload grade
      const gradeRes = await fetch(`/api/agents/${selected}/grade`).then(r => r.json())
      setGrade(gradeRes)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const handleReinforce = async () => {
    if (!selected) return
    setLoading(true)
    try {
      const res = await fetch(`/api/agents/${selected}/reinforce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reward, context: context || selected }),
      })
      setLogs([...logs, { type: 'reinforce', agent: selected, reward, ts: new Date().toLocaleTimeString() }])
      setContext('')
      setReward(0.5)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  return (
    <div style={{ display: 'flex', gap: 10, height: '100%', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
          <StatCard label="Selected Agent" value={selected ? selected.slice(0, 12) : '—'} color="#20D6C7" sub="Training target" />
          <StatCard label="Current Grade" value={gradeName} color={gradeValue >= 4 ? '#22C55E' : gradeValue >= 2 ? '#E5C76B' : '#F59E0B'} sub={`${gradeValue}/${maxGrade}`} />
        </div>

        <Panel title="Training Session" style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: 10 }}>
            {[
              { id: 'tasks', label: 'Tasks' },
              { id: 'reinforce', label: 'Reinforce' },
              { id: 'parameters', label: 'Parameters' },
              { id: 'history', label: 'History' },
            ].map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  padding: '6px 12px',
                  borderRadius: 4,
                  border: 'none',
                  background: tab === t.id ? 'rgba(32,214,199,0.15)' : 'transparent',
                  color: tab === t.id ? '#20D6C7' : 'rgba(255,255,255,0.5)',
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: tab === t.id ? 600 : 400,
                  transition: 'all 0.2s',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'tasks' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Task Description</label>
                <textarea
                  value={taskInput}
                  onChange={e => setTaskInput(e.target.value)}
                  placeholder="e.g., write an email to a lead about our SaaS product"
                  style={{
                    padding: '8px 10px',
                    borderRadius: 4,
                    border: '1px solid rgba(32,214,199,0.2)',
                    background: 'rgba(0,0,0,0.2)',
                    color: '#F0E9D2',
                    fontSize: 11,
                    fontFamily: 'monospace',
                    minHeight: 60,
                    resize: 'none',
                  }}
                />
              </div>
              <button
                onClick={handleSubmitTask}
                disabled={!selected || !taskInput.trim() || loading}
                style={{
                  padding: '8px 12px',
                  borderRadius: 4,
                  border: 'none',
                  background: selected && taskInput.trim() && !loading ? 'linear-gradient(135deg,#FFD97A 0%,#E5C76B 40%,#B8923F 100%)' : 'rgba(229,199,107,0.1)',
                  color: selected && taskInput.trim() && !loading ? '#1a1000' : 'rgba(255,255,255,0.3)',
                  cursor: selected && taskInput.trim() && !loading ? 'pointer' : 'not-allowed',
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  transition: 'all 0.2s',
                }}
              >
                {loading ? 'SUBMITTING...' : 'SUBMIT TASK'}
              </button>
            </div>
          )}

          {tab === 'reinforce' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase' }}>Reward</label>
                  <span style={{ fontSize: 12, fontFamily: 'monospace', color: '#20D6C7' }}>{reward.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="-1"
                  max="1"
                  step="0.1"
                  value={reward}
                  onChange={e => setReward(parseFloat(e.target.value))}
                  style={{ cursor: 'pointer' }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Context (Optional)</label>
                <input
                  type="text"
                  value={context}
                  onChange={e => setContext(e.target.value)}
                  placeholder="e.g., handled objection well"
                  style={{
                    padding: '8px 10px',
                    borderRadius: 4,
                    border: '1px solid rgba(32,214,199,0.2)',
                    background: 'rgba(0,0,0,0.2)',
                    color: '#F0E9D2',
                    fontSize: 11,
                    fontFamily: 'monospace',
                  }}
                />
              </div>
              <button
                onClick={handleReinforce}
                disabled={!selected || loading}
                style={{
                  padding: '8px 12px',
                  borderRadius: 4,
                  border: 'none',
                  background: selected && !loading ? 'linear-gradient(135deg,#22C55E 0%,#16A34A 100%)' : 'rgba(34,197,94,0.1)',
                  color: selected && !loading ? '#f0f0f0' : 'rgba(255,255,255,0.3)',
                  cursor: selected && !loading ? 'pointer' : 'not-allowed',
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                }}
              >
                {loading ? 'APPLYING...' : 'APPLY REWARD'}
              </button>
            </div>
          )}

          {tab === 'parameters' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>
              <div>Behavioral parameters (not yet editable via UI)</div>
              <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: 4, fontFamily: 'monospace', fontSize: 10 }}>
                preferred_strategy: balanced<br />
                confidence_floor: 0.5<br />
                learning_rate_multiplier: 1.0
              </div>
            </div>
          )}

          {tab === 'history' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 10, maxHeight: 300, overflowY: 'auto' }}>
              {logs.filter(l => !selected || l.agent === selected).length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.3)' }}>No training events yet</div>
              ) : (
                logs.filter(l => !selected || l.agent === selected).map((log, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, paddingBottom: 6, borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.6)' }}>
                    <span style={{ color: 'rgba(255,255,255,0.3)', flexShrink: 0 }}>{log.ts}</span>
                    <span style={{ flex: 1 }}>
                      {log.type === 'task' ? `Task submitted: ${log.task.slice(0, 30)}...` : `Reward ${log.reward > 0 ? '+' : ''} ${log.reward.toFixed(2)}`}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}
        </Panel>
      </div>

      <div style={{ width: 260, display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
        <Panel title="Select Agent">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {agents.slice(0, 20).map(a => (
              <div
                key={a.id}
                onClick={() => setSelected(selected === a.id ? null : a.id)}
                style={{
                  padding: '8px 10px',
                  borderRadius: 4,
                  background: selected === a.id ? 'rgba(229,199,107,0.1)' : 'rgba(32,214,199,0.04)',
                  border: `1px solid ${selected === a.id ? 'rgba(229,199,107,0.3)' : 'rgba(32,214,199,0.1)'}`,
                  cursor: 'pointer',
                  fontSize: 10,
                  color: '#F0E9D2',
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 4, height: 4, borderRadius: '50%', background: selected === a.id ? '#E5C76B' : 'rgba(32,214,199,0.3)' }} />
                  <span style={{ flex: 1 }}>{a.id.slice(0, 16)}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Training Log">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 9, color: 'rgba(255,255,255,0.5)', maxHeight: 300, overflowY: 'auto' }}>
            {logs.length === 0 ? (
              <div style={{ color: 'rgba(255,255,255,0.3)' }}>No activity yet</div>
            ) : (
              logs.slice(-10).reverse().map((log, i) => (
                <div key={i} style={{ padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontFamily: 'monospace', color: 'rgba(255,255,255,0.3)' }}>{log.ts}</div>
                  <div>{log.type === 'task' ? '📝 Task' : '⚡ Reinforce'}: {log.agent.slice(0, 12)}</div>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>
    </div>
  )
}

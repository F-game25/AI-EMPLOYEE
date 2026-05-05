import { useState, useEffect } from 'react'
import { Panel, KPITile, HexButton, StatusPill } from '../nexus-ui'
import './TrainingPage.css'

const GRADE_COLORS = { 0: '#8B8B9E', 1: '#20D6C7', 2: '#E5C76B', 3: '#E5C76B', 4: '#22C55E', 5: '#22C55E' }
const GRADE_NAMES = ['Ungraded', 'Beginner', 'Basic', 'Mature', 'Advanced', 'Pro']

export default function TrainingPage() {
  const [agents, setAgents] = useState([])
  const [selected, setSelected] = useState(null)
  const [grade, setGrade] = useState(null)
  const [tab, setTab] = useState('tasks')
  const [taskInput, setTaskInput] = useState('')
  const [reward, setReward] = useState(0)
  const [context, setContext] = useState('')
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch('/api/agents/list')
      .then(r => r.json())
      .then(d => setAgents(d.agents || []))
      .catch(() => setAgents([]))
  }, [])

  useEffect(() => {
    if (!selected) return
    fetch(`/api/agents/${selected}/grade`)
      .then(r => r.json())
      .then(d => setGrade(d))
      .catch(() => setGrade(null))
  }, [selected])

  const gradeIdx = grade?.grade_index ?? 0
  const gradeName = grade?.grade || GRADE_NAMES[gradeIdx]
  const maxGrade = 5

  const handleSubmitTask = async () => {
    if (!selected || !taskInput.trim()) return
    setLoading(true)
    try {
      await fetch(`/api/agents/${selected}/ladder/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: taskInput, success: true }),
      })
      setLogs(prev => [...prev, { type: 'task', agent: selected, task: taskInput, ts: new Date().toLocaleTimeString() }])
      setTaskInput('')
      const res = await fetch(`/api/agents/${selected}/grade`)
      setGrade(await res.json())
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const handleReinforce = async () => {
    if (!selected) return
    setLoading(true)
    try {
      await fetch(`/api/agents/${selected}/reinforce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reward, context: context || selected }),
      })
      setLogs(prev => [...prev, { type: 'reinforce', agent: selected, reward, ts: new Date().toLocaleTimeString() }])
      setContext('')
      setReward(0)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  return (
    <div className="trp-page">
      <div className="trp-kpi-row">
        <KPITile label="Selected Agent" value={selected || '—'} sub="Training target" icon="🤖" iconTone="cool" />
        <KPITile label="Current Grade" value={gradeName} sub={`${gradeIdx}/${maxGrade}`} icon="📈"
          iconTone={gradeIdx >= 4 ? 'success' : gradeIdx >= 2 ? 'gold' : 'warn'} />
      </div>

      <div className="trp-main-grid">
        <div className="trp-left">
          <Panel title="Training Session" tone="gold" style={{ flex: 1 }}>
            <div className="trp-tabs">
              {['tasks', 'reinforce', 'parameters', 'history'].map(t => (
                <button key={t} onClick={() => setTab(t)} className={`trp-tab ${tab === t ? 'trp-tab--active' : ''}`}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>

            {tab === 'tasks' && (
              <div className="trp-tab-content">
                <div className="trp-form-group">
                  <label className="trp-label">Task Description</label>
                  <textarea value={taskInput} onChange={e => setTaskInput(e.target.value)}
                    placeholder="Describe the task to train on…" className="trp-textarea" />
                </div>
                <HexButton onClick={handleSubmitTask} disabled={!selected || !taskInput.trim() || loading}
                  variant="primary" tone="gold" full loading={loading}>
                  {loading ? 'SUBMITTING...' : 'SUBMIT TASK'}
                </HexButton>
              </div>
            )}

            {tab === 'reinforce' && (
              <div className="trp-tab-content">
                <div className="trp-form-group">
                  <div className="trp-label-row">
                    <label className="trp-label">Reward</label>
                    <span className="trp-reward-value">{reward.toFixed(2)}</span>
                  </div>
                  <input type="range" min="-1" max="1" step="0.1" value={reward}
                    onChange={e => setReward(parseFloat(e.target.value))} className="trp-slider" />
                </div>
                <div className="trp-form-group">
                  <label className="trp-label">Context (Optional)</label>
                  <input type="text" value={context} onChange={e => setContext(e.target.value)}
                    placeholder="e.g., handled objection well" className="trp-input" />
                </div>
                <HexButton onClick={handleReinforce} disabled={!selected || loading}
                  variant="primary" tone="success" full loading={loading}>
                  {loading ? 'APPLYING...' : 'APPLY REWARD'}
                </HexButton>
              </div>
            )}

            {tab === 'parameters' && (
              <div className="trp-tab-content">
                <div className="trp-param-note">Behavioral parameters (read-only)</div>
                <div className="trp-param-box">
                  <div>preferred_strategy: balanced</div>
                  <div>confidence_floor: 0.5</div>
                  <div>learning_rate_multiplier: 1.0</div>
                </div>
              </div>
            )}

            {tab === 'history' && (
              <div className="trp-history-list">
                {logs.length === 0 ? (
                  <div className="trp-empty">No training events yet</div>
                ) : (
                  logs.filter(l => !selected || l.agent === selected).reverse().map((log, i) => (
                    <div key={i} className="trp-history-item">
                      <span className="trp-history-ts">{log.ts}</span>
                      <span className="trp-history-text">
                        {log.type === 'task' ? `Task: ${log.task.slice(0, 28)}...` : `Reward ${log.reward > 0 ? '+' : ''}${log.reward.toFixed(2)}`}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}
          </Panel>
        </div>

        <div className="trp-right">
          <Panel title="Select Agent" tone="gold">
            <div className="trp-agent-list">
              {agents.slice(0, 20).map(a => (
                <div key={a.id} onClick={() => setSelected(selected === a.id ? null : a.id)}
                  className={`trp-agent-item ${selected === a.id ? 'trp-agent-item--active' : ''}`}>
                  <div className="trp-agent-dot" />
                  <span className="trp-agent-name">{a.id.slice(0, 16)}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Training Log" tone="gold" style={{ flex: 1, minHeight: 0 }}>
            <div className="trp-log-list">
              {logs.length === 0 ? (
                <div className="trp-empty">No activity yet</div>
              ) : (
                logs.slice(-10).reverse().map((log, i) => (
                  <div key={i} className="trp-log-item">
                    <div className="trp-log-ts">{log.ts}</div>
                    <div className="trp-log-text">{log.type === 'task' ? '📝 Task' : '⚡ Reward'}: {log.agent.slice(0, 12)}</div>
                    {log.type === 'reinforce' && <StatusPill label={`+${log.reward.toFixed(1)}`} tone="success" size="xs" />}
                  </div>
                ))
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

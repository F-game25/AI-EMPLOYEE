import { useState, useEffect } from 'react'
import { Panel, KPITile, HexButton, SectionLabel } from '../nexus-ui'
import './TrainingPage.css'

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
      await res.json()
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
      await fetch(`/api/agents/${selected}/reinforce`, {
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
    <div className="tr-page">
      <div className="tr-kpi-row">
        <KPITile
          label="Selected Agent"
          value={selected ? selected.slice(0, 12) : '—'}
          sub="Training target"
          icon="🤖"
          iconTone="cool"
        />
        <KPITile
          label="Current Grade"
          value={gradeName}
          sub={`${gradeValue}/${maxGrade}`}
          icon="📈"
          iconTone={gradeValue >= 4 ? 'success' : gradeValue >= 2 ? 'gold' : 'warn'}
        />
      </div>

      <div className="tr-main-grid">
        <div className="tr-left">
          <Panel title="Training Session" tone="gold" style={{ flex: 1 }}>
            <div className="tr-tabs">
              {[
                { id: 'tasks', label: 'Tasks' },
                { id: 'reinforce', label: 'Reinforce' },
                { id: 'parameters', label: 'Parameters' },
                { id: 'history', label: 'History' },
              ].map(t => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`tr-tab ${tab === t.id ? 'tr-tab--active' : ''}`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {tab === 'tasks' && (
              <div className="tr-tab-content">
                <div className="tr-form-group">
                  <label className="tr-label">Task Description</label>
                  <textarea
                    value={taskInput}
                    onChange={e => setTaskInput(e.target.value)}
                    placeholder="e.g., write an email to a lead about our SaaS product"
                    className="tr-textarea"
                  />
                </div>
                <HexButton
                  onClick={handleSubmitTask}
                  disabled={!selected || !taskInput.trim() || loading}
                  variant="primary"
                  tone="gold"
                  full
                  loading={loading}
                >
                  {loading ? 'SUBMITTING...' : 'SUBMIT TASK'}
                </HexButton>
              </div>
            )}

            {tab === 'reinforce' && (
              <div className="tr-tab-content">
                <div className="tr-form-group">
                  <div className="tr-label-row">
                    <label className="tr-label">Reward</label>
                    <span className="tr-reward-value">{reward.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="-1"
                    max="1"
                    step="0.1"
                    value={reward}
                    onChange={e => setReward(parseFloat(e.target.value))}
                    className="tr-slider"
                  />
                </div>
                <div className="tr-form-group">
                  <label className="tr-label">Context (Optional)</label>
                  <input
                    type="text"
                    value={context}
                    onChange={e => setContext(e.target.value)}
                    placeholder="e.g., handled objection well"
                    className="tr-input"
                  />
                </div>
                <HexButton
                  onClick={handleReinforce}
                  disabled={!selected || loading}
                  variant="primary"
                  tone="success"
                  full
                  loading={loading}
                >
                  {loading ? 'APPLYING...' : 'APPLY REWARD'}
                </HexButton>
              </div>
            )}

            {tab === 'parameters' && (
              <div className="tr-tab-content">
                <div className="tr-param-note">Behavioral parameters (not yet editable via UI)</div>
                <div className="tr-param-box">
                  <div>preferred_strategy: balanced</div>
                  <div>confidence_floor: 0.5</div>
                  <div>learning_rate_multiplier: 1.0</div>
                </div>
              </div>
            )}

            {tab === 'history' && (
              <div className="tr-history-list">
                {logs.filter(l => !selected || l.agent === selected).length === 0 ? (
                  <div className="tr-empty">No training events yet</div>
                ) : (
                  logs.filter(l => !selected || l.agent === selected).map((log, i) => (
                    <div key={i} className="tr-history-item">
                      <span className="tr-history-ts">{log.ts}</span>
                      <span className="tr-history-text">
                        {log.type === 'task' ? `Task submitted: ${log.task.slice(0, 30)}...` : `Reward ${log.reward > 0 ? '+' : ''} ${log.reward.toFixed(2)}`}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}
          </Panel>
        </div>

        <div className="tr-right">
          <Panel title="Select Agent" tone="gold" style={{ flex: 0, maxHeight: '50%', overflowY: 'auto' }}>
            <div className="tr-agent-list">
              {agents.slice(0, 20).map(a => (
                <div
                  key={a.id}
                  onClick={() => setSelected(selected === a.id ? null : a.id)}
                  className={`tr-agent-item ${selected === a.id ? 'tr-agent-item--active' : ''}`}
                >
                  <div className="tr-agent-dot" />
                  <span className="tr-agent-name">{a.id.slice(0, 16)}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Training Log" tone="gold" style={{ flex: 1, minHeight: 0 }}>
            <div className="tr-log-list">
              {logs.length === 0 ? (
                <div className="tr-empty">No activity yet</div>
              ) : (
                logs.slice(-10).reverse().map((log, i) => (
                  <div key={i} className="tr-log-item">
                    <div className="tr-log-ts">{log.ts}</div>
                    <div className="tr-log-text">{log.type === 'task' ? '📝 Task' : '⚡ Reinforce'}: {log.agent.slice(0, 12)}</div>
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

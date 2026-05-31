import { useState, useRef, useEffect } from 'react'
import { useTaskStore } from '../../store/taskStore'
import { useAppStore } from '../../store/appStore'
import { useCognitiveStore } from '../../store/cognitiveStore'
import './BottomDrawer.css'

const STAGES = ['pending', 'planning', 'running', 'validating', 'completed']
const STAGE_LABELS = { pending: 'INCOMING', planning: 'PLANNING', running: 'EXECUTING', validating: 'VALIDATING', completed: 'COMPLETED' }
const PRIORITY_MAP = { high: 'HIGH', medium: 'MED', low: 'LOW', critical: 'CRIT' }

function KanbanColumn({ stage, tasks = [] }) {
  return (
    <div className="bdrawer__column">
      <div className="bdrawer__col-header">
        <span className={`bdrawer__col-stage bdrawer__col-stage--${stage}`}>{STAGE_LABELS[stage]}</span>
        <span className="bdrawer__col-count">{tasks.length}</span>
      </div>
      <div className="bdrawer__col-tasks">
        {tasks.slice(0, 4).map((t, i) => (
          <div key={i} className="bdrawer__task-card">
            <div className="bdrawer__task-name">{t.description || t.task || t.name || 'Task'}</div>
            <div className="bdrawer__task-meta">
              {t.priority && <span className={`bdrawer__task-priority bdrawer__task-priority--${t.priority}`}>{PRIORITY_MAP[t.priority] || t.priority.toUpperCase()}</span>}
              {t.agent && <span className="bdrawer__task-agent">{t.agent}</span>}
            </div>
          </div>
        ))}
        {tasks.length > 4 && <div className="bdrawer__task-more">+{tasks.length - 4} more</div>}
      </div>
    </div>
  )
}

function TelemetryPanel({ label, unit, value, history }) {
  const pts = history.map((v, i) => {
    const x = (i / (history.length - 1)) * 96 + 2
    const maxV = Math.max(...history, 1)
    const y = 30 - (v / maxV) * 26
    return `${x},${y}`
  }).join(' ')

  const trend = history.length >= 2
    ? history[history.length - 1] - history[history.length - 2]
    : 0

  return (
    <div className="bdrawer__telemetry-panel">
      <div className="bdrawer__tele-label">{label}</div>
      <div className="bdrawer__tele-value">
        {typeof value === 'number' ? value.toFixed(1) : value}
        <span className="bdrawer__tele-unit">{unit}</span>
        <span className={`bdrawer__tele-trend ${trend > 0 ? 'bdrawer__tele-trend--up' : trend < 0 ? 'bdrawer__tele-trend--down' : ''}`}>
          {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'}
        </span>
      </div>
      <svg className="bdrawer__tele-chart" width="100" height="32" viewBox="0 0 100 32">
        <polyline points={pts} fill="none" stroke="rgba(255,184,0,0.6)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points={`${pts} 98,32 2,32`} fill="rgba(255,184,0,0.06)" stroke="none" />
      </svg>
    </div>
  )
}

export default function BottomDrawer() {
  const [isOpen, setIsOpen] = useState(false)
  const executionSteps = useTaskStore(s => s.executionSteps) || []
  const systemHealth = useAppStore(s => s.systemHealth) || {}
  const modelCalls = useCognitiveStore(s => s.modelCalls) || []

  // Group tasks by stage
  const grouped = STAGES.reduce((acc, stage) => {
    acc[stage] = executionSteps.filter(t => t.status === stage)
    return acc
  }, {})
  const counts = { pending: grouped.pending.length, planning: grouped.planning.length, running: grouped.running.length, validating: grouped.validating.length, completed: grouped.completed.length }
  const total = executionSteps.length

  // Rolling history for telemetry charts (12 points)
  const cpuHistory = useRef(new Array(12).fill(0))
  const ramHistory = useRef(new Array(12).fill(0))
  const thrHistory = useRef(new Array(12).fill(0))
  const latHistory = useRef(new Array(12).fill(0))

  useEffect(() => {
    cpuHistory.current = [...cpuHistory.current.slice(1), systemHealth.cpu_percent ?? 0]
    ramHistory.current = [...ramHistory.current.slice(1), systemHealth.memory_percent ?? 0]
    thrHistory.current = [...thrHistory.current.slice(1), modelCalls.length]
    latHistory.current = [...latHistory.current.slice(1), systemHealth.latency ?? 0]
  }, [systemHealth, modelCalls.length])

  return (
    <div className={`bdrawer ${isOpen ? 'bdrawer--open' : ''}`}>
      {/* Tab handle */}
      <div className="bdrawer__tab" onClick={() => setIsOpen(v => !v)}>
        <span className="bdrawer__tab-label">{isOpen ? '▼' : '▲'} TASK PIPELINE</span>
        <span className="bdrawer__tab-total">{total} TASKS</span>
        {isOpen && (
          <div className="bdrawer__stage-pills">
            {STAGES.map(s => (
              <span key={s} className={`bdrawer__stage-pill bdrawer__stage-pill--${s}`} data-count={counts[s] || 0}>
                {STAGE_LABELS[s]} <strong>{counts[s] || 0}</strong>
              </span>
            ))}
          </div>
        )}
        {!isOpen && (
          <div className="bdrawer__stage-counts">
            {STAGES.map(s => counts[s] > 0 && (
              <span key={s} className={`bdrawer__stage-mini bdrawer__stage-mini--${s}`} title={STAGE_LABELS[s]}>
                {counts[s]}
              </span>
            ))}
          </div>
        )}
        <span className="bdrawer__tab-chevron">{isOpen ? '▼' : '▲'}</span>
      </div>

      {/* Expanded content */}
      {isOpen && (
        <div className="bdrawer__content">
          <div className="bdrawer__pipeline">
            {STAGES.map(stage => (
              <KanbanColumn key={stage} stage={stage} tasks={grouped[stage]} />
            ))}
          </div>
          <div className="bdrawer__telemetry">
            <div className="bdrawer__tele-header">SYSTEM TELEMETRY <span>REAL-TIME</span></div>
            <div className="bdrawer__tele-grid">
              <TelemetryPanel label="CPU" unit="%" value={systemHealth.cpu_percent ?? 0} history={cpuHistory.current} />
              <TelemetryPanel label="MEMORY" unit="%" value={systemHealth.memory_percent ?? 0} history={ramHistory.current} />
              <TelemetryPanel label="THROUGHPUT" unit="calls" value={modelCalls.length} history={thrHistory.current} />
              <TelemetryPanel label="LATENCY" unit="ms" value={systemHealth.latency ?? 0} history={latHistory.current} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

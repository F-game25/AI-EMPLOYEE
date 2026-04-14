import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import PageHeader from '../layout/PageHeader'

const STATUS_CONFIG = {
  running: { color: 'var(--success)', label: 'Active', dot: 'dashboard-status-dot--active' },
  busy: { color: 'var(--warning)', label: 'Busy', dot: 'dashboard-status-dot--warning' },
  idle: { color: 'var(--text-muted)', label: 'Idle', dot: 'dashboard-status-dot--idle' },
}

const DEFAULT_AGENT_HEALTH = {
  running: 92,
  busy: 78,
  idle: 55,
}
const MAX_VISIBLE_AGENTS = 18
const MAX_VISIBLE_CHAT_MESSAGES = 20
const MAX_VISIBLE_LOGS = 14

function MetricCard({ label, value, hint, highlighted = false }) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.97 }}
      className={`dashboard-glass-card dashboard-metric-card${highlighted ? ' dashboard-metric-card--highlighted' : ''}`}
    >
      <div className="dashboard-metric-label">
        {label}
      </div>
      <div className="dashboard-metric-value">{value}</div>
      {hint && <div className="dashboard-metric-hint">{hint}</div>}
    </motion.div>
  )
}

function QuickAction({ label, onClick }) {
  return (
    <motion.button
      whileHover={{ y: -2, scale: 1.01 }}
      whileTap={{ scale: 0.97 }}
      className="dashboard-action-btn"
      onClick={onClick}
    >
      {label}
    </motion.button>
  )
}

function ActivityItem({ item, index, compact = false }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className="dashboard-activity-row"
      style={{ padding: compact ? '10px 12px' : '12px 14px' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, flex: 1 }}>
        <span className="dashboard-status-dot dashboard-status-dot--teal" />
        <div style={{ minWidth: 0 }}>
          <div className="dashboard-activity-text">{item?.notes || item?.message || 'System event'}</div>
          <div className="dashboard-activity-kind">{item?.kind || 'event'}</div>
        </div>
      </div>
      <span className="dashboard-activity-ts">
        {item?.ts ? new Date(item.ts).toLocaleTimeString('en-US', {
          hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
        }) : '--:--:--'}
      </span>
    </motion.div>
  )
}

function AgentPill({ agent, index }) {
  const cfg = STATUS_CONFIG[agent.status] || STATUS_CONFIG.idle
  const fallbackHealth = DEFAULT_AGENT_HEALTH[agent.status] ?? DEFAULT_AGENT_HEALTH.idle
  const health = Math.max(0, Math.min(100, Math.round(agent.health ?? fallbackHealth)))

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.02 }}
      whileHover={{ y: -1 }}
      whileTap={{ scale: 0.98 }}
      className={`dashboard-agent-pill${agent.status === 'running' ? ' dashboard-agent-pill--active' : ''}`}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span className={`dashboard-status-dot ${cfg.dot}`} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="dashboard-agent-name">{agent.name || agent.id}</div>
          <div className="dashboard-agent-task">{agent.current_task || 'Monitoring orchestration queue'}</div>
        </div>
        <span className="dashboard-agent-health">{health}%</span>
      </div>
    </motion.div>
  )
}

function RadialGauge({ label, value, color, ariaUnit = 'percent', displaySuffix = '%' }) {
  const size = 110
  const stroke = 8
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.max(0, Math.min(value, 100)) / 100) * circumference

  return (
    <div className="dashboard-gauge">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label} ${Math.round(value)} ${ariaUnit}`}>
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          style={{ filter: `drop-shadow(0 0 8px ${color})` }}
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="dashboard-gauge-center">
        <span className="dashboard-gauge-value">{Math.round(value)}{displaySuffix}</span>
        <span className="dashboard-gauge-label">{label}</span>
      </div>
    </div>
  )
}

function ParticleMap({ compact = false }) {
  const particles = useMemo(
    () => Array.from({ length: compact ? 14 : 26 }, (_, i) => ({
      id: i,
      left: `${(i * 37) % 96 + 2}%`,
      top: `${(i * 23) % 86 + 5}%`,
      size: 4 + (i % 4),
      duration: 7 + (i % 6) * 0.7,
      delay: i * 0.14,
      amber: i % 3 === 0,
    })),
    [compact]
  )

  return (
    <div className={`dashboard-particle-map${compact ? ' dashboard-particle-map--compact' : ''}`}>
      <div className="dashboard-map-grid" />
      {particles.map((particle) => (
        <motion.span
          key={particle.id}
          className={`dashboard-particle${particle.amber ? ' dashboard-particle--amber' : ''}`}
          style={{ left: particle.left, top: particle.top, width: particle.size, height: particle.size }}
          animate={{
            y: [0, -8, 0],
            opacity: [0.45, 1, 0.45],
          }}
          transition={{
            duration: particle.duration,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: particle.delay,
          }}
        />
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState('chat')
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const systemStatus = useAppStore(s => s.systemStatus)
  const agents = useAppStore(s => s.agents)
  const activityFeed = useAppStore(s => s.activityFeed)
  const executionLogs = useAppStore(s => s.executionLogs)
  const chatMessages = useAppStore(s => s.chatMessages)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const isTyping = useAppStore(s => s.isTyping)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const wsConnected = useAppStore(s => s.wsConnected)
  const nnStatus = useAppStore(s => s.nnStatus)
  const brainInsights = useAppStore(s => s.brainInsights)
  const { sendMessage } = useWebSocket()

  const BASE = window.location.origin

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, isTyping])

  const handleSend = () => {
    const text = input.trim()
    if (!text) return
    addChatMessage({ role: 'user', content: text, ts: Date.now() })
    sendMessage(text)
    setInput('')
  }

  const normalizedAgents = useMemo(
    () =>
      (agents || []).map(agent => ({
        ...agent,
        status: agent.status ?? agent.state,
        current_task: agent.current_task ?? agent.task,
      })),
    [agents]
  )
  const activeAgents = useMemo(
    () => normalizedAgents.filter(a => a.status === 'running' || a.status === 'busy'),
    [normalizedAgents]
  )
  const totalAgents = systemStatus?.total_agents || agents?.length || 0
  const runningAgents = systemStatus?.running_agents ?? activeAgents.length
  const stoppedAgents = Math.max(totalAgents - runningAgents, 0)

  const metrics = [
    { label: 'Active Agents', value: runningAgents, hint: `${Math.round((runningAgents / Math.max(totalAgents, 1)) * 100)}% utilization` },
    { label: 'Total Agents', value: totalAgents, hint: 'Fleet capacity' },
    { label: 'Stopped Agents', value: stoppedAgents, hint: 'Standby / idle' },
    { label: 'Gateway Status', value: wsConnected ? 'ONLINE' : 'OFFLINE', hint: wsConnected ? 'Realtime link stable' : 'Reconnect required', highlighted: true },
  ]

  const healthItems = [
    { label: 'CPU', value: systemStatus?.cpu_usage ?? 0, color: 'var(--neon-teal)', ariaUnit: 'percent', displaySuffix: '%' },
    { label: 'RAM', value: systemStatus?.memory ?? 0, color: 'var(--neon-amber)', ariaUnit: 'percent', displaySuffix: '%' },
    { label: 'GPU', value: systemStatus?.gpu_usage ?? 0, color: 'var(--neon-cyan)', ariaUnit: 'percent', displaySuffix: '%' },
    { label: 'Temp', value: Math.min(100, Math.round(systemStatus?.cpu_temperature ?? 0)), color: 'var(--warning)', ariaUnit: 'degrees celsius', displaySuffix: '°C' },
  ]

  return (
    <div className="page-enter dashboard-overview">
      <PageHeader
        title="Overview"
        subtitle="AI Employee control center"
      />

      <div className="dashboard-metrics-grid">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="dashboard-main-grid">
        <section className="dashboard-glass-card dashboard-panel">
          <div className="dashboard-panel-header">
            <h2>Agents</h2>
            <span>{activeAgents.length} active</span>
          </div>
          <div className="dashboard-agents-scroll">
            {activeAgents.length === 0 ? (
              <div className="dashboard-empty">No active agents online</div>
            ) : activeAgents.slice(0, MAX_VISIBLE_AGENTS).map((agent, idx) => (
              <AgentPill key={agent.id || agent.name || idx} agent={agent} index={idx} />
            ))}
          </div>
        </section>

        <section className="dashboard-glass-card dashboard-panel dashboard-panel-center">
          <div className="dashboard-panel-header">
            <h2>Orchestrator</h2>
            <div className="dashboard-tabs" role="tablist" aria-label="Orchestrator views">
              {[{ id: 'chat', label: 'chat' }, { id: 'live-map', label: 'live map' }, { id: 'logs', label: 'logs' }].map((tab) => (
                <button
                  key={tab.id}
                  className={`dashboard-tab-btn${activeTab === tab.id ? ' dashboard-tab-btn--active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  aria-controls={`orchestrator-panel-${tab.id}`}
                  id={`orchestrator-tab-${tab.id}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div
            className="dashboard-tab-content"
            role="tabpanel"
            id={`orchestrator-panel-${activeTab}`}
            aria-labelledby={`orchestrator-tab-${activeTab}`}
          >
            {activeTab === 'chat' && (
              <div className="dashboard-chat-panel">
                <div className="dashboard-chat-messages">
                  {chatMessages.length === 0 && !isTyping && (
                    <div className="dashboard-empty">Start the conversation with your orchestrator</div>
                  )}
                  <AnimatePresence initial={false}>
                    {chatMessages.slice(-MAX_VISIBLE_CHAT_MESSAGES).map((msg, idx) => (
                      <motion.div
                        key={`${msg.ts || idx}-${idx}`}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                        className={`dashboard-msg-row ${msg.role === 'user' ? 'dashboard-msg-row--user' : ''}`}
                      >
                        <div className={`dashboard-msg-bubble ${msg.role === 'user' ? 'dashboard-msg-bubble--user' : ''}`}>
                          {msg.content}
                        </div>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  {isTyping && <div className="dashboard-msg-typing">Orchestrator is thinking…</div>}
                  <div ref={messagesEndRef} />
                </div>
                <div className="dashboard-chat-input-wrap">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        handleSend()
                      }
                    }}
                    className="dashboard-chat-input"
                    placeholder="Send instruction..."
                    aria-label="Chat message input"
                  />
                  <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} className="dashboard-send-btn" onClick={handleSend} aria-label="Send message">
                    Send
                  </motion.button>
                </div>
              </div>
            )}

            {activeTab === 'live-map' && (
              <div style={{ height: '100%' }}>
                <ParticleMap compact />
              </div>
            )}

            {activeTab === 'logs' && (
              <div className="dashboard-log-stream">
                {executionLogs.length === 0
                  ? <div className="dashboard-empty">No logs captured yet</div>
                  : executionLogs.slice(0, MAX_VISIBLE_LOGS).map((item, idx) => <ActivityItem key={item.id || idx} item={item} index={idx} compact />)}
              </div>
            )}
          </div>
        </section>

        <section className="dashboard-side-column">
          <div className="dashboard-glass-card dashboard-panel">
            <div className="dashboard-panel-header">
              <h2>Quick Actions</h2>
            </div>
            <div className="dashboard-actions-grid">
              <QuickAction label="Open AI Control" onClick={() => setActiveSection('ai-control')} />
              <QuickAction label="Manage Agents" onClick={() => setActiveSection('agents')} />
              <QuickAction label="View Operations" onClick={() => setActiveSection('operations')} />
              <QuickAction label="System Settings" onClick={() => setActiveSection('system')} />
            </div>
          </div>

          <div className="dashboard-glass-card dashboard-panel">
            <div className="dashboard-panel-header">
              <h2>Command Center</h2>
            </div>
            <div className="dashboard-actions-grid">
              <QuickAction label="⚡ Hermes Agent" onClick={() => {
                addChatMessage({ role: 'user', content: 'Activate Hermes agent for rapid task execution', ts: Date.now() })
                sendMessage('Activate Hermes agent for rapid task execution')
              }} />
              <QuickAction label="◉ Blacklight Mode" onClick={() => {
                fetch(`${BASE}/api/agents/mode`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ mode: 'BLACKLIGHT' }),
                }).catch(() => {})
                addChatMessage({ role: 'user', content: 'Activating BLACKLIGHT mode — all agents online', ts: Date.now() })
                sendMessage('Activating BLACKLIGHT mode — all agents online')
              }} />
              <QuickAction label="🔺 Ascend Forge" onClick={() => {
                fetch(`${BASE}/api/self-improvement/queue`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ task_type: 'self_improvement', description: 'Ascend Forge: optimize strategies and evolve' }),
                }).catch(() => {})
                addChatMessage({ role: 'user', content: 'Launching Ascend Forge — self-improvement pipeline activated', ts: Date.now() })
                sendMessage('Launching Ascend Forge — self-improvement pipeline activated')
              }} />
              <QuickAction label="💰 Money Mode" onClick={() => {
                fetch(`${BASE}/api/agents/mode`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ mode: 'MONEYMODE' }),
                }).catch(() => {})
                addChatMessage({ role: 'user', content: 'Engaging MONEYMODE — revenue-optimized operations', ts: Date.now() })
                sendMessage('Engaging MONEYMODE — revenue-optimized operations')
              }} />
            </div>
          </div>

          <div className="dashboard-glass-card dashboard-panel">
            <div className="dashboard-panel-header">
              <h2>Neural Brain</h2>
              <span style={{ color: nnStatus?.active ? 'var(--success)' : 'var(--text-muted)', fontSize: '11px' }}>
                {nnStatus?.active ? '● Live' : '○ Idle'}
              </span>
            </div>
            <div className="dashboard-brain-mini">
              <div className="dashboard-brain-row">
                <span className="dashboard-brain-label">Confidence</span>
                <span className="dashboard-brain-value" style={{ color: 'var(--gold)' }}>
                  {Math.round((nnStatus?.confidence ?? 0) * 100)}%
                </span>
              </div>
              <div className="dashboard-brain-bar">
                <motion.div
                  className="dashboard-brain-bar-fill"
                  style={{ background: 'var(--gold)' }}
                  animate={{ width: `${Math.round((nnStatus?.confidence ?? 0) * 100)}%` }}
                  transition={{ duration: 0.6 }}
                />
              </div>
              <div className="dashboard-brain-row">
                <span className="dashboard-brain-label">Learn Step</span>
                <span className="dashboard-brain-value">{(nnStatus?.learn_step ?? 0).toLocaleString()}</span>
              </div>
              <div className="dashboard-brain-row">
                <span className="dashboard-brain-label">Success Rate</span>
                <span className="dashboard-brain-value" style={{ color: 'var(--success)' }}>
                  {brainInsights?.performance_metrics?.success_rate
                    ? `${Math.round(brainInsights.performance_metrics.success_rate * 100)}%`
                    : '—'}
                </span>
              </div>
              <div className="dashboard-brain-row">
                <span className="dashboard-brain-label">Strategies</span>
                <span className="dashboard-brain-value">{brainInsights?.learned_strategies?.length ?? 0}</span>
              </div>
            </div>
          </div>

          <div className="dashboard-glass-card dashboard-panel">
            <div className="dashboard-panel-header">
              <h2>System Health</h2>
              <span>Live</span>
            </div>
              <div className="dashboard-health-grid">
                {healthItems.map((item) => (
                  <RadialGauge key={item.label} label={item.label} value={item.value} color={item.color} ariaUnit={item.ariaUnit} displaySuffix={item.displaySuffix} />
                ))}
              </div>
          </div>
        </section>
      </div>

      <section className="dashboard-glass-card dashboard-map-section">
        <div className="dashboard-panel-header">
          <h2>Live Activity Map</h2>
          <span>Heartbeat {systemStatus?.heartbeat ?? 0}</span>
        </div>
        <ParticleMap />
        <div className="dashboard-map-feed">
          {(activityFeed || []).slice(0, 3).map((item, idx) => (
            <ActivityItem key={item.id || idx} item={item} index={idx} />
          ))}
          {activityFeed.length === 0 && (
            <div className="dashboard-empty">No live events streaming</div>
          )}
        </div>
      </section>
    </div>
  )
}

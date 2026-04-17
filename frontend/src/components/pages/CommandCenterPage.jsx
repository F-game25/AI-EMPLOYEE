import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'
import { sendChatMessage } from '../../hooks/useWebSocket'
import { eventBus, EVENTS } from '../../utils/eventBus'

const BASE = API_URL

const SUBSYSTEM_TAG = {
  core_brain: { label: 'CORE BRAIN AGENT', color: 'var(--gold)' },
  brain: { label: 'NEURAL BRAIN', color: 'var(--info)' },
  memory: { label: 'MEMORY', color: 'var(--success)' },
  doctor: { label: 'DOCTOR', color: 'var(--warning)' },
}

function identifySubsystem(content) {
  const lower = (content || '').toLowerCase()
  if (lower.includes('[neural') || lower.includes('[brain')) return SUBSYSTEM_TAG.brain
  if (lower.includes('[memory')) return SUBSYSTEM_TAG.memory
  if (lower.includes('[doctor')) return SUBSYSTEM_TAG.doctor
  return SUBSYSTEM_TAG.core_brain
}

function ChatMessage({ msg, index }) {
  const isUser = msg.role === 'user'
  const tag = !isUser ? identifySubsystem(msg.content) : null

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.02, 0.3) }}
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 'var(--space-2)',
      }}
    >
      <div style={{
        maxWidth: '85%',
        padding: 'var(--space-3) var(--space-4)',
        borderRadius: isUser ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
        background: isUser ? 'rgba(212, 175, 55, 0.1)' : 'var(--bg-card)',
        border: `1px solid ${isUser ? 'rgba(212, 175, 55, 0.2)' : 'var(--border-subtle)'}`,
      }}>
        {tag && (
          <div style={{
            fontSize: '10px',
            color: tag.color,
            marginBottom: '4px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            fontWeight: 500,
          }}>
            {tag.label}
          </div>
        )}
        <div style={{ fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
          {msg.content}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
          {msg.ts ? new Date(msg.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
        </div>
      </div>
    </motion.div>
  )
}

function TaskQueuePanel({ tasks }) {
  const statusColor = { pending: 'var(--text-muted)', running: 'var(--warning)', completed: 'var(--success)', failed: 'var(--error)' }
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
        Task Queue
      </h3>
      {tasks.length === 0 ? (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-4) 0' }}>
          No tasks in queue
        </div>
      ) : (
        tasks.slice(0, 10).map((task, i) => (
          <div key={task.id || i} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            padding: 'var(--space-2) 0',
            borderBottom: '1px solid var(--border-subtle)',
            fontSize: '12px',
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: statusColor[task.status] || 'var(--text-muted)',
              flexShrink: 0,
            }} />
            <span style={{ flex: 1, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {task.description || task.id}
            </span>
            <span style={{ color: statusColor[task.status] || 'var(--text-muted)', fontSize: '11px' }}>
              {task.status}
            </span>
          </div>
        ))
      )}
    </div>
  )
}

function AgentRoutingPanel({ agents }) {
  const statusColor = { idle: 'var(--text-muted)', active: 'var(--success)', running: 'var(--success)', error: 'var(--error)', busy: 'var(--warning)' }
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
        Agent Routing
      </h3>
      {(!agents || agents.length === 0) ? (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-4) 0' }}>
          No agents registered
        </div>
      ) : (
        agents.slice(0, 8).map((agent, i) => (
          <div key={agent.id || i} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            padding: 'var(--space-2) 0',
            borderBottom: '1px solid var(--border-subtle)',
            fontSize: '12px',
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: statusColor[agent.status] || 'var(--text-muted)',
              flexShrink: 0,
            }} />
            <span style={{ flex: 1, color: 'var(--text-primary)' }}>
              {agent.name || agent.id}
            </span>
            <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
              {agent.type || 'general'}
            </span>
          </div>
        ))
      )}
    </div>
  )
}

function BrainStatusCard({ brainStatus, brainInsights }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        <span style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: brainStatus?.active ? 'var(--success)' : 'var(--text-muted)',
        }} />
        <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
          Core Brain Agent
        </h3>
        <span style={{ fontSize: '11px', color: brainStatus?.active ? 'var(--success)' : 'var(--text-muted)', marginLeft: 'auto' }}>
          {brainStatus?.status || 'unknown'}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-muted)' }}>Memory Size</span>
          <span style={{ color: 'var(--text-primary)' }}>{brainStatus?.memory_size ?? 0}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-muted)' }}>Strategies</span>
          <span style={{ color: 'var(--text-primary)' }}>{brainInsights?.learned_strategies?.length ?? 0}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-muted)' }}>Decisions</span>
          <span style={{ color: 'var(--text-primary)' }}>{brainInsights?.decisions?.length ?? 0}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-muted)' }}>Success Rate</span>
          <span style={{ color: 'var(--success)' }}>
            {brainInsights?.performance_metrics?.success_rate
              ? `${Math.round(brainInsights.performance_metrics.success_rate * 100)}%`
              : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}

export default function CommandCenterPage() {
  const [input, setInput] = useState('')
  const [taskQueue, setTaskQueue] = useState([])
  const [offlineMode, setOfflineMode] = useState(false)
  const messagesEndRef = useRef(null)
  const chatMessages = useAppStore(s => s.chatMessages)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const isTyping = useAppStore(s => s.isTyping)
  const agents = useAppStore(s => s.agents)
  const brainStatus = useAppStore(s => s.brainStatus)
  const brainInsights = useAppStore(s => s.brainInsights)
  const wsConnected = useAppStore(s => s.wsConnected)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, isTyping])

  // Poll task queue from backend
  useEffect(() => {
    const controller = new AbortController()
    const fetchQueue = async () => {
      try {
        const res = await fetch(`${BASE}/api/tasks/queue`, { signal: controller.signal })
        if (res.ok) {
          const data = await res.json()
          setTaskQueue(Array.isArray(data?.tasks) ? data.tasks : Array.isArray(data) ? data : [])
          setOfflineMode(false)
        }
      } catch {
        setOfflineMode(true)
      }
    }
    fetchQueue()
    const i = setInterval(fetchQueue, 4000)
    return () => { clearInterval(i); controller.abort() }
  }, [])

  // Subscribe to navigation events from event bus
  useEffect(() => {
    return eventBus.on(EVENTS.NAVIGATE_TO, ({ path }) => {
      if (path === '/command-center') {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }
    })
  }, [])

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text) return
    addChatMessage({ role: 'user', content: text, ts: Date.now() })
    sendChatMessage(text)
    setInput('')
    // Optimistically add to task queue
    setTaskQueue((prev) => [
      { id: `task-${Date.now()}`, description: text, status: 'pending' },
      ...prev,
    ])
  }, [input, addChatMessage])

  const dispatchDirective = useCallback(async (directive) => {
    addChatMessage({ role: 'user', content: directive, ts: Date.now() })
    sendChatMessage(directive)
    try {
      await fetch(`${BASE}/api/brain/directive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directive }),
      })
    } catch {
      // Backend offline — message queued via WebSocket if/when connected
    }
  }, [addChatMessage])

  const QUICK_DIRECTIVES = [
    { label: 'System Status', cmd: 'report full system status' },
    { label: 'Agent Summary', cmd: 'summarize all active agents and their tasks' },
    { label: 'Brain Insights', cmd: 'show recent brain decisions and learned strategies' },
    { label: 'Error Report', cmd: 'list all recent errors and warnings' },
  ]

  return (
    <div className="page-enter">
      <PageHeader
        title="Command Center"
        subtitle="Core Brain Agent — task routing, decisions, agent coordination"
      />

      {!wsConnected && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)',
          marginBottom: 'var(--space-4)',
          background: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.2)',
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: 'var(--error)',
        }}>
          ⚠ OFFLINE MODE — WebSocket disconnected. Commands will queue for reconnect.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 'var(--space-4)', height: 'calc(100vh - 220px)', minHeight: '500px' }}>
        {/* Main chat / command interface */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', minHeight: 0 }}>
          {/* Brain status bar */}
          <BrainStatusCard brainStatus={brainStatus} brainInsights={brainInsights} />

          {/* Quick directives */}
          <div className="ds-card" style={{ padding: 'var(--space-3)' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: 'var(--space-2)' }}>Quick Directives</div>
            <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
              {QUICK_DIRECTIVES.map((d) => (
                <motion.button
                  key={d.label}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => dispatchDirective(d.cmd)}
                  style={{
                    padding: 'var(--space-1) var(--space-3)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    background: 'transparent',
                    color: 'var(--text-secondary)',
                    fontSize: '12px',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'all 150ms',
                  }}
                >
                  {d.label}
                </motion.button>
              ))}
            </div>
          </div>

          {/* Chat messages */}
          <div className="ds-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 'var(--space-4)', minHeight: 0 }}>
            <div style={{ flex: 1, overflowY: 'auto', marginBottom: 'var(--space-3)' }}>
              {chatMessages.length === 0 && !isTyping && (
                <div style={{ fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-6) 0' }}>
                  Send a directive to the Core Brain Agent
                </div>
              )}
              <AnimatePresence initial={false}>
                {chatMessages.slice(-30).map((msg, idx) => (
                  <ChatMessage key={`${msg.ts || idx}-${idx}`} msg={msg} index={idx} />
                ))}
              </AnimatePresence>
              {isTyping && (
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic', padding: 'var(--space-2) 0' }}>
                  Core Brain Agent is thinking…
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
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
                style={{
                  flex: 1,
                  padding: 'var(--space-3)',
                  background: 'var(--bg-base)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text-primary)',
                  fontSize: '13px',
                  fontFamily: 'inherit',
                  outline: 'none',
                }}
                placeholder="Enter directive for Core Brain Agent..."
                aria-label="Command input"
              />
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleSend}
                style={{
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'rgba(212, 175, 55, 0.1)',
                  border: '1px solid rgba(212, 175, 55, 0.3)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--gold)',
                  fontSize: '13px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                Dispatch
              </motion.button>
            </div>
          </div>
        </div>

        {/* Right panel — routing + queue */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', minHeight: 0, overflowY: 'auto' }}>
          {offlineMode && (
            <div style={{
              padding: 'var(--space-2) var(--space-3)',
              background: 'rgba(245, 158, 11, 0.08)',
              border: '1px solid rgba(245, 158, 11, 0.2)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              color: 'var(--warning)',
            }}>
              OFFLINE MODE — task queue unavailable
            </div>
          )}
          <AgentRoutingPanel agents={agents} />
          <TaskQueuePanel tasks={taskQueue} />
        </div>
      </div>
    </div>
  )
}

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'

const BASE = window.location.origin

const SUBSYSTEM_TAG = {
  orchestrator: { label: 'ORCHESTRATOR', color: 'var(--gold)' },
  brain: { label: 'NEURAL BRAIN', color: 'var(--info)' },
  memory: { label: 'MEMORY', color: 'var(--success)' },
  doctor: { label: 'DOCTOR', color: 'var(--warning)' },
}

function identifySubsystem(content) {
  const lower = (content || '').toLowerCase()
  if (lower.includes('[neural') || lower.includes('[brain')) return SUBSYSTEM_TAG.brain
  if (lower.includes('[memory')) return SUBSYSTEM_TAG.memory
  if (lower.includes('[doctor')) return SUBSYSTEM_TAG.doctor
  return null
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
        <div style={{
          fontSize: '13px',
          color: 'var(--text-primary)',
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          {msg.content}
        </div>
      </div>
    </motion.div>
  )
}

function TypingIndicator() {
  return (
    <div style={{
      display: 'flex',
      gap: '4px',
      padding: 'var(--space-3) var(--space-4)',
    }}>
      {[0, 1, 2].map(i => (
        <motion.span
          key={i}
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.2 }}
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: 'var(--gold)',
          }}
        />
      ))}
    </div>
  )
}

function BrainInsightCard({ insights }) {
  const metrics = insights?.performance_metrics || {}
  const strategies = insights?.learned_strategies || []

  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
        Neural Brain Insights
      </h3>

      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        <div style={{ padding: 'var(--space-2)', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Success Rate</div>
          <div style={{ fontSize: '16px', fontWeight: 500, color: 'var(--success)' }}>
            {metrics.success_rate ? `${Math.round(metrics.success_rate * 100)}%` : '—'}
          </div>
        </div>
        <div style={{ padding: 'var(--space-2)', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Confidence</div>
          <div style={{ fontSize: '16px', fontWeight: 500, color: 'var(--gold)' }}>
            {metrics.confidence ? `${Math.round(metrics.confidence * 100)}%` : '—'}
          </div>
        </div>
      </div>

      {/* Strategies */}
      {strategies.length > 0 && (
        <div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 'var(--space-1)' }}>
            Learned Strategies
          </div>
          {strategies.slice(0, 3).map((s, i) => (
            <div key={i} style={{
              fontSize: '12px',
              color: 'var(--text-secondary)',
              padding: '4px 0',
              borderTop: i > 0 ? '1px solid var(--border-subtle)' : 'none',
            }}>
              {typeof s === 'string' ? s : s.name || s.strategy || JSON.stringify(s)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DecisionFlowCard({ activity }) {
  const decisions = activity?.recent_decisions || activity?.items || []
  if (decisions.length === 0) return null

  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
        Decision Flow
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        {decisions.slice(0, 5).map((d, i) => (
          <div key={i} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            fontSize: '12px',
          }}>
            <span style={{
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              background: 'rgba(212, 175, 55, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10px',
              color: 'var(--gold)',
              flexShrink: 0,
            }}>
              {i + 1}
            </span>
            <span style={{ color: 'var(--text-secondary)' }}>
              {typeof d === 'string' ? d : d.action || d.decision || d.description || JSON.stringify(d)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function NeuralNetworkLive({ nnStatus }) {
  const confidence = Math.round((nnStatus?.confidence ?? 0) * 100)
  const bufferPct = nnStatus?.max_buffer_size
    ? Math.round((nnStatus.buffer_size / nnStatus.max_buffer_size) * 100)
    : 0
  const recentOutputs = nnStatus?.recent_outputs || []
  const recentLearning = nnStatus?.recent_learning_events || []

  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
        <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
          Neural Network
        </h3>
        <span style={{
          fontSize: '11px',
          padding: '2px 8px',
          borderRadius: '4px',
          background: nnStatus?.active ? 'rgba(34,197,94,0.1)' : 'rgba(102,102,112,0.1)',
          color: nnStatus?.active ? 'var(--success)' : 'var(--text-muted)',
        }}>
          {nnStatus?.mode || 'UNKNOWN'}
        </span>
      </div>

      {/* Confidence bar */}
      <div style={{ marginBottom: 'var(--space-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Confidence</span>
          <span style={{ color: 'var(--gold)' }}>{confidence}%</span>
        </div>
        <div style={{ height: '6px', background: 'var(--bg-base)', borderRadius: '3px', overflow: 'hidden' }}>
          <motion.div
            animate={{ width: `${confidence}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            style={{ height: '100%', background: 'var(--gold)', borderRadius: '3px', boxShadow: '0 0 8px rgba(212,175,55,0.4)' }}
          />
        </div>
      </div>

      {/* Buffer bar */}
      <div style={{ marginBottom: 'var(--space-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Replay Buffer</span>
          <span style={{ color: 'var(--neon-teal)' }}>{(nnStatus?.buffer_size ?? 0).toLocaleString()} / {(nnStatus?.max_buffer_size ?? 0).toLocaleString()}</span>
        </div>
        <div style={{ height: '6px', background: 'var(--bg-base)', borderRadius: '3px', overflow: 'hidden' }}>
          <motion.div
            animate={{ width: `${bufferPct}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            style={{ height: '100%', background: 'var(--neon-teal)', borderRadius: '3px', boxShadow: '0 0 8px rgba(32,214,199,0.3)' }}
          />
        </div>
      </div>

      {/* Stats grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        {[
          { label: 'Learn Step', value: (nnStatus?.learn_step ?? 0).toLocaleString() },
          { label: 'Experiences', value: (nnStatus?.experiences ?? 0).toLocaleString() },
          { label: 'Loss', value: nnStatus?.last_loss != null ? nnStatus.last_loss.toFixed(4) : '—', color: 'var(--neon-cyan)' },
          { label: 'Device', value: (nnStatus?.device ?? 'cpu').toUpperCase() },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ padding: 'var(--space-2)', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>{label}</div>
            <div style={{ fontSize: '14px', fontWeight: 500, color: color || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Recent decisions */}
      {recentOutputs.length > 0 && (
        <div style={{ marginBottom: 'var(--space-2)' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 'var(--space-1)' }}>Recent Decisions</div>
          {recentOutputs.slice(0, 3).map((item, i) => (
            <div key={i} style={{ fontSize: '12px', color: 'var(--text-secondary)', padding: '3px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--gold)', fontSize: '10px' }}>›</span>
              {typeof item === 'string' ? item : item.action || item.decision || JSON.stringify(item)}
            </div>
          ))}
        </div>
      )}

      {/* Recent learning */}
      {recentLearning.length > 0 && (
        <div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 'var(--space-1)' }}>Recent Learning</div>
          {recentLearning.slice(0, 3).map((item, i) => (
            <div key={i} style={{ fontSize: '12px', color: 'var(--text-secondary)', padding: '3px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--neon-teal)', fontSize: '10px' }}>●</span>
              {typeof item === 'string' ? item : item.event || item.type || JSON.stringify(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AIControlPage() {
  const chatMessages = useAppStore(s => s.chatMessages)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const isTyping = useAppStore(s => s.isTyping)
  const setTyping = useAppStore(s => s.setTyping)
  const ws = useAppStore(s => s.ws)
  const brainInsights = useAppStore(s => s.brainInsights)
  const brainActivity = useAppStore(s => s.brainActivity)
  const nnStatus = useAppStore(s => s.nnStatus)

  const [input, setInput] = useState('')
  const scrollRef = useRef(null)

  // Poll neural network status for live updates
  useEffect(() => {
    const controller = new AbortController()
    const fetchNN = async () => {
      try {
        const res = await fetch(`${BASE}/api/brain/status`, { signal: controller.signal })
        const data = await res.json()
        if (data) useAppStore.getState().setNnStatus(data)
      } catch { /* ignore */ }
    }
    fetchNN()
    const i = setInterval(fetchNN, 3000)
    return () => { clearInterval(i); controller.abort() }
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [chatMessages, isTyping])

  const sendMessage = useCallback(() => {
    const text = input.trim()
    if (!text) return
    setInput('')
    addChatMessage({ role: 'user', content: text })
    setTyping(true)

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'chat', message: text }))
    } else {
      // HTTP fallback
      fetch(`${BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
        .then(r => r.json())
        .then(data => {
          addChatMessage({ role: 'ai', content: data.reply || data.message || 'No response.' })
          setTyping(false)
        })
        .catch(() => {
          addChatMessage({ role: 'ai', content: 'Connection error. Please try again.' })
          setTyping(false)
        })
    }
  }, [input, ws, addChatMessage, setTyping])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="page-enter" style={{ display: 'flex', gap: 'var(--space-4)', height: '100%' }}>
      {/* Main Chat */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
      }}>
        <PageHeader title="AI Control" subtitle="Chat with your AI employee and monitor neural brain" />

        {/* Chat messages */}
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: 'var(--space-2)',
            marginBottom: 'var(--space-3)',
          }}
        >
          {chatMessages.length === 0 && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: 'var(--text-muted)',
              fontSize: '14px',
            }}>
              Start a conversation with your AI employee
            </div>
          )}
          {chatMessages.map((msg, idx) => (
            <ChatMessage key={idx} msg={msg} index={idx} />
          ))}
          {isTyping && <TypingIndicator />}
        </div>

        {/* Input */}
        <div style={{
          display: 'flex',
          gap: 'var(--space-2)',
          padding: 'var(--space-3)',
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-subtle)',
        }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message or command..."
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--text-primary)',
              fontSize: '14px',
              fontFamily: 'inherit',
            }}
          />
          <button
            className="btn-primary"
            onClick={sendMessage}
            disabled={!input.trim()}
            style={{ flexShrink: 0 }}
          >
            Send
          </button>
        </div>
      </div>

      {/* Right rail — Brain insights + Neural Network live */}
      <div style={{
        width: '340px',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
        overflowY: 'auto',
      }}>
        <NeuralNetworkLive nnStatus={nnStatus} />
        <BrainInsightCard insights={brainInsights} />
        <DecisionFlowCard activity={brainActivity} />
      </div>
    </div>
  )
}

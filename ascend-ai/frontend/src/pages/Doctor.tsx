import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store/ascendStore'
import { ProgressBar } from '../components/ProgressBar'
import { getSessionId } from '../utils/sessionId'

type Tab = 'metrics' | 'logs' | 'errors'

interface BackendError {
  ts: number
  bot: string
  message: string
  detail?: string
}

export function Doctor() {
  const { systemStats, agents, doctorChat, addDoctorChat, activeStream, llmStatus } = useStore()
  const [input, setInput] = useState('')
  const [tab, setTab] = useState<Tab>('metrics')
  const [selectedBot, setSelectedBot] = useState<string>('')
  const [botLogs, setBotLogs] = useState<string[]>([])
  const [errors, setErrors] = useState<BackendError[]>([])
  const [expandedError, setExpandedError] = useState<number | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  // Break #3: instant loading feedback before first WS chunk arrives
  const [pending, setPending] = useState(false)
  const pendingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isStreaming = activeStream?.context === 'doctor'
  const loading = isStreaming || pending
  const streamContent = isStreaming ? activeStream!.content : ''

  // Clear pending once WS stream starts (Break #3)
  useEffect(() => {
    if (isStreaming && pending) {
      if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current)
      setPending(false)
    }
  }, [isStreaming, pending])

  // "Thinking..." after 3s
  const [showThinking, setShowThinking] = useState(false)
  useEffect(() => {
    if (!loading) { setShowThinking(false); return }
    if (streamContent.length > 0) { setShowThinking(false); return }
    const t = setTimeout(() => setShowThinking(true), 3000)
    return () => clearTimeout(t)
  }, [loading, streamContent])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [doctorChat, streamContent, loading])

  // Fetch real errors from backend
  useEffect(() => {
    const load = () =>
      fetch('/api/errors')
        .then((r) => r.json())
        .then((d) => setErrors(Array.isArray(d) ? d : []))
        .catch(() => {})
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  const send = async () => {
    if (!input.trim() || loading) return
    addDoctorChat({ role: 'user', content: input })
    const text = input
    setInput('')
    // Break #3: instant loading feedback before WS responds
    setPending(true)
    pendingTimerRef.current = setTimeout(() => setPending(false), 2000)
    try {
      await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, context: 'doctor', session_id: getSessionId() }),
      })
    } catch {
      if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current)
      setPending(false)
      addDoctorChat({ role: 'ai', content: 'Connection error.' })
    }
  }

  useEffect(() => {
    if (tab === 'logs' && selectedBot) {
      fetch(`/api/logs/${selectedBot}`)
        .then((r) => r.json())
        .then((d) => setBotLogs(d.lines || []))
        .catch(() => setBotLogs(['[No logs available]']))
    }
  }, [tab, selectedBot])

  // Set initial selected bot from real agent list
  useEffect(() => {
    if (agents.length > 0 && !selectedBot) {
      setSelectedBot(agents[0].name)
    }
  }, [agents, selectedBot])

  const runDiagnostic = async () => {
    addDoctorChat({ role: 'system', content: '🩺 Running full diagnostic...', tag: 'DOCTOR' })
    try {
      const r = await fetch('/api/doctor/run', { method: 'POST' })
      const d = await r.json()
      if (d.results) {
        d.results.forEach((res: { check: string; status: string; detail?: string }) => {
          addDoctorChat({ role: 'ai', content: `${res.status === 'pass' ? '✅' : '⚠️'} ${res.check}: ${res.status}${res.detail ? ` — ${res.detail}` : ''}` })
        })
      }
    } catch {
      addDoctorChat({ role: 'ai', content: 'ERROR: Diagnostic failed' })
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700, marginBottom: 20 }} className="metallic-text">
        🩺 DOCTOR — System Diagnostics &amp; Health
      </h1>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Chat */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: 400 }}>
          <div style={{ padding: '10px 16px', borderBottom: 'var(--border-subtle)', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--bronze)' }}>
            DOCTOR CHAT
          </div>
          <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {doctorChat.map((m, i) => (
              <div
                key={i}
                style={{
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  background: m.role === 'user' ? 'rgba(212,175,55,0.08)' : 'rgba(205,127,50,0.06)',
                  // Break #7: error messages get a red-bronze left border
                  borderLeft: m.role !== 'user'
                    ? m.tag === 'ERROR'
                      ? '2px solid #CD3232'
                      : '2px solid var(--bronze)'
                    : undefined,
                  borderRight: m.role === 'user' ? '2px solid var(--gold)' : undefined,
                  padding: '8px 12px',
                  borderRadius: 8,
                  fontSize: 13,
                  lineHeight: 1.5,
                  color: m.role === 'system' ? 'var(--text-secondary)' : 'var(--text-primary)',
                  fontStyle: m.role === 'system' ? 'italic' : undefined,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {m.tag && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: m.tag === 'ERROR' ? '#CD3232' : 'var(--bronze)', marginRight: 6 }}>[{m.tag}]</span>}
                {m.content}
              </div>
            ))}

            {/* Live streaming bubble */}
            {isStreaming && streamContent && (
              <div style={{
                alignSelf: 'flex-start',
                maxWidth: '85%',
                background: 'rgba(205,127,50,0.06)',
                borderLeft: '2px solid var(--bronze)',
                padding: '8px 12px',
                borderRadius: 8,
                fontSize: 13,
                lineHeight: 1.5,
                color: 'var(--text-primary)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {streamContent}
              </div>
            )}

            {/* Typing / Thinking */}
            {loading && !streamContent && (
              showThinking
                ? <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)', padding: '4px 0' }}>Thinking...</div>
                : (
                  <div style={{ alignSelf: 'flex-start', maxWidth: '85%', background: 'rgba(205,127,50,0.06)', borderLeft: '2px solid var(--bronze)', padding: '8px 12px', borderRadius: 8 }}>
                    <span className="typing-indicator">● ● ●</span>
                  </div>
                )
            )}
          </div>
          <div style={{ padding: 12, borderTop: 'var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 4 }}>
            {/* Status indicator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: loading ? 'var(--gold)' : llmStatus.provider === 'ollama' ? 'var(--online)' : llmStatus.provider === 'anthropic' ? 'var(--bronze)' : 'var(--text-dim)',
              }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>
                {loading ? 'generating...' : llmStatus.provider === 'ollama' ? `${llmStatus.model ?? 'ollama'} local` : llmStatus.model ? `${llmStatus.model} backup` : 'no provider'}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && send()}
                disabled={loading}
                placeholder="Ask about system health..."
                className="input-dark"
                style={{ flex: 1, fontSize: 13, padding: '8px 12px', opacity: loading ? 0.6 : 1 }}
              />
              <motion.button onClick={send} disabled={loading} whileTap={{ scale: 0.96 }} className="btn-gold" style={{ padding: '8px 16px', opacity: loading ? 0.6 : 1 }}>
                {loading ? '...' : 'ASK'}
              </motion.button>
            </div>
          </div>
        </div>

        {/* Tabbed panel */}
        <div className="panel" style={{ height: 400, display: 'flex', flexDirection: 'column' }}>
          <div className="tab-bar">
            {(['metrics', 'logs', 'errors'] as Tab[]).map((t) => (
              <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
                {t.toUpperCase()}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
            {tab === 'metrics' && (
              <div>
                <ProgressBar value={systemStats.cpu_percent} label="CPU TOTAL" variant="bronze" />
                <ProgressBar value={Math.round(systemStats.ram_used_gb / (systemStats.ram_total_gb || 1) * 100)} label={`RAM ${systemStats.ram_used_gb}/${systemStats.ram_total_gb}GB`} variant="bronze" />
                <ProgressBar value={systemStats.gpu_percent} label="GPU" variant="bronze" />
                <ProgressBar value={Math.min(systemStats.temp_celsius, 100)} label="TEMPERATURE" unit="°C" variant={systemStats.temp_celsius > 70 ? 'gold' : 'bronze'} />
                <div style={{ marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>
                  <div>Agents online: {agents.filter((a) => a.status === 'online').length} / {agents.length}</div>
                  <div>Errors (recent): {errors.length}</div>
                </div>
              </div>
            )}

            {tab === 'logs' && (
              <div>
                <select
                  value={selectedBot}
                  onChange={(e) => setSelectedBot(e.target.value)}
                  style={{
                    width: '100%', marginBottom: 8, padding: '6px 10px',
                    background: '#111', border: 'var(--border-gold)', borderRadius: 6,
                    color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 11,
                  }}
                >
                  {agents.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
                </select>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.7 }}>
                  {botLogs.length === 0 && <div style={{ color: 'var(--text-dim)' }}>No logs available</div>}
                  {botLogs.map((l, i) => (
                    <div key={i} style={{
                      color: l.includes('ERROR') ? 'var(--offline)' : l.includes('WARN') ? 'var(--warning)' : l.includes('DEBUG') ? 'var(--text-dim)' : 'var(--text-secondary)',
                    }}>
                      {l}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {tab === 'errors' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {errors.length === 0 && <div style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>No errors recorded</div>}
                {errors.map((err, i) => (
                  <div key={i} className="panel" style={{ padding: 10, background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--offline)' }}>{err.bot}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>{new Date(err.ts * 1000).toLocaleTimeString()}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 4 }}>{err.message}</div>
                    {err.detail && (
                      <button
                        onClick={() => setExpandedError(expandedError === i ? null : i)}
                        style={{ background: 'none', border: 'none', color: 'var(--bronze)', fontSize: 10, fontFamily: 'var(--font-mono)', cursor: 'pointer' }}
                      >
                        {expandedError === i ? '▼ Hide detail' : '▶ Show detail'}
                      </button>
                    )}
                    {expandedError === i && err.detail && (
                      <pre style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', marginTop: 4, whiteSpace: 'pre-wrap' }}>{err.detail}</pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <motion.button onClick={runDiagnostic} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} className="btn-gold">
          🩺 RUN FULL DIAGNOSTIC
        </motion.button>
        <motion.button onClick={() => window.location.href = '/forge'} whileHover={{ scale: 1.02 }} className="btn-outline">
          ⚙ OPTIMIZE ASCEND FORGE
        </motion.button>
        <motion.button
          onClick={() => {
            if (window.confirm('Reset all modes to default?')) {
              fetch('/api/forge/rollback', { method: 'POST' })
              fetch('/api/money/rollback', { method: 'POST' })
              fetch('/api/blacklight/rollback', { method: 'POST' })
            }
          }}
          whileHover={{ scale: 1.02 }}
          className="btn-outline"
        >
          🔄 RESET ALL MODES
        </motion.button>
      </div>

      {/* Agent cards */}
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 12 }}>
        AGENT STATUS ({agents.length})
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
        {agents.map((a) => (
          <motion.div
            key={a.name}
            className="panel"
            style={{
              padding: 12,
              cursor: 'pointer',
              border: selectedAgent === a.name ? '1px solid var(--gold)' : 'var(--border-gold)',
            }}
            whileHover={{ scale: 1.02 }}
            onClick={() => {
              setSelectedAgent(a.name)
              setSelectedBot(a.name)
              setTab('logs')
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span className={`dot ${a.status === 'online' ? 'online' : a.status === 'starting' ? 'starting' : 'offline'}`} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>
                {a.name}
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>
              {a.status} {a.uptime ? `• ${Math.round(a.uptime / 60)}m` : ''}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  )
}

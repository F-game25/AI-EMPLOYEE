import { motion, AnimatePresence } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store/ascendStore'
import { ProgressBar } from '../components/ProgressBar'
import { ModeButton } from '../components/ModeButton'
import { getSessionId } from '../utils/sessionId'

const page = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.25 } }

export function Dashboard() {
  const {
    systemStats, mainChat, addMainChat, agents,
    activeStream, llmStatus, showFallbackToast, setShowFallbackToast,
  } = useStore()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  // Break #3: instant loading feedback before first WS chunk arrives
  const [pending, setPending] = useState(false)
  const pendingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isStreaming = activeStream?.context === 'main'
  // loading = true as soon as user sends (pending) or once WS stream starts
  const loading = isStreaming || pending
  const streamContent = isStreaming ? activeStream!.content : ''

  // Clear pending once WS stream starts (Break #3)
  useEffect(() => {
    if (isStreaming && pending) {
      if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current)
      setPending(false)
    }
  }, [isStreaming, pending])

  // Cleanup pending timer on unmount
  useEffect(() => () => { if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current) }, [])


  const [showThinking, setShowThinking] = useState(false)
  useEffect(() => {
    if (!loading) { setShowThinking(false); return }
    if (streamContent.length > 0) { setShowThinking(false); return }
    const t = setTimeout(() => setShowThinking(true), 3000)
    return () => clearTimeout(t)
  }, [loading, streamContent])

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [mainChat, streamContent, loading])

  const send = async () => {
    if (!input.trim() || loading) return
    addMainChat({ role: 'user', content: input })
    const text = input
    setInput('')
    // Break #3: instant loading feedback before WS responds
    setPending(true)
    pendingTimerRef.current = setTimeout(() => setPending(false), 2000)
    try {
      await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, context: 'main', session_id: getSessionId() }),
      })
    } catch {
      if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current)
      setPending(false)
      addMainChat({ role: 'ai', content: 'Connection error. Check backend.' })
    }
  }

  const statusLabel =
    llmStatus.provider === 'ollama'
      ? `${llmStatus.model ?? 'ollama'} local`
      : llmStatus.model
        ? `${llmStatus.model} backup`
        : 'no provider'

  const forgeStatus = (agents.find((a) => a.name.includes('forge'))?.status || 'offline') as 'online' | 'offline' | 'starting'
  const moneyStatus = (agents.find((a) => a.name.includes('money'))?.status || 'offline') as 'online' | 'offline' | 'starting'
  const blackStatus = (agents.find((a) => a.name.includes('black'))?.status || 'offline') as 'online' | 'offline' | 'starting'

  return (
    <motion.div {...page} style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, height: '100%' }}>
      {/* Chat */}
      <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)', position: 'relative' }}>
        {/* Fallback toast */}
        <AnimatePresence>
          {showFallbackToast && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              style={{
                position: 'absolute',
                top: 8,
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 20,
                padding: '6px 16px',
                background: 'rgba(10,10,10,0.95)',
                border: '1px solid var(--bronze)',
                borderRadius: 8,
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--bronze)',
                whiteSpace: 'nowrap',
                boxShadow: '0 0 12px rgba(205,127,50,0.3)',
              }}
              onClick={() => setShowFallbackToast(false)}
            >
              ⚡ Switched to Anthropic backup — Ollama unavailable
            </motion.div>
          )}
        </AnimatePresence>

        <div style={{ padding: '12px 16px', borderBottom: 'var(--border-subtle)', fontFamily: 'var(--font-heading)', fontSize: 13 }} className="metallic-text">
          MAIN AI CHAT
        </div>
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {mainChat.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: m.role === 'user' ? 20 : -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                background: m.role === 'user' ? 'rgba(212,175,55,0.08)' : 'rgba(205,127,50,0.06)',
                // Break #7: error messages get a red-bronze left border
                borderLeft: m.role === 'ai'
                  ? m.tag === 'ERROR'
                    ? '2px solid #CD3232'
                    : '2px solid var(--bronze)'
                  : undefined,
                borderRight: m.role === 'user' ? '2px solid var(--gold)' : undefined,
                padding: '10px 14px',
                borderRadius: 8,
                fontFamily: 'var(--font-body)',
                fontSize: 14,
                lineHeight: 1.6,
                color: m.role === 'system' ? 'var(--text-secondary)' : 'var(--text-primary)',
                fontStyle: m.role === 'system' ? 'italic' : undefined,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {m.tag && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: m.tag === 'ERROR' ? '#CD3232' : 'var(--bronze)', marginRight: 8 }}>
                  [{m.tag}]
                </span>
              )}
              {m.content}
            </motion.div>
          ))}

          {/* Live streaming bubble */}
          {isStreaming && streamContent && (
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.15 }}
              style={{
                alignSelf: 'flex-start',
                maxWidth: '80%',
                background: 'rgba(205,127,50,0.06)',
                borderLeft: '2px solid var(--bronze)',
                padding: '10px 14px',
                borderRadius: 8,
                fontFamily: 'var(--font-body)',
                fontSize: 14,
                lineHeight: 1.6,
                color: 'var(--text-primary)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {streamContent}
            </motion.div>
          )}

          {/* Typing dots or Thinking... */}
          {loading && !streamContent && (
            showThinking
              ? (
                <div style={{
                  alignSelf: 'flex-start',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--text-dim)',
                  padding: '4px 0',
                }}>
                  Thinking...
                </div>
              )
              : (
                <div style={{
                  alignSelf: 'flex-start',
                  maxWidth: '80%',
                  background: 'rgba(205,127,50,0.06)',
                  borderLeft: '2px solid var(--bronze)',
                  padding: '10px 14px',
                  borderRadius: 8,
                }}>
                  <span className="typing-indicator">● ● ●</span>
                </div>
              )
          )}
        </div>
        <div style={{ padding: 16, borderTop: 'var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {/* Status indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: loading
                ? 'var(--gold)'
                : llmStatus.provider === 'ollama'
                  ? 'var(--online)'
                  : llmStatus.provider === 'anthropic'
                    ? 'var(--bronze)'
                    : 'var(--text-dim)',
              flexShrink: 0,
            }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>
              {loading ? 'generating...' : statusLabel}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send()}
              disabled={loading}
              placeholder="Send a task or ask anything..."
              className="input-dark"
              style={{ flex: 1, opacity: loading ? 0.6 : 1 }}
            />
            <motion.button
              onClick={send}
              disabled={loading}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              className="btn-gold"
              style={{ opacity: loading ? 0.6 : 1, cursor: loading ? 'not-allowed' : 'pointer' }}
            >
              {loading ? '...' : 'SEND'}
            </motion.button>
          </div>
        </div>
      </div>

      {/* Right column */}
      <div>
        <div className="panel" style={{ padding: 20, marginBottom: 16 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 16 }}>
            SYSTEM STATS
          </div>
          <ProgressBar value={systemStats.cpu_percent} label="CPU" variant="bronze" />
          <ProgressBar value={Math.round(systemStats.ram_used_gb / (systemStats.ram_total_gb || 1) * 100)} label={`RAM ${systemStats.ram_used_gb}/${systemStats.ram_total_gb}GB`} variant="bronze" />
          <ProgressBar value={systemStats.gpu_percent} label="GPU" variant="bronze" />
          <ProgressBar value={Math.min(systemStats.temp_celsius, 100)} label="TEMP" unit="°C" variant={systemStats.temp_celsius > 70 ? 'gold' : 'bronze'} />
        </div>
        <ModeButton icon="⚗" name="ASCEND FORGE" description="Self-Improvement Engine" status={forgeStatus} route="/forge" />
        <ModeButton icon="💰" name="MONEY MODE" description="Optimization & Revenue" status={moneyStatus} route="/money" />
        <ModeButton icon="🔒" name="BLACKLIGHT" description="Security & Safe Mode" status={blackStatus} route="/blacklight" />
      </div>
    </motion.div>
  )
}

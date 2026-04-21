import { useEffect, useRef, useState, KeyboardEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from '../store/ascendStore'
import { getSessionId } from '../utils/sessionId'

export interface ChatMsg {
  role: 'user' | 'ai' | 'system'
  content: string
  tag?: string
}

interface ChatWindowProps {
  messages: ChatMsg[]
  context: string
  placeholder?: string
  height?: number
  onNewMessage: (msg: ChatMsg) => void
}

function TypingDots() {
  return (
    <div
      style={{
        alignSelf: 'flex-start',
        maxWidth: '80%',
        background: 'rgba(205,127,50,0.06)',
        borderLeft: '2px solid var(--bronze)',
        padding: '10px 14px',
        borderRadius: 8,
      }}
    >
      <span className="typing-indicator">● ● ●</span>
    </div>
  )
}

export function ChatWindow({
  messages,
  context,
  placeholder = 'Type a message...',
  height = 340,
  onNewMessage,
}: ChatWindowProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [input, setInput] = useState('')
  // Break #3: instant loading feedback on send — before first WS chunk arrives
  const [pending, setPending] = useState(false)
  const pendingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { activeStream, llmStatus, showFallbackToast, setShowFallbackToast } = useStore()

  const isStreaming = activeStream?.context === context
  // loading = true as soon as user sends (pending) or once WS stream starts
  const loading = isStreaming || pending
  const streamContent = isStreaming ? activeStream!.content : ''

  // Clear pending once the WS stream actually starts (Break #3)
  useEffect(() => {
    if (isStreaming && pending) {
      if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current)
      setPending(false)
    }
  }, [isStreaming, pending])

  // "Thinking..." — show after 3s if no content yet
  const [showThinking, setShowThinking] = useState(false)
  useEffect(() => {
    if (!loading) {
      setShowThinking(false)
      return
    }
    if (streamContent.length > 0) {
      setShowThinking(false)
      return
    }
    const t = setTimeout(() => setShowThinking(true), 3000)
    return () => clearTimeout(t)
  }, [loading, streamContent])

  // Auto-scroll when messages or stream content changes
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading, streamContent])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    onNewMessage({ role: 'user', content: text })
    setInput('')
    // Break #3: show loading indicator immediately, before WS responds
    setPending(true)
    pendingTimerRef.current = setTimeout(() => setPending(false), 2000)
    try {
      await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, context, session_id: getSessionId() }),
      })
      // Response is streamed via WebSocket — nothing to do with the HTTP body
    } catch (err: unknown) {
      if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current)
      setPending(false)
      const msg = err instanceof Error ? err.message : String(err)
      onNewMessage({ role: 'ai', content: `Error: ${msg}` })
    }
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) send()
  }

  // Status label
  const statusLabel =
    llmStatus.provider === 'ollama'
      ? `${llmStatus.model ?? 'ollama'} local`
      : llmStatus.model
        ? `${llmStatus.model} backup`
        : 'no provider'

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height, position: 'relative' }}>
      {/* Fallback toast — bronze border, auto-dismiss */}
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

      {/* Message history */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '85%',
                background:
                  m.role === 'user'
                    ? 'rgba(212,175,55,0.08)'
                    : 'rgba(205,127,50,0.06)',
                // Break #7: error messages get a red-bronze left border
                borderLeft: m.role !== 'user'
                  ? m.tag === 'ERROR'
                    ? '2px solid #CD3232'
                    : '2px solid var(--bronze)'
                  : undefined,
                borderRight: m.role === 'user' ? '2px solid var(--gold)' : undefined,
                padding: '9px 13px',
                borderRadius: 8,
                fontFamily: 'var(--font-body)',
                fontSize: 13,
                lineHeight: 1.6,
                color:
                  m.role === 'system'
                    ? 'var(--text-secondary)'
                    : 'var(--text-primary)',
                fontStyle: m.role === 'system' ? 'italic' : undefined,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {m.tag && (
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    color: m.tag === 'ERROR' ? '#CD3232' : 'var(--bronze)',
                    marginRight: 6,
                  }}
                >
                  [{m.tag}]
                </span>
              )}
              {m.content}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Live streaming bubble */}
        {isStreaming && streamContent && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
            style={{
              alignSelf: 'flex-start',
              maxWidth: '85%',
              background: 'rgba(205,127,50,0.06)',
              borderLeft: '2px solid var(--bronze)',
              padding: '9px 13px',
              borderRadius: 8,
              fontFamily: 'var(--font-body)',
              fontSize: 13,
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
            : <TypingDots />
        )}
      </div>

      {/* Input row */}
      <div
        style={{
          padding: '10px 12px',
          borderTop: 'var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}
      >
        {/* Status indicator */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          paddingBottom: 4,
        }}>
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
            boxShadow: loading ? '0 0 6px var(--gold)' : undefined,
            animation: loading ? 'pulse 1.2s ease-in-out infinite' : undefined,
            flexShrink: 0,
          }} />
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--text-dim)',
            letterSpacing: 0.5,
          }}>
            {loading ? 'generating...' : statusLabel}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            disabled={loading}
            placeholder={placeholder}
            className="input-dark"
            style={{
              flex: 1,
              fontSize: 13,
              padding: '8px 12px',
              opacity: loading ? 0.6 : 1,
            }}
          />
          <motion.button
            onClick={send}
            disabled={loading}
            whileTap={{ scale: 0.96 }}
            className="btn-gold"
            style={{
              padding: '8px 18px',
              opacity: loading ? 0.6 : 1,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '...' : 'SEND'}
          </motion.button>
        </div>
      </div>
    </div>
  )
}

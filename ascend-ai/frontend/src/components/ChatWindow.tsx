import { useEffect, useRef, useState, KeyboardEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

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
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    onNewMessage({ role: 'user', content: text })
    setInput('')
    setLoading(true)
    try {
      const controller = new AbortController()
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, context }),
        signal: controller.signal,
      })
      const d = await r.json()
      onNewMessage({ role: 'ai', content: d.content || 'No response.' })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      onNewMessage({ role: 'ai', content: `Error: ${msg}` })
    } finally {
      setLoading(false)
    }
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) send()
  }

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height }}>
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
                borderLeft: m.role !== 'user' ? '2px solid var(--bronze)' : undefined,
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
                    color: 'var(--bronze)',
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
        {loading && <TypingDots />}
      </div>

      {/* Input row */}
      <div
        style={{
          padding: '10px 12px',
          borderTop: 'var(--border-subtle)',
          display: 'flex',
          gap: 8,
        }}
      >
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
  )
}

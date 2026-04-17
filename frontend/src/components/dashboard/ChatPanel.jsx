import { useState, useRef, useEffect, useId } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { sendChatMessage } from '../../hooks/useWebSocket'

export default function ChatPanel() {
  const messages = useAppStore(s => s.chatMessages)
  const isTyping = useAppStore(s => s.isTyping)
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const inputId = useId()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  const handleSend = () => {
    const text = input.trim()
    if (!text) return
    addChatMessage({ role: 'user', content: text, ts: Date.now() })
    sendChatMessage(text)
    setInput('')
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center px-4 py-2.5 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-gold-dim)' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
          ORCHESTRATOR CHAT
        </span>
      </div>

      {/* Messages */}
      <div
        role="log"
        aria-label="Chat messages"
        aria-live="polite"
        aria-atomic="false"
        className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
      >
        {messages.length === 0 && !isTyping && (
          <div className="flex items-center justify-center h-full">
            <p className="font-mono text-xs text-center" style={{ color: 'var(--text-muted)' }}>
              Send a command to the orchestrator
            </p>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg, idx) => (
            <motion.div
              key={`${msg.ts}-${idx}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className="max-w-sm lg:max-w-lg px-3 py-2 font-mono text-xs leading-relaxed"
                style={msg.role === 'user' ? {
                  background: 'rgba(212,175,55,0.08)',
                  border: '1px solid rgba(212,175,55,0.25)',
                  borderRadius: '6px 6px 2px 6px',
                  color: 'var(--gold)',
                } : {
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px 6px 6px 2px',
                  color: 'var(--text-primary)',
                }}
              >
                {msg.role === 'ai' && (
                  <div
                    className="text-xs mb-1 font-semibold tracking-widest"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {msg.subsystem === 'nn' ? 'NEURAL BRAIN' :
                     msg.subsystem === 'memory' ? 'MEMORY TREE' :
                     msg.subsystem === 'doctor' ? 'DOCTOR' :
                     'ORCHESTRATOR'}
                  </div>
                )}
                {msg.content}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator */}
        <AnimatePresence>
          {isTyping && (
            <motion.div
              key="typing"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.2 }}
              className="flex justify-start"
            >
              <div
                className="px-3 py-2.5"
                style={{
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px 6px 6px 2px',
                }}
                aria-label="Orchestrator is typing"
              >
                <div className="flex items-center gap-1.5">
                  {[0, 1, 2].map(i => (
                    <motion.div
                      key={i}
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--text-dim)' }}
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
                    />
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        className="flex items-center px-3 py-2.5 flex-shrink-0 gap-2"
        style={{ borderTop: '1px solid var(--border-gold-dim)' }}
      >
        <label htmlFor={inputId} className="sr-only">
          Send a command to the orchestrator
        </label>
        {/* Chevron prompt indicator */}
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          aria-hidden="true"
          className="flex-shrink-0"
          style={{ color: 'var(--gold)' }}
        >
          <path d="M4 2L8 6L4 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <input
          id={inputId}
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Enter command..."
          autoComplete="off"
          className="flex-1 font-mono text-xs outline-none bg-transparent min-w-0"
          style={{ color: 'var(--text-primary)', caretColor: 'var(--gold)' }}
        />
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={handleSend}
          disabled={!input.trim()}
          className="font-mono text-xs px-3 py-1.5 flex-shrink-0"
          style={{
            border: '1px solid rgba(212,175,55,0.3)',
            color: 'var(--gold)',
            background: 'rgba(212,175,55,0.06)',
            borderRadius: '3px',
            cursor: input.trim() ? 'pointer' : 'not-allowed',
            opacity: input.trim() ? 1 : 0.5,
            transition: 'opacity 0.15s',
          }}
          aria-label="Send message"
        >
          SEND
        </motion.button>
      </div>
    </div>
  )
}

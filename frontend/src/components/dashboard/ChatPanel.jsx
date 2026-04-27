import { useState, useRef, useEffect, useId } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { useBrainStore } from '../../store/brainStore'
import { sendChatMessage } from '../../hooks/useWebSocket'
import TaskProgressBlock from '../ui/TaskProgressBlock'

export default function ChatPanel() {
  const messages = useAppStore(s => s.chatMessages)
  const isTyping = useAppStore(s => s.isTyping)
  const debugMode = useAppStore(s => s.debugMode)
  const toggleDebugMode = useAppStore(s => s.toggleDebugMode)
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const addFromPrompt = useBrainStore(s => s.addFromPrompt)
  const inputId = useId()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  const handleSend = () => {
    const text = input.trim()
    if (!text) return
    addChatMessage({ role: 'user', content: text, ts: Date.now() })
    sendChatMessage(text)
    // Add prompt as a node in the shared brain graph
    addFromPrompt(text, 'task', 'automation')
    setInput('')
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const subsystemLabel = (subsystem) => {
    if (subsystem === 'nn') return 'Neural Brain'
    if (subsystem === 'memory') return 'Memory'
    if (subsystem === 'doctor') return 'Doctor'
    return 'AI'
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-gold-dim)' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
          ULTRON ASSISTANT
        </span>
        <button
          onClick={toggleDebugMode}
          title={debugMode ? 'Switch to user mode' : 'Switch to debug mode'}
          className="font-mono text-xs px-2 py-1 flex-shrink-0"
          style={{
            border: `1px solid ${debugMode ? 'rgba(212,175,55,0.5)' : 'rgba(255,255,255,0.1)'}`,
            color: debugMode ? 'var(--gold)' : 'var(--text-muted)',
            background: debugMode ? 'rgba(212,175,55,0.08)' : 'transparent',
            borderRadius: '3px',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          {debugMode ? 'DEBUG ON' : 'DEBUG'}
        </button>
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
              How can I help you today?
            </p>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg, idx) => {
            // Handle task progress messages
            if (msg.type === 'task_progress') {
              return (
                <motion.div
                  key={`${msg.ts}-${idx}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex justify-start w-full"
                >
                  <div className="w-full max-w-sm lg:max-w-lg">
                    <TaskProgressBlock
                      taskId={msg.taskId}
                      title={msg.title || 'Processing...'}
                    />
                  </div>
                </motion.div>
              )
            }

            // Regular chat messages
            return (
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
                  {msg.role === 'ai' && debugMode && msg.subsystem && (
                    <div
                      className="text-xs mb-1 font-semibold tracking-widest"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {subsystemLabel(msg.subsystem).toUpperCase()}
                    </div>
                  )}
                  {msg.content}
                  {msg.role === 'ai' && debugMode && msg.debugInfo && (
                    <div
                      className="mt-2 pt-2 text-xs opacity-60"
                      style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
                    >
                      {msg.debugInfo}
                    </div>
                  )}
                </div>
              </motion.div>
            )
          })}
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
                aria-label="AI is thinking"
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
          Message your AI assistant
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
          placeholder="What do you need help with?"
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

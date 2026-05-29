import { useState, useRef, useEffect, useId } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { sendChatMessage } from '../../hooks/useWebSocket'
import { enableDevMode, disableDevMode, isDevModeActive } from '../../hooks/useDevMode'
import './ChatPanel.css'

const DEV_ON_PHRASE  = 'aethernus nexus dev mode'
const DEV_OFF_PHRASE = 'aethernus nexus dev off'

export default function ChatPanel({ isOpen, onClose }) {
  const messages = useAppStore(s => s.chatMessages) || []
  const isTyping = useAppStore(s => s.isTyping)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const inputId = useId()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  useEffect(() => {
    if (isOpen) inputRef.current?.focus()
  }, [isOpen])

  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape' && isOpen) onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  const handleSend = () => {
    const text = input.trim()
    if (!text) return
    const lower = text.toLowerCase()
    if (lower === DEV_ON_PHRASE) {
      enableDevMode()
      addChatMessage?.({ role: 'assistant', content: '⚡ Dev mode activated. Reload to see dev overlays.', ts: Date.now() })
      setInput('')
      return
    }
    if (lower === DEV_OFF_PHRASE) {
      disableDevMode()
      addChatMessage?.({ role: 'assistant', content: '✓ Dev mode deactivated.', ts: Date.now() })
      setInput('')
      return
    }
    addChatMessage?.({ role: 'user', content: text, ts: Date.now() })
    sendChatMessage(text)
    setInput('')
  }

  const handleKey = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const fmtTime = ts => {
    const d = new Date(ts || Date.now())
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  const proofHref = item => item?.url || item?.preview_url || (item?.path ? `/api/artifacts/${encodeURIComponent(item.path.split('/').pop())}` : null)
  const isHtmlPreview = item => item?.type === 'html_preview' || (item?.url || '').endsWith('.html') || (item?.preview_url || '').includes('/api/preview/')
  const previewSrc = item => {
    const url = item?.preview_url || item?.url || ''
    const token = sessionStorage.getItem('ai_jwt')
    return token ? `${url}?token=${encodeURIComponent(token)}` : url
  }

  const renderTurnMeta = msg => {
    if (msg.type !== 'turn' && !msg.turn_id) return null
    const actions = Array.isArray(msg.actions) ? msg.actions : []
    const proof = Array.isArray(msg.proof) ? msg.proof : []
    const artifacts = Array.isArray(msg.artifacts) ? msg.artifacts : []
    const errors = Array.isArray(msg.errors) ? msg.errors : []
    const allArtifacts = [...proof, ...artifacts].slice(0, 6)
    const htmlPreviews = allArtifacts.filter(isHtmlPreview)
    const otherArtifacts = allArtifacts.filter(a => !isHtmlPreview(a))
    return (
      <div className="turn-meta">
        <div className="turn-meta__bar">
          <span className={`turn-status turn-status--${msg.status || 'unknown'}`}>{msg.status || 'running'}</span>
          {msg.source && <span className="turn-chip">{msg.source}</span>}
          {msg.degraded && <span className="turn-chip turn-chip--warn">fallback/degraded</span>}
          {msg.trace_id && <span className="turn-chip">trace {String(msg.trace_id).slice(0, 10)}</span>}
        </div>
        {actions.length > 0 && (
          <div className="turn-section">
            <span className="turn-section__label">Actions</span>
            {actions.slice(0, 6).map((action, i) => (
              <div className="turn-row" key={`${action.id || action.action || i}-${i}`}>
                <span className={`turn-dot turn-dot--${action.status || 'running'}`} />
                <span>{action.label || action.action || 'action'}</span>
              </div>
            ))}
          </div>
        )}
        {htmlPreviews.map((item, i) => (
          <div key={`preview-${i}`} className="turn-section turn-section--preview">
            <span className="turn-section__label">
              {item.label || item.name || 'Website Preview'}
              <a href={proofHref(item)} target="_blank" rel="noreferrer" className="turn-preview-link">↗ open</a>
            </span>
            <iframe
              src={previewSrc(item)}
              className="turn-preview-iframe"
              title={item.label || 'Website Preview'}
              sandbox="allow-same-origin allow-scripts"
            />
          </div>
        ))}
        {otherArtifacts.length > 0 && (
          <div className="turn-section">
            <span className="turn-section__label">Proof</span>
            {otherArtifacts.map((item, i) => {
              const href = proofHref(item)
              const label = item.label || item.name || item.type || 'proof'
              return (
                <div className="turn-row" key={`${label}-${i}`}>
                  <span className="turn-dot turn-dot--completed" />
                  {href ? <a href={href} target="_blank" rel="noreferrer">{label}</a> : <span>{label}</span>}
                </div>
              )
            })}
          </div>
        )}
        {errors.length > 0 && (
          <div className="turn-section turn-section--error">
            <span className="turn-section__label">Blocked</span>
            {errors.slice(0, 3).map((err, i) => (
              <div className="turn-row" key={`${err.stage || 'error'}-${i}`}>
                <span className="turn-dot turn-dot--failed" />
                <span>{err.message || String(err)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={`chat-panel ${isOpen ? 'chat-panel--open' : 'chat-panel--closed'}`}>
      <button
        type="button"
        className="chat-panel__handle"
        onClick={onClose}
        aria-label="Collapse chat"
        title="Click to collapse"
      />
      <div className="chat-panel__header">
        <h2 className="chat-panel__title">NEXUS COMMAND</h2>
        <button
          className="chat-panel__close"
          onClick={onClose}
          aria-label="Close chat"
          title="Close (Esc)"
        >
          <span className="close-icon">&lt;</span>
          <span className="close-text">CLOSE</span>
        </button>
      </div>

      <div className="chat-panel__messages" role="log" aria-live="polite">
        {messages.length === 0 && !isTyping && (
          <div className="chat-panel__empty">
            <span className="chat-panel__empty-text">How can I help you today?</span>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg, idx) => (
            <motion.div
              key={`${msg.ts || idx}-${idx}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
              className={`chat-panel__message chat-panel__message--${msg.role === 'user' ? 'user' : 'system'}`}
            >
              <div className="message-bubble">
                <span className="message-role">{msg.role === 'user' ? 'USER' : 'SYS'}</span>
                <span className="message-time">{fmtTime(msg.ts)}</span>
              </div>
              <div className="message-content">{msg.content}</div>
              {renderTurnMeta(msg)}
            </motion.div>
          ))}
        </AnimatePresence>

        <AnimatePresence>
          {isTyping && (
            <motion.div
              key="typing"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="chat-panel__message chat-panel__message--typing"
            >
              <div className="message-bubble">
                <span className="message-role">SYS</span>
                <span className="message-time">{fmtTime()}</span>
              </div>
              <div className="message-content">
                <span className="typing-indicator">
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-panel__input-wrap">
        <label htmlFor={inputId} className="sr-only">Message your AI assistant</label>
        <input
          id={inputId}
          ref={inputRef}
          type="text"
          className="chat-panel__input"
          placeholder="Enter command..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          autoComplete="off"
        />
        <button
          className="chat-panel__send"
          onClick={handleSend}
          disabled={!input.trim()}
          aria-label="Send message"
          title="Send (Enter)"
        >
          <span className="send-icon">↑</span>
        </button>
      </div>
    </div>
  )
}

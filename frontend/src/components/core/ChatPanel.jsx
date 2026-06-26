import { useState, useRef, useEffect, useId } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { useCompanionStore } from '../../store/companionStore'
import { enableDevMode, disableDevMode, isDevModeActive } from '../../hooks/useDevMode'
import DeepResearchInline from './DeepResearchInline'
import './ChatPanel.css'

const authHeaders = () => {
  const t = sessionStorage.getItem('ai_jwt') || ''
  return { 'content-type': 'application/json', ...(t ? { authorization: `Bearer ${t}` } : {}) }
}

const DEV_ON_PHRASE  = 'aethernus nexus dev mode'
const DEV_OFF_PHRASE = 'aethernus nexus dev off'

export default function ChatPanel({ isOpen, onClose }) {
  const messages = useAppStore(s => s.chatMessages) || []
  const isTyping = useAppStore(s => s.isTyping)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const activeSection = useAppStore(s => s.activeSection)
  const companionThinking = useCompanionStore(s => s.thinking)
  const companionMessages = useCompanionStore(s => s.messages)
  const sendCompanionMessage = useCompanionStore(s => s.sendMessage)
  const lastActions = useCompanionStore(s => s.lastActions)
  const [input, setInput] = useState('')
  const [researchRuns, setResearchRuns] = useState([])
  const [startingResearch, setStartingResearch] = useState(false)
  const [voiceOn, setVoiceOn] = useState(() => { try { return localStorage.getItem('teammate_voice') === '1' } catch { return false } })
  const spokenRef = useRef(0)
  const audioRef = useRef(null)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const inputId = useId()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping, companionMessages, companionThinking])

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
    // Single path: always route through the Companion Gateway (the teammate
    // runtime — intent → session/context → tools → response policy). No bare-LLM
    // fallback, so the chat always gets context retention, option resolution,
    // and answer discipline.
    addChatMessage?.({ role: 'user', content: text, ts: Date.now() })
    sendCompanionMessage(text, {
      current_page: activeSection || null,
      selected_item: null,
      recent_events: [],
      active_task: null,
    })
    setInput('')
  }

  // Dedicated Deep Research trigger: uses the current input as the topic, launches
  // the multi-hop research engine, and renders a live inline card in the chat that
  // visualizes phases + sites visited + progress and reports back the final report.
  const startDeepResearch = async (depth = 'deep', topicArg = null) => {
    const topic = (topicArg || input.trim()).trim()
    if (!topic || startingResearch) return
    setStartingResearch(true)
    if (!topicArg) addChatMessage?.({ role: 'user', content: `🔬 Deep research: ${topic}`, ts: Date.now() })
    try {
      const r = await fetch('/api/research/deep/start', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ topic, depth }),
      })
      const d = await r.json()
      if (d.ok && d.report_id) {
        setResearchRuns(prev => [...prev, { id: d.report_id, topic, depth, ts: Date.now() }])
        if (!topicArg) setInput('')
      } else {
        addChatMessage?.({ role: 'assistant', content: '⚠ Could not start deep research. Try again.', ts: Date.now() })
      }
    } catch {
      addChatMessage?.({ role: 'assistant', content: '⚠ Deep research is unavailable right now.', ts: Date.now() })
    } finally {
      setStartingResearch(false)
    }
  }

  // When the teammate emits a deep_research DIRECTIVE (you asked it in chat), start
  // the real run + render the live card here — so chat deep research actually runs
  // and shows progress + the report, instead of just confirming.
  const handledDirectivesRef = useRef(new Set())
  useEffect(() => {
    for (const a of (lastActions || [])) {
      const d = a?.data && typeof a.data === 'object' ? a.data : null
      if (d?.directive === 'deep_research' && d.topic) {
        const key = `${d.topic}|${d.depth || 'deep'}`
        if (handledDirectivesRef.current.has(key)) continue
        handledDirectivesRef.current.add(key)
        startDeepResearch(d.depth || 'deep', d.topic)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastActions])

  const toggleVoice = () => setVoiceOn(v => {
    const nv = !v
    try { localStorage.setItem('teammate_voice', nv ? '1' : '0') } catch { /* noop */ }
    if (!nv && audioRef.current) { try { audioRef.current.pause() } catch { /* noop */ } }
    return nv
  })

  // Speak each new companion reply via the local Kokoro voice (browser playback).
  // Uses the concise voice_summary when present so spoken replies stay short.
  useEffect(() => {
    if (!voiceOn || !companionMessages?.length) return
    const last = companionMessages[companionMessages.length - 1]
    if (!last || last.role !== 'companion' || (last.ts || 0) <= spokenRef.current) return
    spokenRef.current = last.ts || Date.now()
    const text = String(last.meta?.voice_summary || last.text || '').trim()
    if (!text) return
    let url = null
    ;(async () => {
      try {
        const r = await fetch('/api/voice/speak', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ text: text.slice(0, 1200) }) })
        if (!r.ok) return
        const blob = await r.blob()
        url = URL.createObjectURL(blob)
        if (audioRef.current) { try { audioRef.current.pause() } catch { /* noop */ } }
        const audio = new Audio(url)
        audioRef.current = audio
        audio.onended = () => { try { URL.revokeObjectURL(url) } catch { /* noop */ } }
        audio.play().catch(() => {})
      } catch { /* voice is best-effort */ }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companionMessages, voiceOn])

  const handleKey = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Merge companion replies into the rendered log. User turns are already added
  // to chatMessages by handleSend, so we only fold in companion-role replies to
  // avoid duplicate user bubbles. Sorted by timestamp.
  const renderedMessages = (() => {
    const companionReplies = (companionMessages || [])
      .filter(m => m.role === 'companion')
      .map(m => ({ role: 'companion', content: m.text, ts: m.ts, source: 'companion', degraded: m.meta?.error }))
    if (!companionReplies.length) return messages
    return [...messages, ...companionReplies].sort((a, b) => (a.ts || 0) - (b.ts || 0))
  })()

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
        {renderedMessages.length === 0 && !isTyping && !companionThinking && (
          <div className="chat-panel__empty">
            <span className="chat-panel__empty-text">How can I help you today?</span>
          </div>
        )}

        <AnimatePresence initial={false}>
          {renderedMessages.map((msg, idx) => (
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

        {researchRuns.map(run => (
          <DeepResearchInline key={run.id} reportId={run.id} topic={run.topic} depth={run.depth} />
        ))}

        <AnimatePresence>
          {(isTyping || companionThinking) && (
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
        <label htmlFor={inputId} className="sr-only">Message your AI teammate</label>
        <input
          id={inputId}
          ref={inputRef}
          type="text"
          className="chat-panel__input"
          placeholder="Ask your teammate..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          autoComplete="off"
        />
        <button
          className={`chat-panel__voice ${voiceOn ? 'is-on' : ''}`}
          onClick={toggleVoice}
          aria-label={voiceOn ? 'Voice on — teammate speaks replies' : 'Voice off'}
          title={voiceOn ? 'Voice ON — teammate speaks (Kokoro). Click to mute.' : 'Voice OFF — click to let the teammate speak'}
        >
          {voiceOn ? '🔊' : '🔇'}
        </button>
        <button
          className="chat-panel__research"
          onClick={() => startDeepResearch('deep')}
          disabled={!input.trim() || startingResearch}
          aria-label="Start deep research on this topic"
          title="Deep Research — multi-hop research with live progress in chat"
        >
          <span className="research-icon">🔬</span>
          <span className="research-label">Deep Research</span>
        </button>
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

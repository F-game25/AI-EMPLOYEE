/* NEXUS OS Mobile — CHAT Screen */
import { useState, useEffect, useRef, useCallback } from 'react'
import { TopBar, Bubble, Spinner } from '../MobileUI'
import api from '../../../api/client'

const QUICK_ACTIONS = [
  { label: '◈ System Status', msg: 'What is the current system status?' },
  { label: '◉ Agent Report', msg: 'Give me a quick agent performance summary.' },
  { label: '▷ Run Task', msg: 'What tasks are currently running?' },
  { label: '⬡ Security Check', msg: 'Any security alerts or anomalies?' },
]

export default function MobileChat() {
  const [messages, setMessages] = useState([
    { id: '0', role: 'system', content: 'NEXUS OS AI — Connected' },
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [model, setModel] = useState('claude-sonnet-4-6')
  const endRef = useRef(null)
  const inputRef = useRef(null)
  const scrollTimer = useRef(null)

  useEffect(() => {
    clearTimeout(scrollTimer.current)
    scrollTimer.current = setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 80)
    return () => clearTimeout(scrollTimer.current)
  }, [messages])

  const send = useCallback(async (text) => {
    const msg = text?.trim() || input.trim()
    if (!msg || sending) return
    setInput('')
    setSending(true)
    const id = Date.now().toString()
    setMessages(prev => [...prev, { id, role: 'user', content: msg }])
    try {
      const r = await api.chat.send(msg, model)
      const reply = r?.response || r?.message || r?.content || r?.reply || 'No response.'
      setMessages(prev => [...prev, { id: id + '-r', role: 'assistant', name: 'NEXUS', content: reply }])
    } catch (e) {
      setMessages(prev => [...prev, { id: id + '-e', role: 'system', content: `Error: ${e.message}` }])
    } finally { setSending(false) }
  }, [input, sending, model])

  const onKey = useCallback(e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }, [send])

  return (
    <div style={S.screen}>
      <TopBar title="CHAT" subtitle="AI Neural Core" right={
        <select style={S.modelPicker} value={model} onChange={e => setModel(e.target.value)}>
          <option value="claude-sonnet-4-6">Sonnet</option>
          <option value="claude-opus-4-7">Opus</option>
          <option value="claude-haiku-4-5-20251001">Haiku</option>
        </select>
      } />

      <div style={S.messages}>
        {messages.map(m => (
          <Bubble key={m.id} role={m.role} name={m.name}>{m.content}</Bubble>
        ))}
        {sending && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '0 0 8px 4px' }}>
            <Spinner size={14} />
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Thinking…</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div style={S.quickRow}>
        {QUICK_ACTIONS.map(qa => (
          <button key={qa.label} style={S.quickBtn} onClick={() => send(qa.msg)}>{qa.label}</button>
        ))}
      </div>

      <div style={S.inputRow}>
        <textarea
          ref={inputRef}
          style={S.textarea}
          placeholder="Message NEXUS…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={1}
          disabled={sending}
        />
        <button style={{ ...S.sendBtn, opacity: !input.trim() || sending ? 0.4 : 1 }}
          onClick={() => send()} disabled={!input.trim() || sending}>
          ▷
        </button>
      </div>
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  messages: { flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column' },
  quickRow: { display: 'flex', gap: 6, padding: '6px 12px', overflowX: 'auto', flexShrink: 0,
    borderTop: '1px solid var(--border-subtle)', scrollbarWidth: 'none' },
  quickBtn: { flexShrink: 0, padding: '5px 10px', background: 'rgba(229,199,107,0.07)',
    border: '1px solid rgba(229,199,107,0.2)', borderRadius: 16, fontSize: 10, color: 'var(--gold)',
    cursor: 'pointer', whiteSpace: 'nowrap' },
  inputRow: { display: 'flex', gap: 8, padding: '8px 12px 12px', borderTop: '1px solid var(--border-subtle)', flexShrink: 0 },
  textarea: { flex: 1, background: 'var(--bg-card)', border: '1px solid var(--border-gold)',
    borderRadius: 10, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13,
    resize: 'none', fontFamily: 'inherit', outline: 'none', minHeight: 38, maxHeight: 100 },
  sendBtn: { width: 38, height: 38, borderRadius: 10, background: 'linear-gradient(135deg, #e5c76b, #b8923f)',
    border: 'none', color: '#14110a', fontSize: 16, cursor: 'pointer', display: 'flex',
    alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  modelPicker: { background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
    borderRadius: 6, color: 'var(--text-muted)', fontSize: 10, padding: '2px 6px' },
}

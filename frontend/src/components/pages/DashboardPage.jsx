import { useCallback, useEffect, useRef, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { sendChatMessage } from '../../hooks/useWebSocket'
import { Panel, Badge, StatusDot, GaugeRing, MiniBar, StatCard, TabBtn, AgentPill } from '../ui/primitives'

// ── Particle Map ──────────────────────────────────────────────────────────────
function ParticleMap() {
  const pts = [
    { x: '8%', y: '20%', g: false }, { x: '22%', y: '55%', g: true }, { x: '38%', y: '30%', g: false },
    { x: '50%', y: '65%', g: false }, { x: '62%', y: '18%', g: true }, { x: '75%', y: '45%', g: false },
    { x: '88%', y: '70%', g: false }, { x: '30%', y: '80%', g: true }, { x: '55%', y: '40%', g: false },
    { x: '70%', y: '25%', g: false }, { x: '15%', y: '65%', g: false }, { x: '45%', y: '85%', g: true },
  ]
  return (
    <div style={{ position: 'relative', flex: 1, borderRadius: 8, overflow: 'hidden', background: 'radial-gradient(ellipse at 50% 50%, rgba(30,22,10,0.8), rgba(5,6,10,0.98))', border: '1px solid rgba(229,199,107,0.08)' }}>
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(to right,rgba(229,199,107,0.04) 1px,transparent 1px),linear-gradient(to bottom,rgba(229,199,107,0.04) 1px,transparent 1px)', backgroundSize: '40px 40px' }} />
      <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
        {pts.slice(0, 8).map((p, i) => { const n = pts[(i + 1) % 8]; return <line key={i} x1={p.x} y1={p.y} x2={n.x} y2={n.y} stroke="rgba(229,199,107,0.12)" strokeWidth="1" /> })}
      </svg>
      {pts.map((p, i) => (
        <div key={i} style={{ position: 'absolute', left: p.x, top: p.y, transform: 'translate(-50%,-50%)' }}>
          <div style={{ width: p.g ? 9 : 6, height: p.g ? 9 : 6, borderRadius: '50%', background: p.g ? 'var(--gold-bright, #FFD97A)' : 'var(--teal, #20D6C7)', boxShadow: `0 0 ${p.g ? 16 : 10}px ${p.g ? 'rgba(229,199,107,0.8)' : 'rgba(32,214,199,0.6)'}` }} />
        </div>
      ))}
    </div>
  )
}

// ── Task Progress Bar ─────────────────────────────────────────────────────────
function TaskProgressBar({ task, progress, eta }) {
  return (
    <div style={{ padding: '8px 12px', borderRadius: 8, background: 'linear-gradient(90deg, rgba(229,199,107,0.06), rgba(205,127,50,0.03))', border: '1px solid rgba(229,199,107,0.2)', marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--gold-bright, #FFD97A)', boxShadow: '0 0 8px rgba(229,199,107,0.8)' }} />
          <span style={{ fontSize: 11, color: 'var(--text-primary, #F0E9D2)', fontWeight: 500 }}>{task}</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontFamily: 'monospace', fontSize: 10, color: 'rgba(255,255,255,0.35)' }}>ETA {eta}</span>
          <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--gold-bright, #FFD97A)', fontWeight: 600 }}>{progress}%</span>
        </div>
      </div>
      <div style={{ height: 4, background: 'rgba(0,0,0,0.4)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${progress}%`, height: '100%', background: 'linear-gradient(135deg, #FFD97A 0%, #E5C76B 40%, #B8923F 100%)', borderRadius: 2, boxShadow: '0 0 10px rgba(229,199,107,0.6)', transition: 'width .5s' }} />
      </div>
    </div>
  )
}

// ── Chat Panel ────────────────────────────────────────────────────────────────
function ChatPanel({ chat, isTyping, executionSteps }) {
  const [input, setInput] = useState('')
  const [micActive, setMicActive] = useState(false)
  const addMsg = useAppStore(s => s.addChatMessage)
  const endRef = useRef(null)
  const recogRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chat, isTyping])

  const send = useCallback((txt) => {
    const t = (txt || input).trim()
    if (!t) return
    addMsg({ role: 'user', content: t, ts: Date.now() })
    sendChatMessage(t)
    setInput('')
  }, [input, addMsg])

  const handleMic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { alert('Voice not supported in this browser.'); return }
    if (micActive) { recogRef.current?.stop(); return }
    const r = new SR()
    r.continuous = false; r.interimResults = true; r.lang = 'en-US'
    r.onstart = () => setMicActive(true)
    r.onresult = (e) => {
      const transcript = Array.from(e.results).map(res => res[0].transcript).join('')
      setInput(transcript)
      if (e.results[e.results.length - 1].isFinal) { send(transcript); setMicActive(false) }
    }
    r.onerror = () => setMicActive(false)
    r.onend = () => setMicActive(false)
    recogRef.current = r
    r.start()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      {isTyping && executionSteps?.length > 0 && <ThinkingProgress steps={executionSteps} />}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, paddingRight: 4 }}>
        {chat.map((msg, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{ maxWidth: '85%', padding: '9px 13px', borderRadius: 10, fontSize: 12, lineHeight: 1.6, background: msg.role === 'user' ? 'linear-gradient(135deg, rgba(229,199,107,0.14), rgba(205,127,50,0.06))' : 'var(--bg-elevated, #12141F)', border: `1px solid ${msg.role === 'user' ? 'rgba(229,199,107,0.3)' : 'rgba(229,199,107,0.08)'}`, color: 'var(--text-primary, #F0E9D2)', whiteSpace: 'pre-wrap' }}>
              {msg.content}
              {msg.attachments?.map((a, j) => (
                <div key={j} style={{ marginTop: 6 }}>
                  <a href={a.url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: 'var(--teal, #20D6C7)', textDecoration: 'underline' }}>{a.name || 'Download'}</a>
                </div>
              ))}
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', marginTop: 4, fontFamily: 'monospace' }}>{new Date(msg.ts || Date.now()).toLocaleTimeString('en-US', { hour12: false })}</div>
            </div>
          </div>
        ))}
        {isTyping && executionSteps?.length === 0 && (
          <div style={{ display: 'flex', gap: 4, padding: 4 }}>
            {[0, 1, 2].map(i => <span key={i} style={{ width: 5, height: 5, borderRadius: '50%', background: 'rgba(255,255,255,0.3)', animation: `blink .9s ${i * 0.2}s ease-in-out infinite`, display: 'inline-block' }} />)}
          </div>
        )}
        <div ref={endRef} />
      </div>
      <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
        <button onClick={handleMic} title={micActive ? 'Stop listening' : 'Voice input'} style={{ padding: '7px 10px', borderRadius: 8, border: `1px solid ${micActive ? 'rgba(239,68,68,0.6)' : 'rgba(229,199,107,0.2)'}`, background: micActive ? 'rgba(239,68,68,0.12)' : 'rgba(229,199,107,0.06)', color: micActive ? '#EF4444' : 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: 14, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 5 }}>
          🎤{micActive && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#EF4444', animation: 'blink .6s ease-in-out infinite' }} />}
        </button>
        <div style={{ flex: 1, display: 'flex', gap: 7, alignItems: 'center', border: `1px solid ${micActive ? 'rgba(239,68,68,0.3)' : 'rgba(229,199,107,0.2)'}`, borderRadius: 10, padding: '6px 6px 6px 12px', background: 'rgba(5,6,10,0.6)' }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder={micActive ? 'LISTENING…' : 'Instruct your AI employee…'}
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: micActive ? '#EF4444' : 'var(--text-primary, #F0E9D2)', fontSize: 12, fontFamily: 'inherit' }}
          />
          <button onClick={() => send()} style={{ background: 'linear-gradient(135deg, #FFD97A 0%, #E5C76B 40%, #B8923F 100%)', border: 'none', borderRadius: 7, padding: '7px 13px', cursor: 'pointer', color: '#1a1000', fontWeight: 700, fontSize: 11, letterSpacing: '0.04em' }}>SEND</button>
        </div>
      </div>
    </div>
  )
}

// ── Priority Alerts ───────────────────────────────────────────────────────────
function PriorityAlerts() {
  const alerts = [
    { sev: 'RED',    t: '14:20:30', msg: 'Agent output anomaly score 0.91 — exceeds threshold',    src: 'Blacklight Monitor' },
    { sev: 'ORANGE', t: '14:15:11', msg: 'Vector store capacity at 78% — pruning recommended',      src: 'Memory Indexer' },
    { sev: 'ORANGE', t: '13:58:02', msg: 'Hermes routing latency spiked to 82ms (normal: 12ms)',    src: 'Hermes Relay' },
    { sev: 'YELLOW', t: '13:22:44', msg: 'Memory Indexer agent health degraded to 74%',             src: 'Doctor Diagnostic' },
    { sev: 'YELLOW', t: '12:11:02', msg: 'Rate limit on external API approaching (84%)',             src: 'Gateway Monitor' },
  ]
  const sc = { RED: '#EF4444', ORANGE: '#F59E0B', YELLOW: '#EAB308' }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
        <StatCard label="Critical" value="1" color="#EF4444" sub="Immediate action required" accent />
        <StatCard label="Warning"  value="2" color="#F59E0B" sub="Monitor closely" />
        <StatCard label="Advisory" value="2" color="#EAB308" sub="No urgency" />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {alerts.map((a, i) => (
          <div key={i} style={{ padding: '11px 14px', borderRadius: 8, border: `1px solid ${sc[a.sev]}40`, background: `linear-gradient(90deg, ${sc[a.sev]}0C, transparent)`, display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 4, alignSelf: 'stretch', borderRadius: 2, background: sc[a.sev], boxShadow: `0 0 10px ${sc[a.sev]}` }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: 'var(--text-primary, #F0E9D2)', marginBottom: 3 }}>{a.msg}</div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace' }}>{a.src} · {a.t}</div>
            </div>
            <Badge label={a.sev} variant={a.sev === 'RED' ? 'error' : a.sev === 'ORANGE' ? 'warn' : 'gold'} />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── System Pipeline ───────────────────────────────────────────────────────────
function SystemPipeline() {
  const stages = [
    { label: 'Input',     in: '248/m', stat: 'healthy', load: 34 },
    { label: 'Agents',    in: '312/m', stat: 'healthy', load: 58 },
    { label: 'Memory',    in: '842/m', stat: 'warn',    load: 78 },
    { label: 'Reasoning', in: '184/m', stat: 'healthy', load: 42 },
    { label: 'Output',    in: '168/m', stat: 'healthy', load: 28 },
  ]
  const sc = { healthy: '#22C55E', warn: '#F59E0B', fail: '#EF4444' }
  return (
    <div>
      <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>LIVE DATA FLOW — Input → Agents → Memory → Reasoning → Output</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 4 }}>
        {stages.map((s, i) => (
          <div key={i} style={{ padding: '16px 14px', borderRadius: 10, border: `1px solid ${sc[s.stat]}44`, background: `linear-gradient(180deg, ${sc[s.stat]}12, var(--bg-card, #0C0E18))` }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Stage {i + 1}</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary, #F0E9D2)', marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontFamily: 'monospace', fontSize: 18, color: sc[s.stat], marginBottom: 8 }}>{s.in}</div>
            <MiniBar value={s.load} color={sc[s.stat]} />
            {s.stat === 'warn' && <div style={{ fontSize: 10, color: '#F59E0B', marginTop: 6, fontFamily: 'monospace' }}>⚠ Bottleneck</div>}
          </div>
        ))}
      </div>
      <div style={{ marginTop: 18, padding: '10px 14px', borderRadius: 8, background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}>
        <div style={{ fontSize: 11, color: '#F59E0B', fontWeight: 600, marginBottom: 3 }}>⚠ Bottleneck detected at Memory stage</div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary, #9A927E)' }}>Vector store capacity at 78%. Indexing latency increased 3.4×. Suggest triggering memory sweep.</div>
      </div>
    </div>
  )
}

// ── Execution Timeline ────────────────────────────────────────────────────────
function ExecutionTimeline({ logs }) {
  const runs = logs?.slice(0, 6).map((l, i) => ({
    id: l.id || `r${i}`, time: l.ts || '--:--:--', label: l.msg || l.message || 'Event',
    dur: l.duration || '—', ok: l.level !== 'ERROR' && l.ok !== false,
  })) || [
    { id: 'r1', time: '14:22:01', label: 'Revenue pathway analysis',    dur: '1.4s', ok: true },
    { id: 'r2', time: '14:21:44', label: 'Stripe deploy — module v2',   dur: '8.2s', ok: true },
    { id: 'r3', time: '14:20:55', label: 'Risk anomaly review',          dur: '0.8s', ok: false },
    { id: 'r4', time: '14:18:12', label: 'Memory sweep + compression',  dur: '4.1s', ok: true },
    { id: 'r5', time: '14:15:30', label: 'Market research batch',       dur: '12.3s', ok: true },
  ]
  const [sel, setSel] = useState(runs[0])
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 12 }}>
      <div>
        <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>Scroll back through past runs — click to replay</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {runs.map(r => (
            <div key={r.id} onClick={() => setSel(r)} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 12px', borderRadius: 8, border: `1px solid ${sel?.id === r.id ? 'rgba(229,199,107,0.4)' : 'rgba(229,199,107,0.08)'}`, background: sel?.id === r.id ? 'rgba(229,199,107,0.06)' : 'var(--bg-elevated, #12141F)', cursor: 'pointer' }}>
              <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'rgba(255,255,255,0.35)' }}>{r.time}</span>
              <span style={{ flex: 1, fontSize: 12, color: 'var(--text-primary, #F0E9D2)' }}>{r.label}</span>
              <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-secondary, #9A927E)' }}>{r.dur}</span>
              <Badge label={r.ok ? 'OK' : 'FAIL'} variant={r.ok ? 'green' : 'error'} />
            </div>
          ))}
        </div>
      </div>
      <div style={{ padding: 12, borderRadius: 8, background: 'var(--bg-elevated, #12141F)', border: '1px solid rgba(229,199,107,0.08)' }}>
        <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>Replay Detail</div>
        <div style={{ fontSize: 13, color: 'var(--gold-bright, #FFD97A)', fontWeight: 500, marginBottom: 8 }}>{sel?.label}</div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary, #9A927E)', lineHeight: 1.7, fontFamily: 'monospace' }}>
          <div>→ Status: {sel?.ok ? 'SUCCESS' : 'FAILED'}</div>
          <div>→ Duration: {sel?.dur}</div>
          <div>→ Timestamp: {sel?.time}</div>
        </div>
        <button style={{ width: '100%', marginTop: 14, padding: '8px', borderRadius: 7, border: '1px solid rgba(229,199,107,0.4)', background: 'rgba(229,199,107,0.1)', color: 'var(--gold-bright, #FFD97A)', cursor: 'pointer', fontSize: 11, fontFamily: 'monospace', letterSpacing: '0.06em' }}>▶ REPLAY RUN</button>
      </div>
    </div>
  )
}

// ── Resource Map ──────────────────────────────────────────────────────────────
function ResourceMap({ agents }) {
  const rows = agents?.slice(0, 8).map(a => ({
    name: a.name || a.id,
    cpu: a.cpu ?? Math.round(20 + (a.health ?? 50) * 0.5),
    ram: a.ram ?? Math.round(15 + (a.health ?? 50) * 0.4),
    tok: a.tokens ?? Math.round(2000 + Math.random() * 12000),
    waste: a.waste ?? Math.round(Math.random() * 25),
  })) || []

  if (!rows.length) return <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 12 }}>No agent data available</div>

  return (
    <div>
      <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>Per-agent utilization — highlight = waste zone</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr', gap: 8, padding: '6px 12px', fontSize: 9, color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          <span>Agent</span><span>CPU</span><span>RAM</span><span>Tokens</span><span>Waste</span>
        </div>
        {rows.map(a => (
          <div key={a.name} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr', gap: 8, padding: '9px 12px', borderRadius: 7, border: `1px solid ${a.waste > 10 ? 'rgba(245,158,11,0.25)' : 'rgba(229,199,107,0.08)'}`, background: a.waste > 10 ? 'rgba(245,158,11,0.04)' : 'var(--bg-elevated, #12141F)', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--text-primary, #F0E9D2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
            <div><MiniBar value={a.cpu} color={a.cpu > 60 ? '#F59E0B' : 'var(--teal, #20D6C7)'} /><span style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)' }}>{a.cpu}%</span></div>
            <div><MiniBar value={a.ram} color={a.ram > 70 ? '#F59E0B' : 'var(--gold, #E5C76B)'} /><span style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)' }}>{a.ram}%</span></div>
            <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-secondary, #9A927E)' }}>{a.tok.toLocaleString()}</span>
            <span style={{ fontFamily: 'monospace', fontSize: 11, color: a.waste > 10 ? '#F59E0B' : 'rgba(255,255,255,0.35)' }}>{a.waste}% {a.waste > 10 && '⚠'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── AI Pipeline Progress ──────────────────────────────────────────────────────
function ThinkingProgress({ steps }) {
  if (!steps?.length) return null
  return (
    <div style={{ margin: '6px 0', padding: '8px 12px', background: 'rgba(0,212,170,0.04)', border: '1px solid rgba(0,212,170,0.12)', borderRadius: 8, fontSize: 11 }}>
      <div style={{ color: 'rgba(255,255,255,0.3)', letterSpacing: '0.08em', marginBottom: 6, fontSize: 10, fontFamily: 'monospace' }}>AI PIPELINE</div>
      {steps.map((step, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0', color: 'var(--text-secondary, #9A927E)' }}>
          <span style={{ color: 'var(--teal, #20D6C7)', fontSize: 8 }}>✓</span>
          <span>{step.label}</span>
          {step.detail && <span style={{ color: 'rgba(255,255,255,0.3)' }}>· {step.detail}</span>}
        </div>
      ))}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0', color: 'var(--gold, #E5C76B)' }}>
        <span style={{ fontSize: 8 }}>⋯</span>
        <span>Thinking…</span>
      </div>
    </div>
  )
}

// ── What Changed ──────────────────────────────────────────────────────────────
function WhatChanged({ activity }) {
  const diffs = activity?.slice(0, 5).map(a => ({ when: 'recently', type: a.kind || 'event', text: a.message || a.notes || 'System event', dir: 'up' })) || [
    { when: '2h ago', type: 'behavior', text: 'Response avg length +18% after prompt v4.2 deploy',        dir: 'up' },
    { when: '5h ago', type: 'perf',     text: 'Memory lookup latency +3.4× — triggered indexer warning',  dir: 'up' },
    { when: '1d ago', type: 'quality',  text: 'Fairness score +1.4% — cultural sensitivity update',       dir: 'up' },
    { when: '2d ago', type: 'drift',    text: 'Response style drift detected — vocabulary shift +7%',     dir: 'neutral' },
    { when: '3d ago', type: 'capacity', text: 'Token usage per task +22% — code generation expanded',     dir: 'up' },
  ]
  return (
    <div>
      <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>System Behavior Changes — auto-detected drift</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {diffs.map((d, i) => (
          <div key={i} style={{ padding: '11px 14px', borderRadius: 8, border: '1px solid rgba(229,199,107,0.08)', background: 'var(--bg-elevated, #12141F)', display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: 18, color: d.dir === 'up' ? 'var(--gold-bright, #FFD97A)' : 'rgba(255,255,255,0.35)' }}>{d.dir === 'up' ? '↑' : '○'}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: 'var(--text-primary, #F0E9D2)' }}>{d.text}</div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', marginTop: 3, fontFamily: 'monospace' }}>{d.when} · {d.type}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const agents      = useAppStore(s => s.agents)
  const chatMessages = useAppStore(s => s.chatMessages)
  const isTyping    = useAppStore(s => s.isTyping)
  const systemStatus = useAppStore(s => s.systemStatus)
  const nnStatus    = useAppStore(s => s.nnStatus)
  const wsConnected = useAppStore(s => s.wsConnected)
  const activityFeed = useAppStore(s => s.activityFeed)
  const executionLogs   = useAppStore(s => s.executionLogs)
  const executionSteps  = useAppStore(s => s.executionSteps)

  const [view, setView] = useState('main')
  const [tab, setTab]   = useState('chat')
  const [agentTab, setAgentTab] = useState('active')

  const running = agents.filter(a => a.status === 'running')
  const busy    = agents.filter(a => a.status === 'busy')
  const idle    = agents.filter(a => a.status === 'idle')
  const shown   = agentTab === 'active' ? [...running, ...busy] : agentTab === 'idle' ? idle : agents

  const cpu  = Math.round(systemStatus?.cpu ?? systemStatus?.cpu_usage ?? 0)
  const ram  = Math.round(systemStatus?.memory ?? 0)
  const gpu  = Math.round(systemStatus?.gpu_usage ?? 0)
  const temp = Math.round(systemStatus?.cpu_temperature ?? 0)
  const mode = systemStatus?.mode ?? 'AUTONOMOUS'
  const conf = nnStatus?.confidence ?? 0
  const brainPct = conf > 1 ? Math.round(conf) : Math.round(conf * 100)
  const learnStep = nnStatus?.learn_step ?? 0
  const strategies = nnStatus?.total_actions ?? 47

  const VIEWS = ['main', 'alerts', 'pipeline', 'timeline', 'resources', 'changes']
  const VIEW_LABELS = { main: '◆ Mission Control', alerts: '◆ Priority Alerts', pipeline: '◆ System Pipeline', timeline: '◆ Execution Timeline', resources: '◆ Resource Map', changes: '◆ What Changed' }

  const logs = executionLogs?.map(l => ({ id: l.id || l.task_id, ts: l.ts || l.timestamp, msg: l.message || l.step || l.agent || 'Event', level: l.level, ok: l.level !== 'ERROR' }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>
      {/* View switcher */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px', background: 'linear-gradient(180deg, rgba(229,199,107,0.04), transparent)', border: '1px solid rgba(229,199,107,0.08)', borderRadius: 10, flexShrink: 0, flexWrap: 'wrap' }}>
        {VIEWS.map(v => <TabBtn key={v} label={VIEW_LABELS[v]} active={view === v} onClick={() => setView(v)} gold />)}
      </div>

      {view === 'main' && (
        <>
          {/* Metric cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10, flexShrink: 0 }}>
            <StatCard label="Active Agents"    value={running.length} sub={`${busy.length} busy · ${idle.length} idle`} />
            <StatCard label="Total Fleet"      value={agents.length}  sub={agents.length ? `${Math.round((running.length / agents.length) * 100)}% utilization` : '—'} />
            <StatCard label="Brain Confidence" value={`${brainPct}%`} sub={`Step ${learnStep.toLocaleString()}`} accent />
            <StatCard label="Gateway"          value={wsConnected ? 'ONLINE' : 'OFFLINE'} sub={wsConnected ? 'Realtime link stable' : 'Reconnecting…'} color={wsConnected ? 'var(--gold-bright, #FFD97A)' : '#EF4444'} />
            <StatCard label="Strategies"       value={strategies} sub={`${Math.round((nnStatus?.confidence ?? 0.91) > 1 ? nnStatus.confidence : (nnStatus?.confidence ?? 0.91) * 100)}% success`} color="var(--teal, #20D6C7)" />
          </div>

          {/* 3-column layout */}
          <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 260px', gap: 10, flex: 1, minHeight: 0 }}>
            {/* Agent Fleet */}
            <Panel title="Agent Fleet" badge={<Badge label={`${running.length} live`} variant="teal" />} bodyStyle={{ padding: 8 }}>
              <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                {['active', 'idle', 'all'].map(f => (
                  <button key={f} onClick={() => setAgentTab(f)} style={{ padding: '3px 9px', borderRadius: 999, border: 'none', cursor: 'pointer', fontSize: 10, fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', background: agentTab === f ? 'rgba(229,199,107,0.12)' : 'transparent', color: agentTab === f ? 'var(--gold-bright, #FFD97A)' : 'rgba(255,255,255,0.35)' }}>{f}</button>
                ))}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {shown.length ? shown.map(a => <AgentPill key={a.id} agent={a} />) : <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.25)', padding: 8 }}>No agents in this state</div>}
              </div>
            </Panel>

            {/* Orchestrator */}
            <Panel title="Orchestrator" badge={
              <div style={{ display: 'flex', gap: 3, padding: 3, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(229,199,107,0.08)', borderRadius: 999 }}>
                {['chat', 'live-map', 'logs'].map(t => (
                  <button key={t} onClick={() => setTab(t)} style={{ padding: '3px 10px', borderRadius: 999, border: 'none', fontSize: 10, fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', cursor: 'pointer', background: tab === t ? 'linear-gradient(135deg, #FFD97A 0%, #E5C76B 40%, #B8923F 100%)' : 'transparent', color: tab === t ? '#1a1000' : 'rgba(255,255,255,0.35)' }}>
                    {t === 'live-map' ? 'map' : t}
                  </button>
                ))}
              </div>
            } bodyStyle={{ padding: 12 }}>
              {tab === 'chat' && <ChatPanel chat={chatMessages} isTyping={isTyping} executionSteps={executionSteps} />}
              {tab === 'live-map' && (
                <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <ParticleMap />
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, flexShrink: 0 }}>
                    {[['Throughput', '3.4K/s', 'var(--teal, #20D6C7)'], ['Latency', '12ms', 'var(--gold-bright, #FFD97A)'], ['Errors', '0.02%', '#22C55E']].map(([l, v, c]) => (
                      <div key={l} style={{ padding: 8, borderRadius: 7, border: '1px solid rgba(229,199,107,0.08)', background: 'var(--bg-elevated, #12141F)', textAlign: 'center' }}>
                        <div style={{ fontFamily: 'monospace', fontSize: 15, color: c, fontWeight: 600 }}>{v}</div>
                        <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', letterSpacing: '0.06em', textTransform: 'uppercase', marginTop: 2 }}>{l}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {tab === 'logs' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5, overflowY: 'auto', height: '100%' }}>
                  {(executionLogs?.slice(0, 20) || []).map((log, i) => (
                    <div key={i} style={{ display: 'flex', gap: 10, fontFamily: 'monospace', fontSize: 10, padding: '5px 8px', borderRadius: 6, background: log.level === 'ERROR' ? 'rgba(239,68,68,0.05)' : log.level === 'WARN' ? 'rgba(245,158,11,0.05)' : 'var(--bg-elevated, #12141F)', border: `1px solid ${log.level === 'ERROR' ? 'rgba(239,68,68,0.15)' : log.level === 'WARN' ? 'rgba(245,158,11,0.15)' : 'rgba(229,199,107,0.08)'}` }}>
                      <span style={{ color: 'rgba(255,255,255,0.35)' }}>{log.ts || log.timestamp || ''}</span>
                      <span style={{ color: log.level === 'ERROR' ? '#EF4444' : log.level === 'WARN' ? '#F59E0B' : 'rgba(255,255,255,0.35)' }}>{log.level || 'INFO'}</span>
                      <span style={{ color: 'var(--text-secondary, #9A927E)', flex: 1 }}>{log.message || log.step || log.agent || JSON.stringify(log)}</span>
                    </div>
                  ))}
                  {!executionLogs?.length && <div style={{ color: 'rgba(255,255,255,0.25)', fontSize: 11, padding: 8 }}>No logs yet</div>}
                </div>
              )}
            </Panel>

            {/* Right column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
              <Panel title="System Health" bodyStyle={{ padding: 14 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, justifyItems: 'center' }}>
                  <GaugeRing value={cpu}  color="var(--teal, #20D6C7)"         label="CPU" />
                  <GaugeRing value={ram}  color="var(--gold-bright, #FFD97A)" label="RAM" />
                  <GaugeRing value={gpu}  color="var(--bronze, #CD7F32)"       label="GPU" />
                  <GaugeRing value={temp} color="#F59E0B"                      label="Temp" />
                </div>
              </Panel>
              <Panel title="Quick Actions">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {['Run Memory Sweep', 'Activate Money Mode', 'Deploy Forge', 'Emergency Halt'].map((l, i) => (
                    <button key={l} style={{ padding: '8px 10px', borderRadius: 7, border: `1px solid ${i === 3 ? 'rgba(239,68,68,0.3)' : 'rgba(229,199,107,0.22)'}`, background: i === 3 ? 'rgba(239,68,68,0.04)' : 'linear-gradient(135deg, rgba(229,199,107,0.07), transparent)', color: i === 3 ? '#EF4444' : 'var(--text-primary, #F0E9D2)', fontSize: 11, cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit' }}>{l}</button>
                  ))}
                </div>
              </Panel>
              <Panel title="Neural Brain" badge={<Badge label="LIVE" variant="green" />}>
                {[['Confidence', `${brainPct}%`, 'var(--gold-bright, #FFD97A)'], ['Learn Step', learnStep.toLocaleString(), 'var(--text-primary, #F0E9D2)'], ['Success', `${Math.round((nnStatus?.success_rate ?? 0.91) * 100)}%`, '#22C55E'], ['Strategies', strategies, 'var(--teal, #20D6C7)']].map(([l, v, c]) => (
                  <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-secondary, #9A927E)' }}>{l}</span>
                    <span style={{ fontFamily: 'monospace', fontSize: 12, color: c, fontWeight: 500 }}>{v}</span>
                  </div>
                ))}
                <MiniBar value={brainPct} color="var(--gold-bright, #FFD97A)" style={{ marginTop: 6 }} />
              </Panel>
            </div>
          </div>
        </>
      )}

      {view === 'alerts'    && <Panel title="Priority Alerts Engine" badge={<Badge label="5 TOTAL" variant="warn" />} style={{ flex: 1 }}><PriorityAlerts /></Panel>}
      {view === 'pipeline'  && <Panel title="System Pipeline" style={{ flex: 1 }}><SystemPipeline /></Panel>}
      {view === 'timeline'  && <Panel title="Execution Timeline (Replay)" style={{ flex: 1 }}><ExecutionTimeline logs={logs} /></Panel>}
      {view === 'resources' && <Panel title="Resource Utilization Map" style={{ flex: 1 }}><ResourceMap agents={agents} /></Panel>}
      {view === 'changes'   && <Panel title="What Changed? (Behavior Drift)" style={{ flex: 1 }}><WhatChanged activity={activityFeed} /></Panel>}
    </div>
  )
}

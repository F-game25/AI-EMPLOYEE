import { useEffect, useRef, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, Badge, MiniBar } from '../ui/primitives'
import api from '../../api/client'

const MODE_MAP = { PRECISION: 'SUPERVISED', BALANCED: 'AUTONOMOUS', SPEED: 'PASSIVE', COST: 'BUSINESS' }

const MODES = [
  { id: 'PRECISION', desc: 'Max accuracy · Higher cost · Slower',  sp: 25, co: 85, pr: 98, color: 'var(--gold-bright, #FFD97A)' },
  { id: 'BALANCED',  desc: 'Adaptive tradeoffs · Default',         sp: 65, co: 55, pr: 85, color: 'var(--teal, #20D6C7)' },
  { id: 'SPEED',     desc: 'Minimum latency · Reduced accuracy',    sp: 95, co: 45, pr: 72, color: 'var(--bronze, #CD7F32)' },
  { id: 'COST',      desc: 'Cheapest path · Capped quality',        sp: 55, co: 15, pr: 68, color: '#22C55E' },
]
const MODELS = [
  { name: 'claude-opus-4',   task: 'Reasoning', load: 42, calls: '842' },
  { name: 'claude-sonnet-4', task: 'Chat',      load: 71, calls: '3.2K' },
  { name: 'claude-haiku',    task: 'Quick',     load: 28, calls: '1.4K' },
  { name: 'gpt-4-turbo',     task: 'Code',      load: 35, calls: '612' },
]
const FALLBACK = [
  { step: 1, strategy: 'Primary execution',           ok: true  },
  { step: 2, strategy: 'Retry with modified prompt',  ok: true  },
  { step: 3, strategy: 'Escalate to Claude Opus',     ok: true  },
  { step: 4, strategy: 'Manual review queue',         ok: false },
]

export default function AIControlPage() {
  const systemStatus  = useAppStore(s => s.systemStatus)
  const executionLogs = useAppStore(s => s.executionLogs)
  const mode = systemStatus?.mode || 'BALANCED'

  const [promptOverride, setPromptOverride] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [injecting, setInjecting] = useState(false)
  const [injectResult, setInjectResult] = useState(null)

  const handleModeSwitch = async (id) => {
    try { await api.post('/api/mode', { mode: MODE_MAP[id] || 'AUTONOMOUS' }) } catch { /* ignore */ }
  }

  const handleInject = async () => {
    if (!promptOverride.trim()) return
    setInjecting(true); setInjectResult(null)
    try {
      await api.chat.send(`[SYSTEM OVERRIDE] ${promptOverride.trim()}`)
      setInjectResult({ ok: true, msg: 'Injected successfully' })
    } catch { setInjectResult({ ok: false, msg: 'Injection failed' }) }
    setInjecting(false)
  }

  const [cmdInput, setCmdInput] = useState('')
  const [cmds, setCmds] = useState([
    { id: 'c1', cmd: 'analyze revenue pathways --depth 3',           status: 'done', dur: '1.4s' },
    { id: 'c2', cmd: 'sync brain weights --nodes all',               status: 'done', dur: '3.1s' },
    { id: 'c3', cmd: 'deploy code-synth module stripe-v2',           status: 'done', dur: '8.2s' },
    { id: 'c4', cmd: 'run memory sweep --compress',                  status: 'done', dur: '4.1s' },
    { id: 'c5', cmd: 'analyze competitor pricing --sector saas',     status: 'done', dur: '2.1s' },
  ])
  const termRef = useRef(null)

  useEffect(() => { if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight }, [cmds])

  useEffect(() => {
    if (!executionLogs?.length) return
    const realCmds = executionLogs.slice(0, 3).map((l, i) => ({
      id: `real${i}${Date.now()}`, cmd: l.step || l.agent || l.message || 'system event',
      status: l.level === 'ERROR' ? 'error' : 'done', dur: l.duration || '—',
    }))
    setCmds(prev => [...realCmds, ...prev].slice(0, 20))
  }, [executionLogs?.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const runCmd = () => {
    const t = cmdInput.trim(); if (!t) return
    const id = `c${Date.now()}`
    setCmds(p => [...p, { id, cmd: t, status: 'running', dur: '...' }])
    setCmdInput('')
    setTimeout(() => setCmds(p => p.map(c => c.id === id ? { ...c, status: 'done', dur: `${(Math.random() * 3 + .5).toFixed(1)}s` } : c)), 1500)
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: 'auto 220px auto', gap: 10, height: '100%' }}>

      <Panel title="Mode Switching Matrix" badge={<Badge label={mode} variant="gold" />} style={{ gridColumn: '1/3' }} bodyStyle={{ padding: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
          {MODES.map(m => (
            <div key={m.id} onClick={() => handleModeSwitch(m.id)} style={{ padding: '11px 13px', borderRadius: 9, border: `1px solid ${mode === m.id ? m.color + '80' : 'rgba(229,199,107,0.08)'}`, background: mode === m.id ? `linear-gradient(180deg, ${m.color}18, transparent)` : 'var(--bg-elevated, #12141F)', cursor: 'pointer', boxShadow: mode === m.id ? `0 0 18px ${m.color}22` : 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: mode === m.id ? m.color : 'rgba(255,255,255,.15)', boxShadow: mode === m.id ? `0 0 8px ${m.color}` : 'none' }} />
                <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600, color: mode === m.id ? m.color : 'var(--text-secondary, #9A927E)', letterSpacing: '0.08em' }}>{m.id}</span>
              </div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', marginBottom: 9, minHeight: 26 }}>{m.desc}</div>
              {[['Speed', m.sp, 'var(--teal, #20D6C7)'], ['Cost', 100 - m.co, 'var(--gold-bright, #FFD97A)'], ['Precision', m.pr, 'var(--bronze, #CD7F32)']].map(([l, v, c]) => (
                <div key={l} style={{ marginBottom: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)', marginBottom: 2 }}><span>{l}</span><span>{v}%</span></div>
                  <MiniBar value={v} color={c} />
                </div>
              ))}
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Command Terminal" badge={<Badge label={`${cmds.length} entries`} variant="teal" />} bodyStyle={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div ref={termRef} style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, fontFamily: 'monospace' }}>
          {cmds.map(c => (
            <div key={c.id} style={{ fontSize: 10.5, padding: '5px 9px', borderRadius: 5, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(229,199,107,0.08)', display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ color: 'var(--gold-bright, #FFD97A)' }}>$</span>
              <span style={{ flex: 1, color: 'var(--text-secondary, #9A927E)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.cmd}</span>
              <span style={{ color: c.status === 'done' ? 'var(--teal, #20D6C7)' : c.status === 'error' ? '#EF4444' : '#F59E0B', fontSize: 9 }}>{c.dur}</span>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6, borderTop: '1px solid rgba(229,199,107,0.08)', paddingTop: 8 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--gold-bright, #FFD97A)', alignSelf: 'center' }}>$</span>
          <input value={cmdInput} onChange={e => setCmdInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && runCmd()} placeholder="type command…" style={{ flex: 1, background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(229,199,107,.18)', borderRadius: 6, padding: '6px 9px', color: 'var(--text-primary, #F0E9D2)', fontFamily: 'monospace', fontSize: 11, outline: 'none' }} />
          <button onClick={runCmd} style={{ background: 'linear-gradient(135deg, #FFD97A 0%, #E5C76B 40%, #B8923F 100%)', border: 'none', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', color: '#1a1000', fontWeight: 700, fontSize: 10, fontFamily: 'monospace' }}>RUN</button>
        </div>
      </Panel>

      <Panel title="Live Prompt Override" bodyStyle={{ padding: 12 }}>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', marginBottom: 8, letterSpacing: '0.06em' }}>INJECT MID-EXECUTION · APPLIED LIVE</div>
        <textarea value={promptOverride} onChange={e => setPromptOverride(e.target.value)} placeholder={'Add instructions… e.g. "prefer shorter answers"'} style={{ width: '100%', minHeight: 62, background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(229,199,107,0.2)', borderRadius: 7, padding: '8px 10px', color: 'var(--text-primary, #F0E9D2)', fontFamily: 'monospace', fontSize: 11, outline: 'none', resize: 'none', boxSizing: 'border-box' }} />
        {showPreview && promptOverride && (
          <div style={{ marginTop: 6, padding: '7px 10px', borderRadius: 6, background: 'rgba(229,199,107,0.04)', border: '1px solid rgba(229,199,107,0.15)', fontSize: 10, color: 'var(--gold-bright,#FFD97A)', fontFamily: 'monospace' }}>Preview: [SYSTEM OVERRIDE] {promptOverride}</div>
        )}
        <div style={{ display: 'flex', gap: 6, marginTop: 7 }}>
          <button onClick={handleInject} disabled={injecting || !promptOverride.trim()} style={{ flex: 1, padding: '7px', background: injecting ? 'rgba(229,199,107,0.1)' : 'linear-gradient(135deg, #FFD97A 0%, #E5C76B 40%, #B8923F 100%)', border: injecting ? '1px solid rgba(229,199,107,0.3)' : 'none', borderRadius: 7, color: injecting ? 'var(--gold,#E5C76B)' : '#1a1000', fontWeight: 700, fontSize: 10, cursor: injecting ? 'wait' : 'pointer', letterSpacing: '0.06em' }}>{injecting ? 'INJECTING...' : 'INJECT NOW'}</button>
          <button onClick={() => setShowPreview(p => !p)} style={{ padding: '7px 11px', background: showPreview ? 'rgba(229,199,107,0.08)' : 'transparent', border: `1px solid rgba(229,199,107,${showPreview ? '0.3' : '0.08'})`, borderRadius: 7, color: showPreview ? 'var(--gold-bright,#FFD97A)' : 'var(--text-secondary, #9A927E)', fontSize: 10, cursor: 'pointer' }}>PREVIEW</button>
        </div>
        {injectResult && (
          <div style={{ marginTop: 6, padding: '5px 8px', borderRadius: 5, fontSize: 10, fontFamily: 'monospace', color: injectResult.ok ? '#22C55E' : '#EF4444', background: injectResult.ok ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)', border: `1px solid ${injectResult.ok ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}` }}>{injectResult.ok ? '✓' : '✗'} {injectResult.msg}</div>
        )}
        {!injectResult && <div style={{ marginTop: 10, padding: '7px 10px', borderRadius: 6, background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.18)', fontSize: 10, color: '#22C55E', fontFamily: 'monospace' }}>✓ Drift detector monitoring active</div>}
      </Panel>

      <Panel title="Multi-Model Routing">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {MODELS.map(m => (
            <div key={m.name} style={{ padding: '8px 10px', borderRadius: 7, border: '1px solid rgba(229,199,107,0.08)', background: 'var(--bg-elevated, #12141F)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-primary, #F0E9D2)' }}>{m.name}</span>
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)' }}>{m.calls} · {m.task}</span>
              </div>
              <MiniBar value={m.load} color={m.load > 60 ? 'var(--gold-bright, #FFD97A)' : 'var(--teal, #20D6C7)'} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Response Quality Scoring" style={{ gridColumn: '1/2' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 10 }}>
          {[['Structure', '94', 'var(--gold-bright, #FFD97A)'], ['Usefulness', '89', 'var(--teal, #20D6C7)'], ['Correctness', '96', '#22C55E']].map(([l, v, c]) => (
            <div key={l} style={{ padding: 9, borderRadius: 7, border: '1px solid rgba(229,199,107,0.08)', background: 'var(--bg-elevated, #12141F)', textAlign: 'center' }}>
              <div style={{ fontFamily: 'monospace', fontSize: 18, color: c, fontWeight: 600 }}>{v}</div>
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{l}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', marginBottom: 6, letterSpacing: '0.06em' }}>7-DAY TREND</div>
        <svg viewBox="0 0 240 44" style={{ width: '100%', height: 44 }}>
          <polyline points="0,30 40,28 80,22 120,25 160,16 200,14 240,10" fill="none" stroke="var(--gold-bright, #FFD97A)" strokeWidth="1.5" />
          <polyline points="0,30 40,28 80,22 120,25 160,16 200,14 240,10 240,44 0,44" fill="rgba(229,199,107,0.12)" />
        </svg>
      </Panel>

      <Panel title="Failure Recovery Chain" style={{ gridColumn: '2/3' }}>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', marginBottom: 8, letterSpacing: '0.06em' }}>AUTO-RETRY WITH MODIFIED STRATEGY</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {FALLBACK.map(f => (
            <div key={f.step} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', borderRadius: 6, border: `1px solid ${f.ok ? 'rgba(34,197,94,0.18)' : 'rgba(255,255,255,0.08)'}`, background: 'var(--bg-elevated, #12141F)' }}>
              <div style={{ width: 22, height: 22, borderRadius: '50%', background: f.ok ? 'rgba(34,197,94,0.15)' : 'rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', fontSize: 10, color: f.ok ? '#22C55E' : 'rgba(255,255,255,0.35)', fontWeight: 700 }}>{f.step}</div>
              <span style={{ flex: 1, fontSize: 11.5, color: f.ok ? 'var(--text-primary, #F0E9D2)' : 'rgba(255,255,255,0.35)' }}>{f.strategy}</span>
              <span style={{ fontSize: 10, color: f.ok ? '#22C55E' : 'rgba(255,255,255,0.35)', fontFamily: 'monospace' }}>{f.ok ? 'OK' : 'IDLE'}</span>
            </div>
          ))}
        </div>
      </Panel>

    </div>
  )
}

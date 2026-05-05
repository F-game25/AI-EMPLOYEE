import { useEffect, useRef, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, StatusPill, HexButton, SectionLabel, LiveBadge, HexFrame, Sparkline } from '../nexus-ui'
import { MiniBar } from '../ui/primitives'
import api from '../../api/client'
import './AIControlPage.css'

const MODE_MAP = { PRECISION: 'SUPERVISED', BALANCED: 'AUTONOMOUS', SPEED: 'PASSIVE', COST: 'BUSINESS' }

const MODES = [
  { id: 'PRECISION', icon: '◆', desc: 'Max accuracy · Higher cost · Slower',  sp: 25, co: 85, pr: 98, tone: 'gold' },
  { id: 'BALANCED',  icon: '⊕', desc: 'Adaptive tradeoffs · Default',         sp: 65, co: 55, pr: 85, tone: 'cool' },
  { id: 'SPEED',     icon: '⚡', desc: 'Minimum latency · Reduced accuracy',   sp: 95, co: 45, pr: 72, tone: 'warn' },
  { id: 'COST',      icon: '◯', desc: 'Cheapest path · Capped quality',       sp: 55, co: 15, pr: 68, tone: 'success' },
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

const QUALITY_TREND = [62, 68, 71, 74, 76, 81, 84, 88, 90, 92, 94, 96]

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
    <div className="aic-grid">
      {/* Mode Matrix — full width */}
      <Panel
        icon="◈"
        title="Mode Switching Matrix"
        actions={<StatusPill tone="gold" label={mode} />}
        className="aic-modes"
      >
        <div className="aic-modes__grid">
          {MODES.map(m => {
            const active = mode === m.id
            return (
              <button
                key={m.id}
                type="button"
                className={`aic-mode ${active ? 'aic-mode--active' : ''} aic-mode--${m.tone}`}
                onClick={() => handleModeSwitch(m.id)}
              >
                <div className="aic-mode__head">
                  <HexFrame size="sm" tone={m.tone} glow={active}>
                    <span style={{ fontSize: 12 }}>{m.icon}</span>
                  </HexFrame>
                  <span className="aic-mode__id">{m.id}</span>
                  {active && <span className="aic-mode__active-dot" aria-hidden="true" />}
                </div>
                <div className="aic-mode__desc">{m.desc}</div>
                {[
                  ['Speed',     m.sp,        'var(--nx-info)'],
                  ['Cost',      100 - m.co,  'var(--nx-gold)'],
                  ['Precision', m.pr,        'var(--nx-success)'],
                ].map(([l, v, c]) => (
                  <div key={l} className="aic-mode__metric">
                    <div className="aic-mode__metric-row">
                      <span>{l}</span><span>{v}%</span>
                    </div>
                    <MiniBar value={v} color={c} />
                  </div>
                ))}
              </button>
            )
          })}
        </div>
      </Panel>

      {/* Terminal */}
      <Panel
        icon="⌖"
        title="Command Terminal"
        actions={<LiveBadge variant="live" label={`${cmds.length} ENTRIES`} />}
        tight
      >
        <div ref={termRef} className="aic-term">
          {cmds.map(c => (
            <div key={c.id} className={`aic-term__row aic-term__row--${c.status}`}>
              <span className="aic-term__sigil">$</span>
              <span className="aic-term__cmd">{c.cmd}</span>
              <span className="aic-term__dur">{c.dur}</span>
            </div>
          ))}
        </div>
        <div className="aic-term__input">
          <span className="aic-term__sigil">$</span>
          <input
            value={cmdInput}
            onChange={e => setCmdInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && runCmd()}
            placeholder="type command…"
          />
          <HexButton size="sm" variant="primary" onClick={runCmd}>RUN</HexButton>
        </div>
      </Panel>

      {/* Prompt Override */}
      <Panel
        icon="⊘"
        title="Live Prompt Override"
        actions={<StatusPill tone="success" label="DRIFT MONITORED" size="sm" />}
        tight
      >
        <SectionLabel size="sm" tone="dim">Inject mid-execution · applied live</SectionLabel>
        <textarea
          className="aic-prompt"
          value={promptOverride}
          onChange={e => setPromptOverride(e.target.value)}
          placeholder={'Add instructions… e.g. "prefer shorter answers"'}
        />
        {showPreview && promptOverride && (
          <div className="aic-prompt__preview">Preview: [SYSTEM OVERRIDE] {promptOverride}</div>
        )}
        <div className="aic-prompt__actions">
          <HexButton
            variant="primary"
            size="sm"
            full
            loading={injecting}
            disabled={!promptOverride.trim()}
            onClick={handleInject}
          >
            {injecting ? 'INJECTING…' : 'INJECT NOW'}
          </HexButton>
          <HexButton
            variant={showPreview ? 'outline' : 'ghost'}
            size="sm"
            onClick={() => setShowPreview(p => !p)}
          >
            PREVIEW
          </HexButton>
        </div>
        {injectResult && (
          <div className={`aic-prompt__result aic-prompt__result--${injectResult.ok ? 'ok' : 'err'}`}>
            {injectResult.ok ? '✓' : '✗'} {injectResult.msg}
          </div>
        )}
      </Panel>

      {/* Multi-Model */}
      <Panel icon="⌬" title="Multi-Model Routing">
        <div className="aic-models">
          {MODELS.map(m => (
            <div key={m.name} className="aic-model">
              <div className="aic-model__head">
                <span className="aic-model__name">{m.name}</span>
                <span className="aic-model__meta">{m.calls} · {m.task}</span>
              </div>
              <MiniBar value={m.load} color={m.load > 60 ? 'var(--nx-gold)' : 'var(--nx-info)'} />
            </div>
          ))}
        </div>
      </Panel>

      {/* Quality */}
      <Panel icon="✦" title="Response Quality">
        <div className="aic-quality">
          {[['STRUCTURE', '94', 'gold'], ['USEFULNESS', '89', 'cool'], ['CORRECTNESS', '96', 'success']].map(([l, v, t]) => (
            <div key={l} className={`aic-quality__cell aic-quality__cell--${t}`}>
              <div className="aic-quality__val">{v}</div>
              <div className="aic-quality__label">{l}</div>
            </div>
          ))}
        </div>
        <SectionLabel size="sm" tone="dim" rule>7-Day Trend</SectionLabel>
        <div className="aic-quality__spark">
          <Sparkline data={QUALITY_TREND} color="#e5c76b" thickness={1.6} height={44} width={400} />
        </div>
      </Panel>

      {/* Fallback */}
      <Panel icon="⛨" title="Failure Recovery Chain">
        <SectionLabel size="sm" tone="dim">Auto-retry with modified strategy</SectionLabel>
        <div className="aic-fallback">
          {FALLBACK.map(f => (
            <div key={f.step} className={`aic-fallback__row ${f.ok ? 'is-ok' : 'is-idle'}`}>
              <div className="aic-fallback__step">{f.step}</div>
              <span className="aic-fallback__strategy">{f.strategy}</span>
              <StatusPill tone={f.ok ? 'success' : 'idle'} label={f.ok ? 'OK' : 'IDLE'} dot={false} size="sm" />
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

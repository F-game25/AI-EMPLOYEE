import { useState, useRef, useEffect } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, KPITile, StatusPill, HexButton, SectionLabel } from '../nexus-ui'
import './AscendForgePage.css'

const OBJECTIVES = [
  { id: 'obj-1', title: 'Monetization Pipeline v2', phase: 'EXECUTE', progress: 72, priority: 'HIGH', due: 'Apr 30', tasks: 8, done: 6, revenue: '$12K/mo target', owner: 'Orchestrator Prime' },
  { id: 'obj-2', title: 'Competitor Intelligence System', phase: 'BUILD', progress: 45, priority: 'HIGH', due: 'May 5', tasks: 5, done: 2, revenue: 'Strategic', owner: 'Data Harvester' },
  { id: 'obj-3', title: 'Automated Outreach Engine', phase: 'PLAN', progress: 20, priority: 'MED', due: 'May 15', tasks: 7, done: 1, revenue: '$8K/mo target', owner: 'Strategy Engine' },
  { id: 'obj-4', title: 'AI Cost Optimization Suite', phase: 'REVIEW', progress: 90, priority: 'MED', due: 'Apr 28', tasks: 4, done: 4, revenue: '-$2K/mo cost', owner: 'Risk Auditor' },
]

const MILESTONES = [
  { label: 'Stripe webhook live', done: true, ts: 'Apr 22' },
  { label: 'Revenue model v1 deployed', done: true, ts: 'Apr 23' },
  { label: 'First $500 automated', done: true, ts: 'Apr 24' },
  { label: 'Agent fleet at 15 bots', done: false, ts: 'Apr 29' },
  { label: 'Reach $5K MRR milestone', done: false, ts: 'May 10' },
  { label: 'Launch outreach engine', done: false, ts: 'May 15' },
]

const INSIGHTS = [
  { text: 'Revenue pathway #1 has 3.2× ROI vs pathway #2 — reallocate agent hours', tone: 'gold' },
  { text: 'Competitor pricing dropped 12% — opportunity to capture SMB segment', tone: 'bronze' },
  { text: 'API cost optimization saves est. $340/mo — approve and deploy', tone: 'success' },
]

const PHASE_TONE = { EXECUTE: 'gold', BUILD: 'bronze', PLAN: 'idle', REVIEW: 'success' }

function CodingAISection() {
  const [provider, setProvider] = useState('anthropic')
  const [model, setModel] = useState('claude-sonnet-4-6')
  const [apiKey, setApiKey] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [models, setModels] = useState([])
  const messagesEndRef = useRef(null)

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const res = await fetch('/api/system/settings/coding-ai')
        const data = await res.json()
        if (data.provider) setProvider(data.provider)
        if (data.model) setModel(data.model)
      } catch (err) {
        console.log('Settings load skipped:', err.message)
      }
    }
    loadSettings()
  }, [])

  useEffect(() => {
    const defaultModels = { anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'], openrouter: ['deepseek/deepseek-coder-v2', 'anthropic/claude-3.5-sonnet'], ollama: [] }
    setModels(defaultModels[provider] || [])
    if (defaultModels[provider].length > 0) setModel(defaultModels[provider][0])
  }, [provider])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim()) return
    const userMsg = { role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('/api/forge/code-ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model, messages: [...messages, userMsg], systemPrompt: 'You are an expert coding assistant.' }),
      })
      const data = await res.json()
      if (data.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.response }])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.error}` }])
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    }
    setLoading(false)
  }

  return (
    <Panel
      icon="⚛"
      title="Coding AI Assistant"
      className="af-panel"
      actions={<StatusPill tone="bronze" label={provider.toUpperCase()} dot={false} size="sm" />}
    >
      <div className="af-ai-config">
        <select value={provider} onChange={e => setProvider(e.target.value)} className="af-ai-input">
          <option value="anthropic">Claude (Anthropic)</option>
          <option value="openrouter">OpenRouter</option>
          <option value="ollama">Ollama (Local)</option>
        </select>
        <select value={model} onChange={e => setModel(e.target.value)} className="af-ai-input">
          {models.map(m => <option key={m} value={m}>{m.split('/').pop()}</option>)}
        </select>
        {provider === 'openrouter' && (
          <>
            <input type="password" placeholder="API Key" value={apiKey} onChange={e => setApiKey(e.target.value)} className="af-ai-input" />
            <button onClick={async () => {
              await fetch('/api/system/settings/coding-ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider, model, openrouter_api_key: apiKey })
              });
              setApiKey('');
            }} className="af-ai-save">SAVE</button>
          </>
        )}
      </div>

      <div className="af-chat">
        {messages.map((msg, i) => (
          <div key={i} className={`af-msg af-msg--${msg.role}`}>
            <div className={`af-msg__bubble af-msg__bubble--${msg.role}`}>
              {msg.role === 'assistant' && msg.content.includes('```') ? (
                <div dangerouslySetInnerHTML={{ __html: msg.content.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,0.4);padding:8px;borderRadius:4px;overflow:auto;fontSize:9px"><code>$2</code></pre>').replace(/\n/g, '<br/>') }} />
              ) : (
                <span>{msg.content}</span>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="af-thinking">Thinking…</div>}
        <div ref={messagesEndRef} />
      </div>

      <div className="af-input-row">
        <input type="text" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()} placeholder="Ask a coding question…" disabled={loading} className="af-input" />
        <HexButton onClick={handleSend} disabled={loading || !input.trim()} size="sm">SEND</HexButton>
      </div>
    </Panel>
  )
}

export default function AscendForgePage() {
  const store = useAppStore(s => s.objectivePanels?.ascend_forge)
  const [sel, setSel] = useState(null)
  const objectives = store?.objectives?.length ? store.objectives : OBJECTIVES
  const selObj = sel ?? objectives[0]

  const totalProgress = Math.round(objectives.reduce((a, o) => a + o.progress, 0) / objectives.length)
  const executing = objectives.filter(o => o.phase === 'EXECUTE' || o.phase === 'BUILD').length

  return (
    <div className="af-grid">
      <div className="af-shimmer" />

      <div className="af-kpis">
        <KPITile icon="◈" iconTone="gold" label="Overall Progress" value={`${totalProgress}%`} sub="Across all objectives" />
        <KPITile icon="⊙" iconTone="bronze" label="Active Objectives" value={executing} sub={`of ${objectives.length} total`} />
        <KPITile icon="✓" iconTone="success" label="Milestones Done" value={MILESTONES.filter(m => m.done).length} sub={`of ${MILESTONES.length} total`} />
        <KPITile icon="💰" iconTone="gold" label="Est. Revenue" value="$20K/mo" sub="When objectives complete" />
      </div>

      <div className="af-cols">
        <div className="af-col">
          <Panel icon="◐" title="Strategic Objectives" className="af-panel" actions={<StatusPill tone="bronze" label="FORGE ACTIVE" dot={false} size="sm" />}>
            <div className="af-objectives">
              {objectives.map(o => (
                <button key={o.id} onClick={() => setSel(o)} className={`af-objective ${selObj?.id === o.id ? 'is-selected' : ''}`}>
                  <div className="af-objective__head">
                    <StatusPill tone={PHASE_TONE[o.phase]} label={o.phase} dot={false} size="xs" />
                    <span className="af-objective__title">{o.title}</span>
                    <span className={`af-objective__priority ${o.priority === 'HIGH' ? 'is-high' : ''}`}>{o.priority}</span>
                  </div>
                  <div className="af-objective__bar">
                    <div className="af-objective__progress" style={{ width: `${o.progress}%` }} />
                  </div>
                  <div className="af-objective__meta">
                    <span>{o.owner}</span>
                    <span>{o.done}/{o.tasks} tasks · due {o.due}</span>
                    <span className="af-objective__pct">{o.progress}%</span>
                  </div>
                </button>
              ))}
            </div>
          </Panel>

          <Panel icon="💡" title="Strategic Insights" className="af-panel af-col__grow">
            <div className="af-insights">
              {INSIGHTS.map((ins, i) => (
                <div key={i} className={`af-insight af-insight--${ins.tone}`}>
                  <div className="af-insight__rail" />
                  <span className="af-insight__text">{ins.text}</span>
                </div>
              ))}
            </div>
          </Panel>

          {selObj && (
            <Panel icon="◈" title={selObj.title} className="af-panel" actions={<StatusPill tone={PHASE_TONE[selObj.phase]} label={selObj.phase} dot={false} size="sm" />}>
              <div className="af-detail">
                {[
                  ['Priority', selObj.priority, selObj.priority === 'HIGH' ? 'alert' : 'warning'],
                  ['Progress', `${selObj.progress}%`, 'bronze'],
                  ['Tasks', `${selObj.done}/${selObj.tasks} done`, null],
                  ['Due', selObj.due, null],
                  ['Owner', selObj.owner, 'bronze'],
                  ['Revenue', selObj.revenue, 'success'],
                ].map(([label, value, tone]) => (
                  <div key={label} className="af-detail__row">
                    <span className="af-detail__label">{label}</span>
                    <span className={`af-detail__val ${tone ? `af-detail__val--${tone}` : ''}`}>{value}</span>
                  </div>
                ))}
                <div className="af-detail__bar">
                  <div className="af-detail__progress" style={{ width: `${selObj.progress}%` }} />
                </div>
                <div className="af-detail__cta">
                  <HexButton variant="primary" tone="gold" size="sm">EXECUTE</HexButton>
                  <HexButton variant="outline" size="sm">PAUSE</HexButton>
                </div>
              </div>
            </Panel>
          )}
        </div>

        <div className="af-col">
          <CodingAISection />

          <Panel icon="🎯" title="Forge Milestones" className="af-panel">
            <div className="af-milestones">
              {MILESTONES.map((m, i) => (
                <div key={i} className={`af-milestone ${m.done ? 'is-done' : ''}`}>
                  <div className="af-milestone__dot" />
                  <span className="af-milestone__label">{m.label}</span>
                  <span className="af-milestone__ts">{m.ts}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel icon="🔥" title="Forge Heat" className="af-panel af-col__grow">
            <svg viewBox="0 0 240 36" className="af-heatchart">
              <defs>
                <linearGradient id="af-heat-g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--nx-gold-warm)" stopOpacity=".5" />
                  <stop offset="100%" stopColor="var(--nx-bronze)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <polyline points="0,30 20,26 40,18 60,22 80,10 100,16 120,6 140,12 160,8 180,14 200,10 220,16 240,12" fill="none" stroke="var(--nx-gold-bright)" strokeWidth="1.5" />
              <polygon points="0,30 20,26 40,18 60,22 80,10 100,16 120,6 140,12 160,8 180,14 200,10 220,16 240,12 240,36 0,36" fill="url(#af-heat-g)" />
            </svg>
            <SectionLabel size="sm" tone="bronze">EXECUTION INTENSITY — LIVE</SectionLabel>
          </Panel>
        </div>
      </div>
    </div>
  )
}

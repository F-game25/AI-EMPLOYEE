import { useState, useRef, useEffect, useCallback } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, KPITile, StatusPill, HexButton, SectionLabel } from '../nexus-ui'
import FileUploadZone from '../workspace/FileUploadZone'
import './AscendForgePage.css'

const OBJECTIVES = [
  { id: 'obj-1', title: 'Monetization Pipeline v2', phase: 'EXECUTE', progress: 72, priority: 'HIGH', due: 'Apr 30', tasks: 8, done: 6, revenue: '$12K/mo target', owner: 'Orchestrator Prime', description: 'Implement revenue tracking and automated payment processing integration with Stripe webhooks and financial reporting.' },
  { id: 'obj-2', title: 'Competitor Intelligence System', phase: 'BUILD', progress: 45, priority: 'HIGH', due: 'May 5', tasks: 5, done: 2, revenue: 'Strategic', owner: 'Data Harvester', description: 'Build competitive analysis tools to track market movements and pricing changes in real-time.' },
  { id: 'obj-3', title: 'Automated Outreach Engine', phase: 'PLAN', progress: 20, priority: 'MED', due: 'May 15', tasks: 7, done: 1, revenue: '$8K/mo target', owner: 'Strategy Engine', description: 'Develop personalized outreach workflow with AI-driven messaging and lead scoring.' },
  { id: 'obj-4', title: 'AI Cost Optimization Suite', phase: 'REVIEW', progress: 90, priority: 'MED', due: 'Apr 28', tasks: 4, done: 4, revenue: '-$2K/mo cost', owner: 'Risk Auditor', description: 'Optimize API call costs and infrastructure expenses through intelligent resource allocation.' },
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
  const [showAnalysis, setShowAnalysis] = useState(false)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [analysisResults, setAnalysisResults] = useState(null)
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
    const defaultModels = {
      anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'],
      openrouter: ['deepseek/deepseek-coder-v2', 'anthropic/claude-3.5-sonnet'],
      ollama: []
    }
    setModels(defaultModels[provider] || [])
    if (defaultModels[provider].length > 0) setModel(defaultModels[provider][0])
  }, [provider])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleFileUploadComplete = useCallback(async () => {
    const fileInput = document.querySelector('.fuz-zone-content input[type="file"]')
    if (fileInput?.files?.[0]) {
      const file = fileInput.files[0]
      const reader = new FileReader()
      reader.onload = async (e) => {
        const content = e.target.result
        setUploadedFile({ name: file.name, content })
        setAnalysisResults(null)

        try {
          const ext = (file.name.split('.').pop() || '').toLowerCase()
          const langMap = {
            py: 'python', js: 'javascript', ts: 'typescript', jsx: 'jsx', tsx: 'tsx',
            sh: 'bash', md: 'markdown', html: 'html', css: 'css', json: 'json', txt: 'text',
          }
          const language = langMap[ext] || 'text'

          const res = await fetch('/api/codex/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              file_name: file.name,
              content,
              language,
            }),
          })
          if (res.ok) {
            const data = await res.json()
            setAnalysisResults(data.data || data)
          }
        } catch (err) {
          console.error('Analysis failed:', err)
        }
      }
      reader.readAsText(file)
    }
  }, [])

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
        body: JSON.stringify({
          provider,
          model,
          messages: [...messages, userMsg],
          systemPrompt: 'You are an expert coding assistant helping developers improve code quality, performance, and maintainability.',
          context: analysisResults ? { analysis: analysisResults, file: uploadedFile?.name } : undefined,
        }),
      })
      const data = await res.json()
      if (data.ok || data.response) {
        const assistantMsg = { role: 'assistant', content: data.response || data.message }
        setMessages(prev => [...prev, assistantMsg])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.error || 'Unknown error'}` }])
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    }
    setLoading(false)
  }

  const suggestImprovements = () => {
    if (!analysisResults) return
    const bugCount = (analysisResults.bugs || []).length
    const styleCount = (analysisResults.style_issues || []).length
    const perfCount = (analysisResults.perf_concerns || []).length
    const suggestion = `I've analyzed the code and found ${bugCount} bugs, ${styleCount} style issues, and ${perfCount} performance concerns. Can you suggest specific fixes for the highest-priority issues?`
    setInput(suggestion)
  }

  const handleSaveSettings = async () => {
    try {
      await fetch('/api/system/settings/coding-ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model, openrouter_api_key: apiKey })
      })
      setApiKey('')
    } catch (err) {
      console.error('Failed to save settings:', err)
    }
  }

  return (
    <Panel
      icon="⚛"
      title="Coding AI Assistant"
      className="af-panel"
      actions={<StatusPill tone="bronze" label={provider.toUpperCase()} dot={false} size="sm" />}
    >
      <div className="af-upload-section">
        <SectionLabel size="xs" tone="gold">Upload Code for Analysis</SectionLabel>
        <FileUploadZone apiUrl="" onUploadComplete={handleFileUploadComplete} />
      </div>

      {uploadedFile && analysisResults && (
        <div className="af-analysis-summary">
          <div className="af-summary-header">
            <SectionLabel size="xs" tone="gold">Analysis Results</SectionLabel>
            <button className="af-summary-toggle" onClick={() => setShowAnalysis(!showAnalysis)}>
              {showAnalysis ? 'Hide' : 'Show'} Details
            </button>
          </div>

          <div className="af-summary-stats">
            <div className={`af-stat af-stat--bug ${(analysisResults.bugs || []).length > 0 ? 'has-issues' : ''}`}>
              <span className="af-stat__label">Bugs</span>
              <span className="af-stat__value">{(analysisResults.bugs || []).length}</span>
            </div>
            <div className={`af-stat af-stat--style ${(analysisResults.style_issues || []).length > 0 ? 'has-issues' : ''}`}>
              <span className="af-stat__label">Style</span>
              <span className="af-stat__value">{(analysisResults.style_issues || []).length}</span>
            </div>
            <div className={`af-stat af-stat--perf ${(analysisResults.perf_concerns || []).length > 0 ? 'has-issues' : ''}`}>
              <span className="af-stat__label">Performance</span>
              <span className="af-stat__value">{(analysisResults.perf_concerns || []).length}</span>
            </div>
          </div>

          {showAnalysis && (
            <div className="af-analysis-details">
              {(analysisResults.bugs || []).length > 0 && (
                <div className="af-detail-section">
                  <h4>Bugs Found</h4>
                  <ul>
                    {analysisResults.bugs.slice(0, 3).map((bug, i) => (
                      <li key={i} className="af-issue-item">
                        <code>{bug.description || bug.message || 'Unknown bug'}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {(analysisResults.style_issues || []).length > 0 && (
                <div className="af-detail-section">
                  <h4>Style Issues</h4>
                  <ul>
                    {analysisResults.style_issues.slice(0, 2).map((style, i) => (
                      <li key={i} className="af-issue-item">
                        <code>{style.description || style.message || 'Style violation'}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <button className="af-suggest-btn" onClick={suggestImprovements}>
            Get AI Improvement Suggestions
          </button>
        </div>
      )}

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
            <input
              type="password"
              placeholder="API Key"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              className="af-ai-input"
            />
            <HexButton onClick={handleSaveSettings} size="sm" tone="gold">SAVE</HexButton>
          </>
        )}
      </div>

      <div className="af-chat">
        {messages.length === 0 && (
          <div className="af-chat-empty">
            <p>Upload code and ask for improvements, or ask general coding questions.</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`af-msg af-msg--${msg.role}`}>
            <div className={`af-msg__bubble af-msg__bubble--${msg.role}`}>
              {msg.role === 'assistant' && msg.content.includes('```') ? (
                <div dangerouslySetInnerHTML={{
                  __html: msg.content
                    .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,0.4);padding:8px;borderRadius:4px;overflow:auto;fontSize:10px"><code>$2</code></pre>')
                    .replace(/\n/g, '<br/>')
                }}
                />
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
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder="Ask a coding question…"
          disabled={loading}
          className="af-input"
        />
        <HexButton onClick={handleSend} disabled={loading || !input.trim()} size="sm">
          SEND
        </HexButton>
      </div>
    </Panel>
  )
}

export default function AscendForgePage() {
  const store = useAppStore(s => s.objectivePanels?.ascend_forge)
  const [sel, setSel] = useState(null)
  const [milestones, setMilestones] = useState(MILESTONES)

  const objectives = store?.objectives?.length ? store.objectives : OBJECTIVES
  const selObj = sel ?? objectives[0]

  const totalProgress = Math.round(objectives.reduce((a, o) => a + o.progress, 0) / objectives.length)
  const executing = objectives.filter(o => o.phase === 'EXECUTE' || o.phase === 'BUILD').length

  const toggleMilestone = useCallback((index) => {
    setMilestones(prev => {
      const updated = [...prev]
      updated[index].done = !updated[index].done
      return updated
    })
  }, [])

  return (
    <div className="af-grid">
      <div className="af-shimmer" />

      <div className="af-kpis">
        <KPITile icon="◈" iconTone="gold" label="Overall Progress" value={`${totalProgress}%`} sub="Across all objectives" />
        <KPITile icon="⊙" iconTone="bronze" label="Active Objectives" value={executing} sub={`of ${objectives.length} total`} />
        <KPITile icon="✓" iconTone="success" label="Milestones Done" value={milestones.filter(m => m.done).length} sub={`of ${milestones.length} total`} />
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
                <div className="af-detail__description">
                  <p>{selObj.description}</p>
                </div>
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
              {milestones.map((m, i) => (
                <button
                  key={i}
                  className={`af-milestone ${m.done ? 'is-done' : ''}`}
                  onClick={() => toggleMilestone(i)}
                  title="Click to toggle completion"
                >
                  <div className="af-milestone__dot" />
                  <span className="af-milestone__label">{m.label}</span>
                  <span className="af-milestone__ts">{m.ts}</span>
                </button>
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

import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, KPITile, StatusPill, HexButton } from '../nexus-ui'
import api from '../../api/client'
import './HermesPage.css'

const STRATEGIES = [
  { id:'fast',   label:'Fast / Risky',    risk:0.8, resources:'Low',  desc:'Prioritize speed, skip validation steps' },
  { id:'stable', label:'Slow / Stable',   risk:0.2, resources:'Med',  desc:'Full validation, rollback checkpoints' },
  { id:'exp',    label:'Experimental',    risk:0.6, resources:'High', desc:'LLM-generated strategy — uncertain upside' },
]
const TOOLS = ['Web Search', 'Code Runner', 'Database', 'Email', 'File System', 'External APIs']

export default function HermesPage() {
  const setHermesGoal = useAppStore(s => s.setHermesGoal)
  const hermesGoal = useAppStore(s => s.hermesGoal)
  const setActiveSection = useAppStore(s => s.setActiveSection)

  const [goal, setGoal] = useState(hermesGoal || '')
  const [decomposed, setDecomposed] = useState(false)
  const [activePath, setActivePath] = useState(null)
  const [budget, setBudget] = useState(500)
  const [timeDays, setTimeDays] = useState(14)
  const [enabledTools, setEnabledTools] = useState(new Set(['Web Search', 'Code Runner', 'Database']))
  const [sending, setSending] = useState(false)
  const [memoryLoading, setMemoryLoading] = useState(false)
  const [memoryResult, setMemoryResult] = useState(null)
  const [opsLoading, setOpsLoading] = useState(false)
  const [opsResult, setOpsResult] = useState(null)
  const [productLoading, setProductLoading] = useState(false)
  const [productResult, setProductResult] = useState(null)
  const [thoughtNode, setThoughtNode] = useState(null)

  const handleDecompose = () => {
    if (!goal.trim()) return
    setHermesGoal(goal.trim())
    setDecomposed(true)
  }

  const handleSendToAgents = async () => {
    setSending(true)
    try {
      await api.tasks.run(goal.trim())
    } catch (e) {
      console.error('Failed to send goal to agents:', e)
    }
    setSending(false)
  }

  const handleRequestMemory = async () => {
    setMemoryLoading(true)
    setMemoryResult(null)
    try {
      const d = await api.brain.insights()
      setMemoryResult(JSON.stringify(d).slice(0, 200))
    } catch (e) {
      setMemoryResult('Memory retrieval unavailable')
    }
    setMemoryLoading(false)
  }

  const handleMonitorOps = () => {
    setOpsLoading(true)
    setOpsResult(null)
    setTimeout(() => {
      setActiveSection('operations')
      setOpsLoading(false)
    }, 300)
  }

  const handleProductDashboard = async () => {
    setProductLoading(true)
    setProductResult(null)
    try {
      const d = await api.product.dashboard()
      setProductResult(`Revenue: ${d.revenue?.total ?? 'N/A'} | Agents: ${d.agents?.running ?? 'N/A'}`)
    } catch (e) {
      setProductResult('Dashboard data unavailable')
    }
    setProductLoading(false)
  }

  const toggleTool = (t) => setEnabledTools(prev => {
    const next = new Set(prev)
    if (next.has(t)) next.delete(t); else next.add(t)
    return next
  })

  const THOUGHT_NODES = [
    { id:'a1', x:60,  y:20,  label:'Assumption 1', desc:'Market growing 12% YoY' },
    { id:'a2', x:200, y:20,  label:'Assumption 2', desc:'Competitor X lags on mobile' },
    { id:'a3', x:340, y:20,  label:'Assumption 3', desc:'Retention is the primary lever' },
    { id:'l1', x:120, y:100, label:'Logic A',       desc:'Growth + weak competitor → enter now' },
    { id:'l2', x:280, y:100, label:'Logic B',       desc:'Focus resources on retention first' },
    { id:'con',x:200, y:175, label:'Conclusion',    desc:'Launch MVP in 30 days, retention-first GTM' },
  ]
  const EDGES = [['a1','l1'],['a2','l1'],['a3','l2'],['l1','con'],['l2','con']]
  const npos = Object.fromEntries(THOUGHT_NODES.map(n => [n.id, { cx: n.x+40, cy: n.y+15 }]))

  return (
    <div className="he-page">
      <div className="he-kpi-row">
        <KPITile label="Strategy Mode" value="HERMES" sub="Strategic Reasoning OS" icon="⚙" iconTone="gold" accent />
        <KPITile label="Active Path" value={activePath ?? '—'} sub="Selected strategy" icon="📍" iconTone="gold" />
        <KPITile label="Constraints" value={`€${budget} · ${timeDays}d`} sub="Budget · Timeline" icon="⏱" iconTone="gold" />
      </div>

      <div className="he-main-grid">
        <div className="he-left">
          <Panel title="Goal Decomposition Engine" tone="gold">
            <textarea
              value={goal}
              onChange={e => setGoal(e.target.value)}
              rows={2}
              placeholder="Enter a strategic goal to decompose..."
              className="he-textarea"
            />
            <HexButton onClick={handleDecompose} disabled={!goal.trim()} variant="primary" tone="gold">
              DECOMPOSE
            </HexButton>
            {decomposed && goal && (
              <div className="he-decomp-layers">
                {[
                  ['LAYER 1: Strategic Analysis',['Identify market positioning','Define competitive moat','Map key stakeholders']],
                  ['LAYER 2: Resource Planning',['Allocate budget by workstream','Identify capability gaps']],
                  ['LAYER 3: Execution Roadmap',['Set validation checkpoints','Assign agents to tasks']]
                ].map(([title, tasks]) => (
                  <div key={title} className="he-layer">
                    <div className="he-layer-title">{title}</div>
                    {tasks.map(t => <div key={t} className="he-layer-task">→ {t}</div>)}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Constraint Reasoning" tone="gold">
            <div className="he-constraint-group">
              <label className="he-constraint-label">BUDGET (€)</label>
              <input type="number" value={budget} onChange={e => setBudget(+e.target.value)} min={0} step={100}
                className="he-input" />
            </div>
            <div className="he-constraint-group">
              <label className="he-constraint-label">TIMELINE (days)</label>
              <input type="number" value={timeDays} onChange={e => setTimeDays(+e.target.value)} min={1}
                className="he-input" />
            </div>
            <div>
              <label className="he-constraint-label">TOOLS</label>
              <div className="he-tool-grid">
                {TOOLS.map(t => (
                  <label key={t} className="he-tool-checkbox">
                    <input type="checkbox" checked={enabledTools.has(t)} onChange={() => toggleTool(t)} />
                    <span>{t}</span>
                  </label>
                ))}
              </div>
            </div>
          </Panel>
        </div>

        <div className="he-right">
          <Panel title="Multi-Path Planning" tone="gold">
            {STRATEGIES.map(s => (
              <div key={s.id} className={`he-strategy ${activePath === s.id ? 'he-strategy--active' : ''}`} onClick={() => setActivePath(s.id)}>
                <div className="he-strategy-header">
                  <span className="he-strategy-label">{s.label}</span>
                  <StatusPill label={s.resources} tone="cool" size="sm" dot={false} />
                </div>
                <div className="he-strategy-desc">{s.desc}</div>
                <div className="he-strategy-risk">
                  <span className="he-risk-label">RISK</span>
                  <div className="he-risk-bar">
                    <div className="he-risk-fill" style={{ width: `${s.risk*100}%`, background: s.risk>0.6?'#ef4444':s.risk>0.3?'#f59e0b':'#22C55E' }} />
                  </div>
                </div>
                {activePath === s.id && <div className="he-strategy-check">✓ SELECTED</div>}
              </div>
            ))}
          </Panel>

          <Panel title="Execution Bridge" tone="gold">
            <div className="he-button-grid">
              <HexButton onClick={handleSendToAgents} variant="primary" tone="gold" size="sm" loading={sending}>
                SEND TO AGENTS
              </HexButton>
              <HexButton onClick={handleRequestMemory} variant="outline" tone="cool" size="sm" loading={memoryLoading}>
                REQUEST MEMORY
              </HexButton>
              <HexButton onClick={handleMonitorOps} variant="outline" tone="gold" size="sm" loading={opsLoading}>
                MONITOR OPS
              </HexButton>
              <HexButton onClick={handleProductDashboard} variant="outline" tone="purple" size="sm" loading={productLoading}>
                REPORT STATUS
              </HexButton>
            </div>
            {(memoryResult || opsResult || productResult) && (
              <div className="he-result-box">
                {memoryResult || opsResult || productResult}
              </div>
            )}
          </Panel>

          <Panel title="Reasoning Thought Map" tone="gold" className="he-thoughtmap-panel">
            <div className="he-thoughtmap">
              <svg width="430" height="215" viewBox="0 0 430 215" className="he-thoughtmap-svg">
                {EDGES.map(([f,t], i) => (
                  <line key={i} x1={npos[f].cx} y1={npos[f].cy} x2={npos[t].cx} y2={npos[t].cy} stroke="rgba(229,199,107,0.2)" strokeWidth="1.5" strokeDasharray="4 3"/>
                ))}
                {THOUGHT_NODES.map(n => (
                  <g key={n.id} onClick={() => setThoughtNode(thoughtNode?.id===n.id ? null : n)} className="he-thoughtnode" style={{ cursor:'pointer' }}>
                    <circle cx={npos[n.id].cx} cy={npos[n.id].cy} r={22} fill={thoughtNode?.id===n.id?'rgba(229,199,107,0.12)':'rgba(255,255,255,0.03)'} stroke={thoughtNode?.id===n.id?'rgba(229,199,107,0.4)':'rgba(229,199,107,0.15)'} strokeWidth="1"/>
                    <text x={npos[n.id].cx} y={npos[n.id].cy+4} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.6)" fontFamily="monospace">{n.label}</text>
                  </g>
                ))}
              </svg>
              {thoughtNode && (
                <div className="he-thoughtnode-detail">
                  <div className="he-thoughtnode-title">{thoughtNode.label}</div>
                  <div className="he-thoughtnode-desc">{thoughtNode.desc}</div>
                </div>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

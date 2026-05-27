import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, Badge, StatCard } from '../ui/primitives'
import api from '../../api/client'

const STRATEGIES = [
  { id:'fast',   label:'Fast / Risky',    risk:0.8, resources:'Low',  desc:'Prioritize speed, skip validation steps' },
  { id:'stable', label:'Slow / Stable',   risk:0.2, resources:'Med',  desc:'Full validation, rollback checkpoints' },
  { id:'exp',    label:'Experimental',    risk:0.6, resources:'High', desc:'LLM-generated strategy — uncertain upside' },
]
const TOOLS = ['Web Search', 'Code Runner', 'Database', 'Email', 'File System', 'External APIs']

function SilverPanel({ title, children, style, badge }) {
  return (
    <div style={{ background:'linear-gradient(180deg,rgba(216,216,224,0.04) 0%,transparent 40%),linear-gradient(180deg,#101218,#080A10)', border:'1px solid rgba(216,216,224,0.14)', borderRadius:10, display:'flex', flexDirection:'column', overflow:'hidden', ...style }}>
      {(title || badge) && (
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'10px 14px 8px', borderBottom:'1px solid rgba(216,216,224,0.08)', flexShrink:0 }}>
          {title && <span style={{ fontFamily:'monospace', fontSize:10, letterSpacing:'0.1em', textTransform:'uppercase', color:'var(--silver,#D8D8E0)' }}>{title}</span>}
          {badge}
        </div>
      )}
      <div style={{ padding:'12px 14px', flex:1, overflowY:'auto' }}>{children}</div>
    </div>
  )
}

function MiniBar({ value, color = 'var(--silver,#D8D8E0)' }) {
  return (
    <div style={{ height:3, background:'rgba(255,255,255,0.06)', borderRadius:2 }}>
      <div style={{ width:`${value*100}%`, height:'100%', background:color, borderRadius:2 }}/>
    </div>
  )
}

export default function HermesPage() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const setHermesGoal = useAppStore(s => s.setHermesGoal)
  const hermesGoal = useAppStore(s => s.hermesGoal)

  const [goal, setGoal] = useState(hermesGoal || '')
  const [decomposed, setDecomposed] = useState(false)
  const [activePath, setActivePath] = useState(null)
  const [budget, setBudget] = useState(500)
  const [timeDays, setTimeDays] = useState(14)
  const [enabledTools, setEnabledTools] = useState(new Set(['Web Search', 'Code Runner', 'Database']))
  const [sending, setSending] = useState(false)
  const [memoryResult, setMemoryResult] = useState(null)
  const [productResult, setProductResult] = useState(null)
  const [thoughtNode, setThoughtNode] = useState(null)

  const handleDecompose = () => {
    if (!goal.trim()) return
    setHermesGoal(goal.trim())
    setDecomposed(true)
  }

  const handleSendToAgents = async () => {
    setSending(true)
    try { await api.tasks.run(goal.trim()) } catch { /* ignore */ }
    setSending(false)
  }

  const handleRequestMemory = async () => {
    try { const d = await api.brain.insights(); setMemoryResult(JSON.stringify(d).slice(0, 200)) }
    catch { setMemoryResult('Memory retrieval unavailable') }
  }

  const handleProductDashboard = async () => {
    try { const d = await api.product.dashboard(); setProductResult(`Revenue: ${d.revenue?.total ?? 'N/A'} | Agents: ${d.agents?.running ?? 'N/A'}`) }
    catch { setProductResult('Dashboard data unavailable') }
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
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, flexShrink:0 }}>
        <StatCard label="Strategy Mode"  value="HERMES"             color="var(--silver,#D8D8E0)" sub="Strategic Reasoning OS"/>
        <StatCard label="Active Path"    value={activePath ?? '—'}  color="var(--silver-dim,#8B8B9E)" sub="Selected strategy"/>
        <StatCard label="Constraints"    value={`€${budget} · ${timeDays}d`} color="var(--silver,#D8D8E0)" sub="Budget · Timeline"/>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, flex:1, minHeight:0 }}>
        {/* Left */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <SilverPanel title="Goal Decomposition Engine">
            <textarea value={goal} onChange={e => setGoal(e.target.value)} rows={2} placeholder="Enter a strategic goal to decompose..."
              style={{ width:'100%', resize:'none', padding:'7px 9px', borderRadius:5, background:'rgba(255,255,255,0.04)', border:'1px solid rgba(216,216,224,0.15)', color:'var(--text-primary,#F0E9D2)', fontFamily:'monospace', fontSize:12, boxSizing:'border-box', marginBottom:8 }}/>
            <button onClick={handleDecompose} style={{ width:'100%', padding:'6px', borderRadius:5, background:'rgba(216,216,224,0.1)', border:'1px solid rgba(216,216,224,0.3)', color:'var(--silver,#D8D8E0)', cursor:'pointer', fontFamily:'monospace', fontSize:10, fontWeight:600, letterSpacing:'0.06em', marginBottom:10 }}>DECOMPOSE</button>
            {decomposed && goal && (
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {[['LAYER 1: Strategic Analysis',['Identify market positioning','Define competitive moat','Map key stakeholders']],
                  ['LAYER 2: Resource Planning',['Allocate budget by workstream','Identify capability gaps']],
                  ['LAYER 3: Execution Roadmap',['Set validation checkpoints','Assign agents to tasks']]
                ].map(([title, tasks]) => (
                  <div key={title} style={{ borderLeft:'2px solid rgba(216,216,224,0.2)', paddingLeft:10 }}>
                    <div style={{ fontSize:8, fontFamily:'monospace', color:'var(--silver-dim,#8B8B9E)', marginBottom:3, letterSpacing:'0.06em' }}>{title}</div>
                    {tasks.map(t => <div key={t} style={{ fontSize:11, color:'rgba(255,255,255,0.45)', marginBottom:1 }}>→ {t}</div>)}
                  </div>
                ))}
              </div>
            )}
          </SilverPanel>

          <SilverPanel title="Constraint Reasoning" style={{ flex:1 }}>
            <div style={{ marginBottom:10 }}>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:3 }}>BUDGET (€)</div>
              <input type="number" value={budget} onChange={e => setBudget(+e.target.value)} min={0} step={100}
                style={{ width:'100%', padding:'5px 8px', borderRadius:5, background:'rgba(255,255,255,0.04)', border:'1px solid rgba(216,216,224,0.15)', color:'var(--text-primary,#F0E9D2)', fontFamily:'monospace', fontSize:12, boxSizing:'border-box' }}/>
            </div>
            <div style={{ marginBottom:10 }}>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:3 }}>TIMELINE (days)</div>
              <input type="number" value={timeDays} onChange={e => setTimeDays(+e.target.value)} min={1}
                style={{ width:'100%', padding:'5px 8px', borderRadius:5, background:'rgba(255,255,255,0.04)', border:'1px solid rgba(216,216,224,0.15)', color:'var(--text-primary,#F0E9D2)', fontFamily:'monospace', fontSize:12, boxSizing:'border-box' }}/>
            </div>
            <div>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:5 }}>TOOLS</div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:4 }}>
                {TOOLS.map(t => (
                  <label key={t} style={{ display:'flex', alignItems:'center', gap:5, cursor:'pointer' }}>
                    <input type="checkbox" checked={enabledTools.has(t)} onChange={() => toggleTool(t)} style={{ accentColor:'var(--silver,#D8D8E0)' }}/>
                    <span style={{ fontSize:10, fontFamily:'monospace', color: enabledTools.has(t)?'var(--silver,#D8D8E0)':'rgba(255,255,255,0.3)' }}>{t}</span>
                  </label>
                ))}
              </div>
            </div>
          </SilverPanel>
        </div>

        {/* Right */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <SilverPanel title="Multi-Path Planning">
            {STRATEGIES.map(s => (
              <div key={s.id} onClick={() => setActivePath(s.id)} style={{ padding:'10px 12px', borderRadius:7, marginBottom:6, border:`1px solid ${activePath===s.id?'rgba(216,216,224,0.4)':'rgba(216,216,224,0.1)'}`, background:activePath===s.id?'rgba(216,216,224,0.06)':'rgba(255,255,255,0.02)', cursor:'pointer' }}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                  <span style={{ fontSize:12, color:'var(--silver,#D8D8E0)', fontWeight:600 }}>{s.label}</span>
                  <Badge label={s.resources} variant="default"/>
                </div>
                <div style={{ fontSize:10, color:'rgba(255,255,255,0.4)', marginBottom:6 }}>{s.desc}</div>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ fontSize:8, fontFamily:'monospace', color:'rgba(255,255,255,0.3)', width:28 }}>RISK</span>
                  <div style={{ flex:1 }}><MiniBar value={s.risk} color={s.risk>0.6?'#ef4444':s.risk>0.3?'#f59e0b':'#22C55E'}/></div>
                </div>
                {activePath===s.id && (
                  <div style={{ marginTop:6, fontSize:9, fontFamily:'monospace', color:'var(--silver,#D8D8E0)' }}>✓ SELECTED</div>
                )}
              </div>
            ))}
          </SilverPanel>

          <SilverPanel title="Execution Bridge">
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6 }}>
              {[
                { label:'SEND TO AGENTS', action:handleSendToAgents, loading:sending, color:'rgba(216,216,224,0.3)', bg:'rgba(216,216,224,0.08)' },
                { label:'REQUEST MEMORY', action:handleRequestMemory, color:'rgba(32,214,199,0.3)', bg:'rgba(32,214,199,0.06)' },
                { label:'MONITOR OPS',    action:() => setActiveSection('operations'), color:'rgba(229,199,107,0.3)', bg:'rgba(229,199,107,0.06)' },
                { label:'REPORT STATUS',  action:handleProductDashboard, color:'rgba(168,85,247,0.3)', bg:'rgba(168,85,247,0.06)' },
              ].map(b => (
                <button key={b.label} onClick={b.action} disabled={b.loading} style={{ padding:'8px', borderRadius:6, border:`1px solid ${b.color}`, background:b.bg, color:'rgba(255,255,255,0.7)', cursor:'pointer', fontFamily:'monospace', fontSize:9, fontWeight:600, letterSpacing:'0.05em' }}>
                  {b.loading ? '...' : b.label}
                </button>
              ))}
            </div>
            {(memoryResult || productResult) && (
              <div style={{ marginTop:8, padding:'7px 9px', borderRadius:5, background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.06)', fontSize:10, fontFamily:'monospace', color:'rgba(255,255,255,0.5)' }}>
                {memoryResult || productResult}
              </div>
            )}
          </SilverPanel>

          <SilverPanel title="Reasoning Thought Map" style={{ flex:1 }}>
            <div style={{ display:'flex', gap:10 }}>
              <svg width="430" height="215" viewBox="0 0 430 215" style={{ flexShrink:0 }}>
                {EDGES.map(([f,t], i) => (
                  <line key={i} x1={npos[f].cx} y1={npos[f].cy} x2={npos[t].cx} y2={npos[t].cy} stroke="rgba(216,216,224,0.2)" strokeWidth="1.5" strokeDasharray="4 3"/>
                ))}
                {THOUGHT_NODES.map(n => (
                  <g key={n.id} onClick={() => setThoughtNode(thoughtNode?.id===n.id ? null : n)} style={{ cursor:'pointer' }}>
                    <circle cx={npos[n.id].cx} cy={npos[n.id].cy} r={22} fill={thoughtNode?.id===n.id?'rgba(216,216,224,0.12)':'rgba(255,255,255,0.03)'} stroke={thoughtNode?.id===n.id?'rgba(216,216,224,0.4)':'rgba(216,216,224,0.15)'} strokeWidth="1"/>
                    <text x={npos[n.id].cx} y={npos[n.id].cy+4} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.6)" fontFamily="monospace">{n.label}</text>
                  </g>
                ))}
              </svg>
              {thoughtNode && (
                <div style={{ flex:1, padding:'8px', background:'rgba(216,216,224,0.04)', borderRadius:6, border:'1px solid rgba(216,216,224,0.12)', minWidth:0 }}>
                  <div style={{ fontSize:9, fontFamily:'monospace', color:'var(--silver-dim,#8B8B9E)', marginBottom:4 }}>{thoughtNode.label}</div>
                  <div style={{ fontSize:11, color:'rgba(255,255,255,0.6)', lineHeight:1.5 }}>{thoughtNode.desc}</div>
                </div>
              )}
            </div>
          </SilverPanel>
        </div>
      </div>
    </div>
  )
}

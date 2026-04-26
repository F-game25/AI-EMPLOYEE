import { useState, useRef, useEffect } from 'react'
import { useAppStore } from '../../store/appStore'

/* ── Luxury Bronze design tokens ────────────────────────────────────── */
const BR  = '#CD7F32'   // bronze
const BRB = '#E8A84A'   // bronze-bright
const BRD = '#8B5120'   // bronze-deep
const BRL = '#F0C060'   // bronze-light shimmer

function BZPanel({ title, badge, children, style = {}, bodyStyle = {} }) {
  return (
    <div style={{ background:'linear-gradient(180deg,rgba(139,81,32,0.12) 0%,rgba(10,7,4,0.97) 100%)', border:`1px solid rgba(205,127,50,0.28)`, borderRadius:10, overflow:'hidden', display:'flex', flexDirection:'column', ...style }}>
      <div style={{ height:1, background:`linear-gradient(90deg,transparent,${BRB},${BRL},${BRB},transparent)`, opacity:0.7 }}/>
      {title && (
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 14px 0', flexShrink:0 }}>
          <span style={{ fontSize:10, fontFamily:'monospace', letterSpacing:'0.12em', textTransform:'uppercase', color:BRB }}>{title}</span>
          {badge}
        </div>
      )}
      <div style={{ padding:'10px 14px', flex:1, minHeight:0, ...bodyStyle }}>{children}</div>
    </div>
  )
}

function BZBadge({ label, variant }) {
  const c = variant==='execute'?BRL:variant==='build'?BRB:variant==='review'?'#22C55E':variant==='error'?'#EF4444':BR
  return <span style={{ fontFamily:'monospace', fontSize:8, letterSpacing:'0.1em', color:c, padding:'2px 7px', border:`1px solid ${c}55`, borderRadius:4, background:`${c}0A` }}>{label}</span>
}

function BZBar({ value = 0, color = BR }) {
  return (
    <div style={{ height:4, background:'rgba(139,81,32,0.15)', borderRadius:2, overflow:'hidden' }}>
      <div style={{ width:`${Math.min(100,Math.max(0,value))}%`, height:'100%', background:`linear-gradient(90deg,${BRD},${color},${BRL})`, boxShadow:`0 0 8px ${color}66`, borderRadius:2, transition:'width .5s' }}/>
    </div>
  )
}

function BZStat({ label, value, sub, color = BRB }) {
  return (
    <div style={{ background:'linear-gradient(180deg,rgba(139,81,32,0.14),rgba(10,7,4,0.97))', border:`1px solid rgba(205,127,50,0.25)`, borderRadius:9, padding:'12px 14px', position:'relative', overflow:'hidden' }}>
      <div style={{ position:'absolute', top:0, left:0, right:0, height:1, background:`linear-gradient(90deg,transparent,${BR},${BRL},${BR},transparent)` }}/>
      <div style={{ position:'absolute', top:0, right:0, width:40, height:40, background:`radial-gradient(circle at top right,${BR}18,transparent 70%)` }}/>
      <div style={{ fontFamily:'monospace', fontSize:22, fontWeight:700, color, marginBottom:2, textShadow:`0 0 18px ${color}44` }}>{value}</div>
      <div style={{ fontSize:10, color:'rgba(205,127,50,0.6)', letterSpacing:'0.06em', textTransform:'uppercase' }}>{label}</div>
      {sub && <div style={{ fontSize:9, color:'rgba(205,127,50,0.4)', marginTop:3, fontFamily:'monospace' }}>{sub}</div>}
    </div>
  )
}

function BZRow({ label, value, color }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:`1px solid rgba(139,81,32,0.12)` }}>
      <span style={{ fontSize:11, color:'rgba(205,127,50,0.55)' }}>{label}</span>
      <span style={{ fontFamily:'monospace', fontSize:11, color:color||BRB, fontWeight:500 }}>{value}</span>
    </div>
  )
}

const OBJECTIVES = [
  { id:'obj-1', title:'Monetization Pipeline v2',       phase:'EXECUTE', progress:72, priority:'HIGH', due:'Apr 30', tasks:8, done:6, revenue:'$12K/mo target', owner:'Orchestrator Prime' },
  { id:'obj-2', title:'Competitor Intelligence System', phase:'BUILD',   progress:45, priority:'HIGH', due:'May 5',  tasks:5, done:2, revenue:'Strategic',      owner:'Data Harvester'    },
  { id:'obj-3', title:'Automated Outreach Engine',      phase:'PLAN',    progress:20, priority:'MED',  due:'May 15', tasks:7, done:1, revenue:'$8K/mo target',  owner:'Strategy Engine'   },
  { id:'obj-4', title:'AI Cost Optimization Suite',     phase:'REVIEW',  progress:90, priority:'MED',  due:'Apr 28', tasks:4, done:4, revenue:'-$2K/mo cost',   owner:'Risk Auditor'      },
]
const MILESTONES = [
  { label:'Stripe webhook live',        done:true,  ts:'Apr 22' },
  { label:'Revenue model v1 deployed',  done:true,  ts:'Apr 23' },
  { label:'First $500 automated',       done:true,  ts:'Apr 24' },
  { label:'Agent fleet at 15 bots',     done:false, ts:'Apr 29' },
  { label:'Reach $5K MRR milestone',    done:false, ts:'May 10' },
  { label:'Launch outreach engine',     done:false, ts:'May 15' },
]
const INSIGHTS = [
  { text:'Revenue pathway #1 has 3.2× ROI vs pathway #2 — reallocate agent hours', c:BRL  },
  { text:'Competitor pricing dropped 12% — opportunity to capture SMB segment',     c:BRB  },
  { text:'API cost optimization saves est. $340/mo — approve and deploy',           c:'#22C55E' },
]
const PHASE_C = { EXECUTE:BRL, BUILD:BRB, PLAN:'rgba(205,127,50,0.45)', REVIEW:'#22C55E' }

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
    <BZPanel title="Coding AI Assistant" badge={<BZBadge label={provider.toUpperCase()} variant="build"/>} style={{ flex: 1, display: 'flex', flexDirection: 'column' }} bodyStyle={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, padding: '10px 14px' }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={provider} onChange={e => setProvider(e.target.value)} style={{ flex: 1, padding: '4px 8px', borderRadius: 4, border: `1px solid ${BR}44`, background: 'rgba(139,81,32,0.1)', color: BRB, fontSize: 10, fontFamily: 'monospace' }}>
          <option value="anthropic">Claude (Anthropic)</option>
          <option value="openrouter">OpenRouter</option>
          <option value="ollama">Ollama (Local)</option>
        </select>
        <select value={model} onChange={e => setModel(e.target.value)} style={{ flex: 1, padding: '4px 8px', borderRadius: 4, border: `1px solid ${BR}44`, background: 'rgba(139,81,32,0.1)', color: BRB, fontSize: 10, fontFamily: 'monospace' }}>
          {models.map(m => <option key={m} value={m}>{m.split('/').pop()}</option>)}
        </select>
        {provider === 'openrouter' && <input type="password" placeholder="API Key" value={apiKey} onChange={e => setApiKey(e.target.value)} style={{ flex: 1, padding: '4px 8px', borderRadius: 4, border: `1px solid ${BR}44`, background: 'rgba(139,81,32,0.1)', color: '#F5E6C8', fontSize: 10 }} />}
      </div>

      <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 6, minHeight: 100, paddingBottom: 8 }}>
        {messages.map((msg, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{ maxWidth: '85%', padding: '8px 10px', borderRadius: 6, background: msg.role === 'user' ? `rgba(205,127,50,0.25)` : `rgba(139,81,32,0.15)`, border: `1px solid ${msg.role === 'user' ? BRL : BR}44`, fontSize: 10, color: '#F5E6C8', lineHeight: 1.4, wordBreak: 'break-word' }}>
              {msg.role === 'assistant' && msg.content.includes('```') ? (
                <div dangerouslySetInnerHTML={{ __html: msg.content.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,0.4);padding:8px;borderRadius:4px;overflow:auto;fontSize:9px"><code>$2</code></pre>').replace(/\n/g, '<br/>') }} />
              ) : (
                <span>{msg.content}</span>
              )}
            </div>
          </div>
        ))}
        {loading && <div style={{ fontSize: 10, color: BRL, fontStyle: 'italic' }}>Thinking...</div>}
        <div ref={messagesEndRef} />
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        <input type="text" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()} placeholder="Ask a coding question..." disabled={loading} style={{ flex: 1, padding: '6px 8px', borderRadius: 4, border: `1px solid ${BR}44`, background: 'rgba(139,81,32,0.1)', color: '#F5E6C8', fontSize: 10, fontFamily: 'monospace' }} />
        <button onClick={handleSend} disabled={loading || !input.trim()} style={{ padding: '6px 12px', borderRadius: 4, border: `1px solid ${BR}66`, background: `linear-gradient(135deg,${BRD}88,${BR}22)`, color: BRL, cursor: 'pointer', fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.08em', fontWeight: 700, opacity: loading || !input.trim() ? 0.5 : 1 }}>SEND</button>
      </div>
    </BZPanel>
  )
}

export default function AscendForgePage() {
  const store = useAppStore(s => s.objectivePanels?.ascend_forge)
  const [sel, setSel] = useState(null)
  const objectives = store?.objectives?.length ? store.objectives : OBJECTIVES
  const selObj = sel ?? objectives[0]

  const totalProgress = Math.round(objectives.reduce((a, o) => a + o.progress, 0) / objectives.length)
  const executing     = objectives.filter(o => o.phase === 'EXECUTE' || o.phase === 'BUILD').length

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>

      {/* Luxury shimmer bar */}
      <div style={{ height:2, background:`linear-gradient(90deg,transparent 0%,${BRD} 15%,${BR} 35%,${BRL} 50%,${BR} 65%,${BRD} 85%,transparent 100%)`, borderRadius:1, flexShrink:0, boxShadow:`0 0 14px ${BR}66` }}/>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, flexShrink:0 }}>
        <BZStat label="Overall Progress"  value={`${totalProgress}%`}                          color={BRL}        sub="Across all objectives"/>
        <BZStat label="Active Objectives" value={executing}                                     color={BRB}        sub={`${objectives.length} total`}/>
        <BZStat label="Milestones Done"   value={MILESTONES.filter(m=>m.done).length}          color="#22C55E"    sub={`of ${MILESTONES.length} total`}/>
        <BZStat label="Est. Revenue"      value="$20K/mo"                                       color={BRL}        sub="When objectives complete"/>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'2fr 3fr', gap:10, flex:1, minHeight:0 }}>
        {/* Left column: Strategic Objectives + Insights */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <BZPanel title="Strategic Objectives" badge={<BZBadge label="FORGE ACTIVE" variant="build"/>} bodyStyle={{ padding:8 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
              {objectives.map(o => (
                <div key={o.id} onClick={() => setSel(o)} style={{ padding:'10px 12px', borderRadius:8, border:`1px solid ${selObj?.id===o.id?`rgba(205,127,50,0.55)`:`rgba(139,81,32,0.2)`}`, background:selObj?.id===o.id?`rgba(139,81,32,0.14)`:`rgba(139,81,32,0.05)`, cursor:'pointer', position:'relative', overflow:'hidden', transition:'all .15s' }}>
                  {selObj?.id===o.id && <div style={{ position:'absolute', top:0, left:0, right:0, height:1, background:`linear-gradient(90deg,transparent,${BR},transparent)` }}/>}
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:7 }}>
                    <span style={{ fontFamily:'monospace', fontSize:9, color:PHASE_C[o.phase]||BRB, padding:'1px 6px', border:`1px solid ${PHASE_C[o.phase]||BRB}44`, borderRadius:3, background:`${PHASE_C[o.phase]||BRB}0A` }}>{o.phase}</span>
                    <span style={{ fontSize:12, color:'#F5E6C8', flex:1, fontWeight:500 }}>{o.title}</span>
                    <span style={{ fontFamily:'monospace', fontSize:9, color:o.priority==='HIGH'?'#EF4444':'#F59E0B', letterSpacing:'0.06em' }}>{o.priority}</span>
                  </div>
                  <BZBar value={o.progress} color={PHASE_C[o.phase]||BR}/>
                  <div style={{ display:'flex', justifyContent:'space-between', marginTop:5, fontSize:10, fontFamily:'monospace', color:'rgba(205,127,50,0.45)' }}>
                    <span>{o.owner}</span>
                    <span>{o.done}/{o.tasks} tasks · due {o.due}</span>
                    <span style={{ color:PHASE_C[o.phase]||BRB }}>{o.progress}%</span>
                  </div>
                </div>
              ))}
            </div>
          </BZPanel>

          <BZPanel title="Strategic Insights" style={{ flex:1 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:7 }}>
              {INSIGHTS.map((ins, i) => (
                <div key={i} style={{ padding:'9px 11px', borderRadius:7, border:`1px solid ${ins.c}28`, background:`linear-gradient(90deg,${ins.c}09,transparent)`, position:'relative', overflow:'hidden' }}>
                  <div style={{ position:'absolute', top:0, bottom:0, left:0, width:2, background:ins.c, boxShadow:`0 0 8px ${ins.c}` }}/>
                  <span style={{ fontSize:11.5, color:'#F5E6C8', lineHeight:1.5 }}>{ins.text}</span>
                </div>
              ))}
            </div>
          </BZPanel>

          {selObj && (
            <BZPanel title={selObj.title} badge={<BZBadge label={selObj.phase} variant={selObj.phase.toLowerCase()}/>} style={{ flexShrink:0 }}>
              <BZRow label="Priority"  value={selObj.priority} color={selObj.priority==='HIGH'?'#EF4444':'#F59E0B'}/>
              <BZRow label="Progress"  value={`${selObj.progress}%`} color={PHASE_C[selObj.phase]}/>
              <BZRow label="Tasks"     value={`${selObj.done}/${selObj.tasks} done`}/>
              <BZRow label="Due"       value={selObj.due}/>
              <BZRow label="Owner"     value={selObj.owner} color={BRB}/>
              <BZRow label="Revenue"   value={selObj.revenue} color="#22C55E"/>
              <div style={{ marginTop:10 }}><BZBar value={selObj.progress} color={PHASE_C[selObj.phase]||BR}/></div>
              <div style={{ display:'flex', gap:5, marginTop:10 }}>
                <button style={{ flex:1, padding:'7px', borderRadius:6, border:`1px solid ${BR}66`, background:`linear-gradient(135deg,${BRD}88,${BR}22)`, color:BRL, cursor:'pointer', fontSize:9, fontFamily:'monospace', letterSpacing:'0.08em', fontWeight:700 }}>EXECUTE</button>
                <button style={{ flex:1, padding:'7px', borderRadius:6, border:`1px solid rgba(139,81,32,0.3)`, background:`rgba(139,81,32,0.08)`, color:BR, cursor:'pointer', fontSize:9, fontFamily:'monospace', letterSpacing:'0.08em' }}>PAUSE</button>
              </div>
            </BZPanel>
          )}
        </div>

        {/* Right column: Coding AI + Milestones + Heat */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <CodingAISection />

          <BZPanel title="Forge Milestones" style={{ flexShrink:0 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:6, maxHeight:180, overflow:'auto' }}>
              {MILESTONES.map((m, i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 0', borderBottom:`1px solid rgba(139,81,32,0.1)` }}>
                  <div style={{ width:14, height:14, borderRadius:'50%', border:`2px solid ${m.done?BRB:'rgba(139,81,32,0.3)'}`, background:m.done?`rgba(205,127,50,0.15)`:'transparent', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0, boxShadow:m.done?`0 0 8px ${BR}66`:'none' }}>
                    {m.done && <div style={{ width:6, height:6, borderRadius:'50%', background:`radial-gradient(circle,${BRL},${BR})` }}/>}
                  </div>
                  <span style={{ flex:1, fontSize:11, color:m.done?'#F5E6C8':'rgba(205,127,50,0.35)' }}>{m.label}</span>
                  <span style={{ fontFamily:'monospace', fontSize:9, color:'rgba(205,127,50,0.3)' }}>{m.ts}</span>
                </div>
              ))}
            </div>
          </BZPanel>

          {/* Forge heat visualiser */}
          <BZPanel title="Forge Heat" style={{ flexShrink:0 }}>
            <svg viewBox="0 0 240 36" style={{ width:'100%', height:36 }}>
              <defs>
                <linearGradient id="bzheat" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={BRB} stopOpacity=".5"/>
                  <stop offset="100%" stopColor={BR}  stopOpacity="0"/>
                </linearGradient>
              </defs>
              <polyline points="0,30 20,26 40,18 60,22 80,10 100,16 120,6 140,12 160,8 180,14 200,10 220,16 240,12" fill="none" stroke={BRL} strokeWidth="1.5"/>
              <polygon points="0,30 20,26 40,18 60,22 80,10 100,16 120,6 140,12 160,8 180,14 200,10 220,16 240,12 240,36 0,36" fill="url(#bzheat)"/>
            </svg>
            <div style={{ fontFamily:'monospace', fontSize:9, color:'rgba(205,127,50,0.5)', marginTop:4, letterSpacing:'0.08em' }}>EXECUTION INTENSITY — LIVE</div>
          </BZPanel>
        </div>
      </div>
    </div>
  )
}

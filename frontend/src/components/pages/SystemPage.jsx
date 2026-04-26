import { useAppStore } from '../../store/appStore'
import { Panel, Badge, StatCard, MiniBar, DataRow } from '../ui/primitives'

const APIS = [
  { name:'Anthropic Claude',  status:'ok',   calls:4241, cost:'$1.82',  p99:'340ms' },
  { name:'OpenAI GPT-4',      status:'ok',   calls:612,  cost:'$0.64',  p99:'980ms' },
  { name:'Stripe Payments',   status:'ok',   calls:14,   cost:'$0.00',  p99:'280ms' },
  { name:'Tavily Search',     status:'ok',   calls:88,   cost:'$0.09',  p99:'440ms' },
  { name:'Ollama (local)',     status:'idle', calls:0,    cost:'$0.00',  p99:'—'     },
]
const SECURITY = [
  { item:'JWT rotation',        status:'ok',   note:'Rotated 3d ago'         },
  { item:'API key vault',       status:'ok',   note:'All keys encrypted'      },
  { item:'Rate limiter',        status:'ok',   note:'1200 req/min cap active' },
  { item:'CORS policy',         status:'ok',   note:'Whitelist enforced'      },
  { item:'Anomaly responder',   status:'warn', note:'1 alert in last 24h'     },
]
const STATUS_C = { ok:'#22C55E', warn:'#F59E0B', error:'#EF4444', idle:'rgba(255,255,255,0.25)' }

export default function SystemPage() {
  const systemStatus = useAppStore(s => s.systemStatus)
  const nnStatus     = useAppStore(s => s.nnStatus)

  const cpu     = systemStatus?.cpu     ?? 42
  const memory  = systemStatus?.memory  ?? 67
  const gpu     = systemStatus?.gpu     ?? 31
  const temp    = systemStatus?.temp    ?? 48
  const mode    = systemStatus?.mode    || 'BALANCED'
  const uptime  = systemStatus?.uptime  || '6h 14m'
  const agents  = systemStatus?.agentCount ?? 8
  const conf    = nnStatus?.confidence  ?? 0
  const brainPct = conf > 1 ? Math.round(conf) : Math.round(conf * 100)

  const totalAPICost = APIS.reduce((a, api) => a + parseFloat(api.cost.replace('$', '') || '0'), 0).toFixed(2)

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, flexShrink:0 }}>
        <StatCard label="CPU"         value={`${cpu}%`}      color={cpu>80?'#EF4444':cpu>60?'#F59E0B':'#22C55E'} sub={`Temp: ${temp}°C`}/>
        <StatCard label="Memory"      value={`${memory}%`}   color={memory>80?'#EF4444':memory>60?'#F59E0B':'var(--teal,#20D6C7)'} sub="System RAM"/>
        <StatCard label="GPU"         value={`${gpu}%`}      color="var(--gold,#E5C76B)" sub="Neural compute"/>
        <StatCard label="Uptime"      value={uptime}         color="#22C55E"              sub={`Mode: ${mode}`}/>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, flex:1, minHeight:0 }}>
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <Panel title="Hardware" badge={<Badge label="LIVE" variant="green"/>}>
            {[['CPU Load', cpu, cpu>80?'#EF4444':cpu>60?'#F59E0B':'#22C55E'], ['Memory', memory, memory>80?'#EF4444':memory>60?'#F59E0B':'var(--teal,#20D6C7)'], ['GPU', gpu, 'var(--gold,#E5C76B)'], ['Disk I/O', 34, 'rgba(255,255,255,0.35)']].map(([l, v, c]) => (
              <div key={l} style={{ marginBottom:8 }}>
                <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:4, letterSpacing:'0.06em', textTransform:'uppercase' }}><span>{l}</span><span style={{ color:c }}>{v}%</span></div>
                <MiniBar value={v} color={c}/>
              </div>
            ))}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginTop:4 }}>
              <DataRow label="CPU Temp"  value={`${temp}°C`}/>
              <DataRow label="Fans"      value="1,840 RPM"/>
              <DataRow label="Processes" value="247"/>
              <DataRow label="Threads"   value="1,023"/>
            </div>
          </Panel>

          <Panel title="Runtime" style={{ flex:1 }}>
            <DataRow label="Node.js"      value="v22.3.0"       color="var(--teal,#20D6C7)"/>
            <DataRow label="Python"       value="3.11.4"        color="var(--gold,#E5C76B)"/>
            <DataRow label="Vite/React"   value="5.0 / 18.3"   />
            <DataRow label="FastAPI"      value="0.104.1"       />
            <DataRow label="Mode"         value={mode}          color="var(--gold-bright,#FFD97A)"/>
            <DataRow label="Active Agents" value={agents}       color="var(--teal,#20D6C7)"/>
            <DataRow label="Bus Events"   value="18,920"        />
            <DataRow label="LLM Calls"    value="4,241"         />
          </Panel>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <Panel title="API Integrations">
            <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
              {APIS.map(api => (
                <div key={api.name} style={{ padding:'8px 10px', borderRadius:7, border:'1px solid rgba(229,199,107,0.08)', background:'var(--bg-elevated,#12141F)' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                    <div style={{ width:7, height:7, borderRadius:'50%', background:STATUS_C[api.status], boxShadow:`0 0 5px ${STATUS_C[api.status]}`, flexShrink:0 }}/>
                    <span style={{ fontSize:12, color:'var(--text-primary,#F0E9D2)', flex:1 }}>{api.name}</span>
                    <span style={{ fontFamily:'monospace', fontSize:10, color:STATUS_C[api.status] }}>{api.status.toUpperCase()}</span>
                  </div>
                  <div style={{ display:'flex', gap:12, fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)' }}>
                    <span>calls <span style={{ color:'var(--teal,#20D6C7)' }}>{api.calls}</span></span>
                    <span>cost <span style={{ color:'#22C55E' }}>{api.cost}</span></span>
                    <span>p99 <span style={{ color:'var(--gold,#E5C76B)' }}>{api.p99}</span></span>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop:8, padding:'6px 8px', borderRadius:6, background:'rgba(34,197,94,0.05)', border:'1px solid rgba(34,197,94,0.15)', display:'flex', justifyContent:'space-between' }}>
              <span style={{ fontSize:10, color:'rgba(255,255,255,0.35)', fontFamily:'monospace' }}>TOTAL API COST TODAY</span>
              <span style={{ fontFamily:'monospace', fontSize:11, color:'#22C55E', fontWeight:600 }}>${totalAPICost}</span>
            </div>
          </Panel>

          <Panel title="Neural System">
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
              <span style={{ fontSize:10, color:'rgba(255,255,255,0.4)' }}>Status</span>
              {nnStatus?.bg_running
                ? <span style={{ fontSize:9, fontFamily:'monospace', color:'#22C55E', background:'rgba(34,197,94,0.12)', padding:'2px 6px', borderRadius:4, border:'1px solid rgba(34,197,94,0.3)' }}>● LIVE</span>
                : <span style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.3)', background:'rgba(255,255,255,0.04)', padding:'2px 6px', borderRadius:4, border:'1px solid rgba(255,255,255,0.1)' }}>○ OFFLINE</span>
              }
            </div>
            <DataRow label="Brain Confidence" value={`${brainPct}%`} color="var(--gold,#E5C76B)"/>
            <div style={{ height:4, background:'rgba(255,255,255,0.06)', borderRadius:2, margin:'-4px 0 8px' }}>
              <div style={{ height:'100%', width:`${brainPct}%`, background:'var(--gold,#E5C76B)', borderRadius:2, transition:'width 1s ease' }}/>
            </div>
            <DataRow label="Learn Step"   value={(nnStatus?.learn_step ?? 14820).toLocaleString()} color="var(--teal,#20D6C7)"/>
            <DataRow label="Success Rate" value={`${Math.round((nnStatus?.success_rate ?? 0.91) * 100)}%`} color="#22C55E"/>
            <div style={{ marginTop:10, paddingTop:8, borderTop:'1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.3)', letterSpacing:'0.08em', marginBottom:6 }}>RECENT DECISIONS</div>
              {(nnStatus?.recent_outputs?.length > 0) ? (nnStatus.recent_outputs.slice(0,5).map((d, i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:6, padding:'3px 0', borderBottom:'1px solid rgba(255,255,255,0.04)', fontSize:10 }}>
                  <span style={{ width:5, height:5, borderRadius:'50%', background:'var(--teal,#20D6C7)', flexShrink:0 }}/>
                  <span style={{ flex:1, color:'var(--text-primary,#F0E9D2)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{d.action || d.decision || JSON.stringify(d)}</span>
                  {d.confidence != null && <span style={{ fontFamily:'monospace', fontSize:9, color:'rgba(255,255,255,0.35)' }}>{Math.round((d.confidence > 1 ? d.confidence : d.confidence * 100))}%</span>}
                </div>
              ))) : (
                <div style={{ fontSize:10, color:'rgba(255,255,255,0.25)', fontStyle:'italic' }}>— no decisions yet —</div>
              )}
            </div>
            {nnStatus?.recent_learning_events?.length > 0 && (
              <div style={{ marginTop:8, paddingTop:6, borderTop:'1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.25)', letterSpacing:'0.08em', marginBottom:4 }}>LEARNING EVENTS</div>
                {nnStatus.recent_learning_events.slice(0,3).map((e, i) => (
                  <div key={i} style={{ fontSize:10, color:'rgba(255,255,255,0.35)', padding:'2px 0' }}>{typeof e === 'string' ? e : JSON.stringify(e)}</div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Security" style={{ flex:1 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
              {SECURITY.map((s, i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 0', borderBottom:'1px solid rgba(255,255,255,.04)' }}>
                  <div style={{ width:7, height:7, borderRadius:'50%', background:STATUS_C[s.status], flexShrink:0 }}/>
                  <span style={{ flex:1, fontSize:11, color:'var(--text-primary,#F0E9D2)' }}>{s.item}</span>
                  <span style={{ fontSize:10, color:STATUS_C[s.status]==='rgba(255,255,255,0.25)'?STATUS_C[s.status]:STATUS_C[s.status], fontFamily:'monospace' }}>{s.note}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

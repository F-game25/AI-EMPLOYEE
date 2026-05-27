import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, Badge, StatCard, MiniBar, DataRow } from '../ui/primitives'

const FALLBACK_TRACES = [
  { id:'pt-001', agent:'Orchestrator Prime', prompt:'Analyze revenue pathways for Q2 — rank by ROI, identify top 3 with rationale.', output:'Ranked 12 pathways. Top 3: SaaS upsell (3.2×), API licensing (2.8×), Data resale (1.9×).', tokens:{ in:284, out:412 }, latency:'1.4s', score:94, flags:[] },
  { id:'pt-002', agent:'Data Harvester',     prompt:'Scrape competitor pricing from 12 SaaS vendors. Return structured JSON.',           output:'{"vendors":12,"records":2413,"avg_price":"$89/mo","range":"$29-$499"}',             tokens:{ in:156, out:320 }, latency:'3.8s', score:88, flags:[] },
  { id:'pt-003', agent:'Strategy Engine',    prompt:'Compare our pricing to competitor data. Suggest 3 tactical moves.',                  output:'1. Launch $49 tier. 2. Bundle API access. 3. Annual discount 20%.',                  tokens:{ in:490, out:280 }, latency:'2.1s', score:79, flags:['generic_output'] },
  { id:'pt-004', agent:'Code Synthesizer',   prompt:'Generate Stripe webhook handler for subscription events.',                            output:'[48 lines of Python — 4 routes, auth, retry, idempotency]',                         tokens:{ in:320, out:890 }, latency:'4.2s', score:97, flags:[] },
  { id:'pt-005', agent:'Memory Indexer',     prompt:'',                                                                                    output:'',                                                                                   tokens:{ in:0,   out:0   }, latency:'—',    score:0,  flags:['empty_prompt','empty_output'] },
]
const FLAG_C = { empty_prompt:'#EF4444', empty_output:'#EF4444', generic_output:'#F59E0B', missing_context:'#F59E0B', error:'#EF4444' }
const QUALITY = [['Structure','94','var(--gold-bright,#FFD97A)'],['Clarity','88','var(--teal,#20D6C7)'],['Specificity','82','#22C55E'],['Token Eff.','91','#8B8B9E']]

export default function PromptInspectorPage() {
  const promptTraces = useAppStore(s => s.promptTraces)
  const [sel, setSel] = useState(null)
  const [editText, setEditText] = useState('')

  const traces = (promptTraces?.length ? promptTraces : FALLBACK_TRACES)
  const selT = sel ?? traces[0]

  const avgScore = Math.round(traces.filter(t=>t.score>0).reduce((a,t)=>a+t.score,0) / traces.filter(t=>t.score>0).length || 0)
  const flagged  = traces.filter(t => t.flags?.length > 0).length
  const totalTok = traces.reduce((a,t) => a + (t.tokens?.in||0) + (t.tokens?.out||0), 0)

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, flexShrink:0 }}>
        <StatCard label="Avg Quality"   value={`${avgScore}/100`} color="var(--gold,#E5C76B)"  sub="Across all traces"/>
        <StatCard label="Prompts Today" value={traces.length}     color="var(--teal,#20D6C7)"  sub="Traced executions"/>
        <StatCard label="Flagged"       value={flagged}           color={flagged>0?'#EF4444':'#22C55E'} sub="Needs review"/>
        <StatCard label="Total Tokens"  value={totalTok.toLocaleString()} color="#8B8B9E"     sub="In + out"/>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:10, flex:1, minHeight:0 }}>
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <Panel title="Prompt Traces" badge={<Badge label="LIVE INSPECTION" variant="teal"/>} bodyStyle={{ padding:8 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
              {traces.map(t => (
                <div key={t.id} onClick={() => { setSel(t); setEditText(t.prompt) }} style={{ padding:'9px 10px', borderRadius:7, border:`1px solid ${selT?.id===t.id?'rgba(229,199,107,0.4)':'rgba(229,199,107,0.08)'}`, background:selT?.id===t.id?'rgba(229,199,107,0.06)':'var(--bg-elevated,#12141F)', cursor:'pointer' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:5 }}>
                    <span style={{ fontSize:11.5, color:'var(--text-primary,#F0E9D2)', flex:1, fontWeight:500 }}>{t.agent}</span>
                    {t.flags?.length > 0 && t.flags.map(f => <span key={f} style={{ fontSize:8, fontFamily:'monospace', color:FLAG_C[f]||'#9A927E', padding:'1px 4px', border:`1px solid ${FLAG_C[f]||'#9A927E'}55`, borderRadius:3 }}>{f.replace('_',' ')}</span>)}
                    <span style={{ fontFamily:'monospace', fontSize:11, color:t.score>85?'#22C55E':t.score>60?'var(--gold,#E5C76B)':'#EF4444', fontWeight:600 }}>{t.score || '—'}</span>
                  </div>
                  <div style={{ fontSize:10.5, color:'var(--text-secondary,#9A927E)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', marginBottom:4 }}>{t.prompt || <span style={{ color:'rgba(255,255,255,0.2)', fontStyle:'italic' }}>empty prompt</span>}</div>
                  <div style={{ display:'flex', gap:12, fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)' }}>
                    <span>IN: {t.tokens?.in||0}</span><span>OUT: {t.tokens?.out||0}</span><span>⏱ {t.latency}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Prompt Editor" style={{ flex:1 }} bodyStyle={{ display:'flex', flexDirection:'column', gap:8 }}>
            <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', letterSpacing:'0.08em' }}>EDIT · RE-RUN · INJECT LIVE</div>
            <textarea value={editText} onChange={e => setEditText(e.target.value)} placeholder="Select a trace to edit its prompt…" style={{ flex:1, background:'rgba(0,0,0,0.4)', border:'1px solid rgba(229,199,107,0.18)', borderRadius:7, padding:'8px 10px', color:'var(--text-primary,#F0E9D2)', fontFamily:'monospace', fontSize:11, outline:'none', resize:'none', lineHeight:1.5 }}/>
            <div style={{ display:'flex', gap:6 }}>
              <button style={{ flex:1, padding:'7px', background:'linear-gradient(135deg,#FFD97A 0%,#E5C76B 40%,#B8923F 100%)', border:'none', borderRadius:7, color:'#1a1000', fontWeight:700, fontSize:9, cursor:'pointer', fontFamily:'monospace', letterSpacing:'0.08em' }}>RE-RUN</button>
              <button style={{ padding:'7px 11px', background:'transparent', border:'1px solid rgba(32,214,199,.3)', borderRadius:7, color:'var(--teal,#20D6C7)', fontSize:9, cursor:'pointer', fontFamily:'monospace' }}>INJECT</button>
              <button style={{ padding:'7px 11px', background:'transparent', border:'1px solid rgba(229,199,107,.08)', borderRadius:7, color:'var(--text-secondary,#9A927E)', fontSize:9, cursor:'pointer' }}>CLEAR</button>
            </div>
          </Panel>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {selT && (
            <Panel title="Trace Detail" badge={<Badge label={selT.flags?.length>0?'FLAGGED':'CLEAN'} variant={selT.flags?.length>0?'error':'green'}/>}>
              <DataRow label="Agent"   value={selT.agent} color="var(--teal,#20D6C7)"/>
              <DataRow label="Score"   value={selT.score||'—'} color={selT.score>85?'#22C55E':'var(--gold,#E5C76B)'}/>
              <DataRow label="Latency" value={selT.latency}/>
              <DataRow label="Tokens In"  value={(selT.tokens?.in||0).toLocaleString()}/>
              <DataRow label="Tokens Out" value={(selT.tokens?.out||0).toLocaleString()}/>
              {selT.flags?.length > 0 && (
                <div style={{ marginTop:8, padding:'6px 8px', borderRadius:6, background:'rgba(239,68,68,0.06)', border:'1px solid rgba(239,68,68,0.18)', fontSize:10, color:'#EF4444', fontFamily:'monospace' }}>
                  FLAGS: {selT.flags.join(', ')}
                </div>
              )}
              {selT.output && <div style={{ marginTop:8, padding:'7px 9px', borderRadius:6, background:'rgba(0,0,0,0.3)', border:'1px solid rgba(255,255,255,0.06)', fontSize:10, color:'var(--text-secondary,#9A927E)', fontFamily:'monospace', lineHeight:1.5 }}>{selT.output.slice(0,120)}{selT.output.length>120?'…':''}</div>}
            </Panel>
          )}

          <Panel title="Quality Analysis">
            {QUALITY.map(([l,v,c]) => (
              <div key={l} style={{ marginBottom:8 }}>
                <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:3, letterSpacing:'0.06em', textTransform:'uppercase' }}><span>{l}</span><span>{v}</span></div>
                <MiniBar value={+v} color={c}/>
              </div>
            ))}
          </Panel>

          <Panel title="Quality Trend" style={{ flex:1 }}>
            <svg viewBox="0 0 240 50" style={{ width:'100%', height:50 }}>
              <polyline points="0,40 30,36 60,30 90,34 120,24 150,20 180,16 210,18 240,12" fill="none" stroke="var(--gold,#E5C76B)" strokeWidth="1.5"/>
              <polygon points="0,40 30,36 60,30 90,34 120,24 150,20 180,16 210,18 240,12 240,50 0,50" fill="rgba(229,199,107,0.1)"/>
            </svg>
            <div style={{ fontFamily:'monospace', fontSize:10, color:'var(--gold,#E5C76B)', marginTop:4 }}>+18% quality over 7 days</div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

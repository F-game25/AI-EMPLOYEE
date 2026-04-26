import { useState } from 'react'
import { Panel, Badge, MiniBar } from '../ui/primitives'

const TASKS = [
  { id:1, col:'running', title:'Scrape market intelligence feeds',   agent:'Data Harvester',   priority:'HIGH', started:'14:18:02', progress:68, why:'Weekly cadence + signal divergence in pricing feed', did:'Fetched 2,413 records from 12 sources; deduped 342 items.', next:'Enrich with sentiment classifier → store in vector DB' },
  { id:2, col:'running', title:'Compress and archive vector DB',     agent:'Memory Indexer',   priority:'MED',  started:'14:12:44', progress:42, why:'Capacity hit 78%; auto-triggered compaction rule',   did:'Merged 847 near-duplicates; reclaimed 1.2GB.', next:'Reindex strongest clusters + emit checkpoint' },
  { id:3, col:'review',  title:'Revenue pathway analysis v3',        agent:'Orchestrator',     priority:'HIGH', started:'14:05:11', progress:100,why:'User instruction — "analyze revenue pathways"',      did:'Ranked 12 candidate pathways; surfaced top 3 with ROI.', next:'Awaiting your approval to execute pathway #1' },
  { id:4, col:'todo',    title:'Analyze competitor pricing',         agent:'Strategy Engine',  priority:'HIGH', started:'—',        progress:0,  why:'Scheduled weekly brief', did:'—', next:'Dispatch when agent frees up' },
  { id:5, col:'todo',    title:'Generate weekly report PDF',         agent:'Code Synthesizer', priority:'MED',  started:'—',        progress:0,  why:'Friday auto-digest rule', did:'—', next:'Templated — will render once analysis lands' },
  { id:6, col:'todo',    title:'Update knowledge base index',        agent:'Memory Indexer',   priority:'LOW',  started:'—',        progress:0,  why:'Low-priority maintenance', did:'—', next:'Run during next idle window' },
  { id:7, col:'done',    title:'Deploy Stripe API integration',      agent:'Code Synthesizer', priority:'HIGH', started:'14:02:30', progress:100,why:'Milestone goal: monetization pipeline', did:'Generated routes, auth, webhooks. 48 tests passing.', next:'Production deploy → monitor first 100 transactions' },
  { id:8, col:'done',    title:'Fairness audit batch 12',            agent:'Fairness Monitor', priority:'MED',  started:'13:50:12', progress:100,why:'Scheduled audit cadence', did:'Scanned 412 outputs; flagged 1 biased phrasing.', next:'Correction sent to Prompt Inspector' },
]
const COLS = [['todo','Queued','var(--silver-dim,#8B8B9E)'],['running','In Progress','var(--teal,#20D6C7)'],['review','Review','var(--gold-bright,#FFD97A)'],['done','Completed','#22C55E']]
const ERRC = [{ cluster:'API timeout (vendor-x)', n:14, trend:'up' },{ cluster:'Token limit exceeded', n:8, trend:'flat' },{ cluster:'JSON parse failure', n:3, trend:'down' }]
const AUTO = [
  { rule:'If memory > 75% → run sweep',          active:true  },
  { rule:'If agent health < 60% → restart',      active:true  },
  { rule:'On failure cluster (≥3) → notify Doctor', active:true },
  { rule:'Nightly (02:00 UTC) → full backup',    active:false },
]
const OPT = [
  { sug:'Batch memory writes every 5s → -38% write load', gain:'38%' },
  { sug:'Route quick queries to Haiku → -$0.08/task',     gain:'$' },
  { sug:'Pre-warm vector cache on idle → -42% latency',   gain:'42%' },
]

const PRIORITY_COLORS = { HIGH:'#EF4444', MED:'var(--gold-bright,#FFD97A)', LOW:'rgba(255,255,255,0.35)' }

export default function OperationsPage() {
  const [sel, setSel] = useState(null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>
      {/* Kanban */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, flex: 1, minHeight: 0 }}>
        {COLS.map(([id, label, color]) => (
          <Panel key={id} title={label} badge={<span style={{ fontFamily:'monospace', fontSize:11, color:'rgba(255,255,255,0.35)' }}>{TASKS.filter(t => t.col === id).length}</span>} bodyStyle={{ padding: 8 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {TASKS.filter(t => t.col === id).map(t => (
                <div key={t.id} onClick={() => setSel(t)} style={{ padding:'9px 10px', borderRadius:8, border:`1px solid ${sel?.id===t.id?'rgba(229,199,107,0.4)':'rgba(229,199,107,0.08)'}`, background:sel?.id===t.id?'rgba(229,199,107,0.06)':'var(--bg-elevated,#12141F)', cursor:'pointer', transition:'all .12s' }}>
                  <div style={{ fontSize:11.5, color:'var(--text-primary,#F0E9D2)', marginBottom:5, lineHeight:1.4 }}>{t.title}</div>
                  {t.progress > 0 && t.progress < 100 && <MiniBar value={t.progress} color={color} style={{ marginBottom:5 }}/>}
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                    <span style={{ fontSize:10, color:'rgba(255,255,255,0.35)' }}>{t.agent}</span>
                    <span style={{ fontFamily:'monospace', fontSize:9, color:PRIORITY_COLORS[t.priority], letterSpacing:'0.06em' }}>{t.priority}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        ))}
      </div>

      {/* Bottom row */}
      <div style={{ display:'grid', gridTemplateColumns:'1.3fr 1fr 1fr', gap:10, height:200, flexShrink:0 }}>
        <Panel title={sel ? `Task · ${sel.title}` : 'Task Detail'}>
          {sel ? (
            <div style={{ fontSize:11.5, lineHeight:1.6 }}>
              <div style={{ display:'flex', gap:12, marginBottom:8 }}>
                <Badge label={sel.col}       variant={sel.col==='done'?'green':sel.col==='running'?'teal':'gold'}/>
                <Badge label={sel.priority}  variant={sel.priority==='HIGH'?'error':'warn'}/>
                <span style={{ fontFamily:'monospace', fontSize:10, color:'rgba(255,255,255,0.35)' }}>Started {sel.started} · {sel.agent}</span>
              </div>
              <div style={{ marginBottom:7 }}><span style={{ color:'var(--gold-bright,#FFD97A)', fontFamily:'monospace', fontSize:10, letterSpacing:'0.06em' }}>WHAT →</span> <span style={{ color:'var(--text-primary,#F0E9D2)' }}>{sel.title}</span></div>
              <div style={{ marginBottom:7 }}><span style={{ color:'var(--teal,#20D6C7)', fontFamily:'monospace', fontSize:10, letterSpacing:'0.06em' }}>WHY →</span> <span style={{ color:'var(--text-secondary,#9A927E)' }}>{sel.why}</span></div>
              <div style={{ marginBottom:7 }}><span style={{ color:'var(--bronze,#CD7F32)', fontFamily:'monospace', fontSize:10, letterSpacing:'0.06em' }}>DID →</span> <span style={{ color:'var(--text-secondary,#9A927E)' }}>{sel.did}</span></div>
              <div><span style={{ color:'#8B8B9E', fontFamily:'monospace', fontSize:10, letterSpacing:'0.06em' }}>NEXT →</span> <span style={{ color:'var(--text-secondary,#9A927E)' }}>{sel.next}</span></div>
            </div>
          ) : <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100%', color:'rgba(255,255,255,0.25)', fontSize:11 }}>Click a task card to see details</div>}
        </Panel>

        <Panel title="Error Clustering">
          <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
            {ERRC.map(e => (
              <div key={e.cluster} style={{ padding:'8px 10px', borderRadius:7, border:'1px solid rgba(229,199,107,0.08)', background:'var(--bg-elevated,#12141F)', display:'flex', alignItems:'center', gap:10 }}>
                <span style={{ fontSize:11, color:'var(--text-primary,#F0E9D2)', flex:1 }}>{e.cluster}</span>
                <span style={{ fontFamily:'monospace', fontSize:11, color:e.trend==='up'?'#EF4444':'var(--text-secondary,#9A927E)' }}>{e.n}</span>
                <span style={{ color:e.trend==='up'?'#EF4444':e.trend==='down'?'#22C55E':'rgba(255,255,255,0.35)' }}>{e.trend==='up'?'↑':e.trend==='down'?'↓':'→'}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Automation + Optimizer">
          <div style={{ fontSize:9, color:'rgba(255,255,255,0.35)', letterSpacing:'0.08em', marginBottom:5 }}>RULES</div>
          {AUTO.map(r => (
            <div key={r.rule} style={{ display:'flex', justifyContent:'space-between', padding:'4px 0', fontSize:10.5 }}>
              <span style={{ color:r.active?'var(--text-primary,#F0E9D2)':'rgba(255,255,255,0.35)' }}>{r.rule}</span>
              <span style={{ color:r.active?'#22C55E':'rgba(255,255,255,0.35)', fontFamily:'monospace', fontSize:9 }}>{r.active?'ON':'OFF'}</span>
            </div>
          ))}
          <div style={{ fontSize:9, color:'rgba(255,255,255,0.35)', letterSpacing:'0.08em', margin:'8px 0 5px' }}>OPTIMIZER</div>
          {OPT.map(o => (
            <div key={o.sug} style={{ fontSize:10.5, color:'var(--text-secondary,#9A927E)', padding:'4px 0' }}>
              <span style={{ color:'var(--gold-bright,#FFD97A)', fontFamily:'monospace', marginRight:6 }}>{o.gain}</span>{o.sug}
            </div>
          ))}
        </Panel>
      </div>
    </div>
  )
}

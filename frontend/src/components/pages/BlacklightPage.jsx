import { useState, useEffect } from 'react'
import { MiniBar, DataRow } from '../ui/primitives'
import api from '../../api/client'

/* ── Blacklight design tokens ──────────────────────────────────────── */
const P  = '#A855F7'   // purple
const PB = '#C084FC'   // purple-bright
const PD = '#7C3AED'   // purple-deep
const PE = '#581C87'   // purple-edge

function BLPanel({ title, badge, children, style = {}, bodyStyle = {} }) {
  return (
    <div style={{ background:'linear-gradient(180deg,rgba(88,28,135,0.14) 0%,rgba(7,5,14,0.96) 100%)', border:`1px solid rgba(168,85,247,0.22)`, borderRadius:10, overflow:'hidden', display:'flex', flexDirection:'column', ...style }}>
      <div style={{ position:'relative', height:1, background:`linear-gradient(90deg,transparent,${P},transparent)`, opacity:0.6 }}/>
      {title && (
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 14px 0', flexShrink:0 }}>
          <span style={{ fontSize:10, fontFamily:'monospace', letterSpacing:'0.12em', textTransform:'uppercase', color:P }}>{title}</span>
          {badge}
        </div>
      )}
      <div style={{ padding:'10px 14px', flex:1, minHeight:0, ...bodyStyle }}>{children}</div>
    </div>
  )
}

function BLBadge({ label, variant }) {
  const c = variant==='error'?'#EF4444':variant==='warn'?'#F59E0B':variant==='ok'?'#22C55E':PB
  return <span style={{ fontFamily:'monospace', fontSize:8, letterSpacing:'0.1em', color:c, padding:'2px 6px', border:`1px solid ${c}44`, borderRadius:4 }}>{label}</span>
}

function BLStat({ label, value, sub, color = PB }) {
  return (
    <div style={{ background:'linear-gradient(180deg,rgba(88,28,135,0.12),rgba(7,5,14,0.97))', border:`1px solid rgba(168,85,247,0.2)`, borderRadius:9, padding:'12px 14px', position:'relative', overflow:'hidden' }}>
      <div style={{ position:'absolute', top:0, left:0, right:0, height:1, background:`linear-gradient(90deg,transparent,${PD},transparent)` }}/>
      <div style={{ fontFamily:'monospace', fontSize:22, fontWeight:700, color, marginBottom:2, textShadow:`0 0 20px ${color}55` }}>{value}</div>
      <div style={{ fontSize:10, color:'rgba(255,255,255,0.5)', letterSpacing:'0.06em', textTransform:'uppercase' }}>{label}</div>
      {sub && <div style={{ fontSize:9, color:'rgba(168,85,247,0.6)', marginTop:3, fontFamily:'monospace' }}>{sub}</div>}
    </div>
  )
}

const SEV_C  = { HIGH:'#EF4444', MED:'#F59E0B', LOW:'rgba(168,85,247,0.5)' }
const SEV_GL = { HIGH:'rgba(239,68,68,0.3)', MED:'rgba(245,158,11,0.2)', LOW:`rgba(168,85,247,0.12)` }

export default function BlacklightPage() {
  const [events, setEvents] = useState([])
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [sel, setSel] = useState(null)

  useEffect(() => {
    const fetch_alerts = async () => {
      try {
        const res = await api.get('/api/blacklight/alerts')
        setEvents(res?.alerts || [])
        setRules(res?.rules || [])
        setLoading(false)
      } catch (e) {
        setLoading(false)
      }
    }
    fetch_alerts()
    const t = setInterval(fetch_alerts, 6000)
    return () => clearInterval(t)
  }, [])

  const selE   = sel ?? (events.length > 0 ? events[0] : null)
  const blocked = events.filter(e => e.blocked).length
  const high    = events.filter(e => e.severity === 'HIGH').length
  // Build matrix from live events
  const MATRIX = (() => {
    const threatMap = {}
    events.forEach(e => {
      const key = e.type || 'Unknown'
      if (!threatMap[key]) threatMap[key] = { severity: e.severity, count: 0 }
      threatMap[key].count++
    })
    return Object.entries(threatMap).slice(0, 6).map(([name, data]) => [name, data.severity, data.count])
  })()

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>

      {/* Header scan-line bar */}
      <div style={{ height:2, background:`linear-gradient(90deg,transparent 0%,${P} 30%,${PB} 50%,${P} 70%,transparent 100%)`, borderRadius:1, flexShrink:0, boxShadow:`0 0 12px ${P}88` }}/>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, flexShrink:0 }}>
        <BLStat label="Events Today"  value={loading ? '—' : events.length}                      color={high>0?'#EF4444':PB}         sub={`${high} HIGH severity`}/>
        <BLStat label="Blocked"       value={loading ? '—' : blocked}                              color="#EF4444"                      sub="Threats neutralised"/>
        <BLStat label="Rules Active"  value={loading ? '—' : rules.filter(r=>r.active).length}   color={PB}                           sub={`of ${rules.length} total`}/>
        <BLStat label="Threat Level"  value={high>2?'HIGH':high>0?'MED':'LOW'}                     color={high>2?'#EF4444':high>0?'#F59E0B':'#22C55E'} sub="Current posture"/>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:10, flex:1, minHeight:0 }}>
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>

          <BLPanel title="Security Events" badge={<BLBadge label={loading?'LOADING':high>0?'THREAT DETECTED':'ALL CLEAR'} variant={loading?'default':high>0?'error':'ok'}/>} bodyStyle={{ padding:8 }}>
            {loading ? (
              <div style={{ fontSize:11, color:'rgba(168,85,247,0.4)', fontFamily:'monospace' }}>Fetching alerts…</div>
            ) : !events.length ? (
              <div style={{ fontSize:11, color:'#22C55E', fontFamily:'monospace' }}>✓ No alerts detected</div>
            ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
              {events.map(e => (
                <div key={e.id} onClick={() => setSel(e)} style={{ padding:'9px 10px', borderRadius:7, border:`1px solid ${selE?.id===e.id?`${SEV_C[e.severity]}55`:`rgba(168,85,247,0.1)`}`, background:selE?.id===e.id?SEV_GL[e.severity]:`rgba(88,28,135,0.06)`, cursor:'pointer', position:'relative', overflow:'hidden', transition:'all .12s' }}>
                  <div style={{ position:'absolute', top:0, bottom:0, left:0, width:2, background:SEV_C[e.severity], boxShadow:`0 0 8px ${SEV_C[e.severity]}` }}/>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4, paddingLeft:6 }}>
                    <span style={{ fontFamily:'monospace', fontSize:9, color:SEV_C[e.severity], fontWeight:700, letterSpacing:'0.08em' }}>{e.severity}</span>
                    <span style={{ fontSize:11.5, color:'#E8D5FF', flex:1, fontWeight:500 }}>{e.type}</span>
                    {e.blocked && <span style={{ fontFamily:'monospace', fontSize:8, color:'#EF4444', padding:'1px 5px', border:'1px solid rgba(239,68,68,0.5)', borderRadius:3, background:'rgba(239,68,68,0.06)' }}>BLOCKED</span>}
                    <span style={{ fontFamily:'monospace', fontSize:9, color:`rgba(168,85,247,0.5)` }}>{e.ts}</span>
                  </div>
                  <div style={{ fontSize:10.5, color:'rgba(200,180,255,0.55)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', paddingLeft:6 }}>{e.detail}</div>
                  <div style={{ fontSize:9, color:`rgba(168,85,247,0.4)`, fontFamily:'monospace', marginTop:3, paddingLeft:6 }}>{e.agent}</div>
                </div>
              ))}
            </div>
            )}
          </BLPanel>

          <BLPanel title="Rule Engine" style={{ flex:1 }}>
            {loading ? (
              <div style={{ fontSize:11, color:'rgba(168,85,247,0.4)', fontFamily:'monospace' }}>Loading rules…</div>
            ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
              {rules.map(r => (
                <div key={r.rule} style={{ display:'flex', alignItems:'center', gap:10, padding:'6px 0', borderBottom:`1px solid rgba(168,85,247,0.08)` }}>
                  <div style={{ width:7, height:7, borderRadius:'50%', background:r.active?PB:'rgba(168,85,247,0.2)', boxShadow:r.active?`0 0 8px ${P}`:  'none', flexShrink:0 }}/>
                  <span style={{ flex:1, fontSize:11, color:r.active?'#E8D5FF':'rgba(168,85,247,0.3)' }}>{r.rule}</span>
                  <span style={{ fontFamily:'monospace', fontSize:10, color:r.hits>0?'#F59E0B':`rgba(168,85,247,0.35)` }}>{r.hits}</span>
                </div>
              ))}
            </div>
            )}
          </BLPanel>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {selE && (
            <BLPanel title="Event Detail" badge={<BLBadge label={selE.severity} variant={selE.severity==='HIGH'?'error':selE.severity==='MED'?'warn':'default'}/>}>
              <div style={{ display:'flex', flexDirection:'column', gap:0 }}>
                {[['Type', selE.type, SEV_C[selE.severity]], ['Agent', selE.agent, PB], ['Time', selE.ts, null], ['Blocked', selE.blocked?'YES':'NO', selE.blocked?'#EF4444':'#22C55E']].map(([l,v,c]) => (
                  <div key={l} style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:`1px solid rgba(168,85,247,0.08)` }}>
                    <span style={{ fontSize:11, color:`rgba(168,85,247,0.6)` }}>{l}</span>
                    <span style={{ fontFamily:'monospace', fontSize:11, color:c||'#E8D5FF', fontWeight:500 }}>{v}</span>
                  </div>
                ))}
              </div>
              <div style={{ marginTop:8, padding:'7px 9px', borderRadius:6, background:`${SEV_C[selE.severity]}09`, border:`1px solid ${SEV_C[selE.severity]}28`, fontSize:11, color:'rgba(200,180,255,0.7)', lineHeight:1.5 }}>{selE.detail}</div>
              {selE.severity === 'HIGH' && (
                <div style={{ display:'flex', gap:5, marginTop:8 }}>
                  <button style={{ flex:1, padding:'6px', borderRadius:6, border:'1px solid rgba(239,68,68,.45)', background:'rgba(239,68,68,.09)', color:'#EF4444', cursor:'pointer', fontSize:9, fontFamily:'monospace', letterSpacing:'0.08em' }}>QUARANTINE</button>
                  <button style={{ flex:1, padding:'6px', borderRadius:6, border:`1px solid rgba(168,85,247,.4)`, background:`rgba(168,85,247,.08)`, color:PB, cursor:'pointer', fontSize:9, fontFamily:'monospace', letterSpacing:'0.08em' }}>REVIEW</button>
                </div>
              )}
            </BLPanel>
          )}

          <BLPanel title="Threat Matrix" style={{ flex:1 }}>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6 }}>
              {MATRIX.map(([l,s,n]) => (
                <div key={l} style={{ padding:'8px 9px', borderRadius:7, background:`rgba(88,28,135,0.1)`, border:`1px solid ${SEV_C[s]}28`, position:'relative', overflow:'hidden' }}>
                  <div style={{ position:'absolute', bottom:0, left:0, right:0, height:1, background:`linear-gradient(90deg,transparent,${SEV_C[s]}66,transparent)` }}/>
                  <div style={{ fontFamily:'monospace', fontSize:18, color:SEV_C[s], fontWeight:700, textShadow:`0 0 14px ${SEV_C[s]}88` }}>{n}</div>
                  <div style={{ fontSize:9, color:`rgba(168,85,247,0.55)`, letterSpacing:'0.08em', textTransform:'uppercase', marginTop:1 }}>{l}</div>
                </div>
              ))}
            </div>
          </BLPanel>

          <BLPanel title="UV Scan" style={{ flexShrink:0 }}>
            <svg viewBox="0 0 240 36" style={{ width:'100%', height:36 }}>
              <defs>
                <linearGradient id="uvg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={P} stopOpacity=".5"/>
                  <stop offset="100%" stopColor={P} stopOpacity="0"/>
                </linearGradient>
              </defs>
              <polyline points="0,28 20,24 40,20 60,26 80,12 100,18 120,8 140,15 160,10 180,18 200,14 220,20 240,16" fill="none" stroke={PB} strokeWidth="1.5"/>
              <polygon points="0,28 20,24 40,20 60,26 80,12 100,18 120,8 140,15 160,10 180,18 200,14 220,20 240,16 240,36 0,36" fill="url(#uvg)"/>
            </svg>
            <div style={{ fontFamily:'monospace', fontSize:9, color:`rgba(168,85,247,0.55)`, marginTop:4, letterSpacing:'0.08em' }}>ANOMALY SIGNATURE — LIVE SCAN</div>
          </BLPanel>
        </div>
      </div>
    </div>
  )
}

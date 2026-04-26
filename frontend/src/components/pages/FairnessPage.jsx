import { useState, useEffect } from 'react'
import { Panel, Badge, StatCard, MiniBar } from '../ui/primitives'
import api from '../../api/client'

export default function FairnessPage() {
  const [categories, setCategories] = useState([])
  const [samples, setSamples] = useState([])
  const [audits, setAudits] = useState([])
  const [loading, setLoading] = useState(true)
  const [sel, setSel] = useState(null)
  const [correcting, setCorrecting] = useState(false)
  const [corrected, setCorrected] = useState(null)

  useEffect(() => {
    const fetch_fairness = async () => {
      try {
        const fairness = await api.get('/api/fairness/report')
        setCategories(fairness?.categories || [])
        setSamples(fairness?.samples || [])

        const audit = await api.get('/api/audit/events')
        // Group audit events into batches by date
        if (audit?.events) {
          const batches = {}
          audit.events.forEach(e => {
            const date = new Date(e.ts).toLocaleDateString('en-US', {month:'short', day:'numeric'})
            if (!batches[date]) batches[date] = { date, outputs: 0, flagged: 0, passed: true }
            batches[date].outputs++
            if (e.severity === 'HIGH' || e.severity === 'WARN') batches[date].flagged++
            if (e.severity === 'ERROR') batches[date].passed = false
          })
          setAudits(Object.values(batches).slice(0, 4))
        }
        setLoading(false)
      } catch (e) {
        setLoading(false)
      }
    }
    fetch_fairness()
    const t = setInterval(fetch_fairness, 8000)
    return () => clearInterval(t)
  }, [])

  const selS = sel ?? (samples.length > 0 ? samples[0] : null)

  const handleApplyCorrection = async () => {
    if (!selS) return
    setCorrecting(true); setCorrected(null)
    try {
      await api.chat.send(`Apply fairness correction for flag "${selS.flag}": Replace "${selS.output}" with "${selS.corrected}"`)
      setCorrected({ ok: true, id: selS.id })
    } catch {
      setCorrected({ ok: false, id: selS.id })
    }
    setCorrecting(false)
  }
  const avgScore = categories.length ? Math.round(categories.reduce((a,c) => a + (c.score || 0), 0) / categories.length) : loading ? 0 : 100
  const totalFlagged = categories.reduce((a,c) => a + (c.flagged || 0), 0)

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, flexShrink:0 }}>
        <StatCard label="Fairness Score" value={loading ? '—' : `${avgScore}/100`}  color={avgScore>90?'#22C55E':'#F59E0B'}     sub="Avg across categories"/>
        <StatCard label="Outputs Audited" value={loading ? '—' : categories[0]?.samples || '0'} color="var(--teal,#20D6C7)"                  sub="Latest audit"/>
        <StatCard label="Flags Raised"    value={loading ? '—' : totalFlagged}      color={totalFlagged>5?'#F59E0B':'#22C55E'}  sub="This batch"/>
        <StatCard label="Passed Audits"   value={loading ? '—' : `${audits.filter(a=>a.passed).length}/${audits.length}`} color="#22C55E" sub="Recent history"/>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:10, flex:1, minHeight:0 }}>
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <Panel title="Bias Categories" badge={<Badge label={loading ? 'LOADING' : 'REPORT'} variant="gold"/>}>
            {loading ? (
              <div style={{ fontSize:12, color:'rgba(255,255,255,0.3)', fontFamily:'monospace' }}>Fetching fairness report…</div>
            ) : !categories.length ? (
              <div style={{ fontSize:12, color:'rgba(255,255,255,0.3)', fontFamily:'monospace' }}>No categories available</div>
            ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {categories.map(c => (
                <div key={c.cat} style={{ padding:'9px 10px', borderRadius:7, border:'1px solid rgba(229,199,107,0.08)', background:'var(--bg-elevated,#12141F)' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6 }}>
                    <span style={{ fontSize:12, color:'var(--text-primary,#F0E9D2)', width:80, flexShrink:0 }}>{c.cat}</span>
                    <div style={{ flex:1 }}><MiniBar value={c.score} color={c.score>93?'#22C55E':c.score>85?'var(--gold,#E5C76B)':'#F59E0B'}/></div>
                    <span style={{ fontFamily:'monospace', fontSize:11, color:c.score>93?'#22C55E':c.score>85?'var(--gold,#E5C76B)':'#F59E0B', width:36, textAlign:'right', flexShrink:0 }}>{c.score}%</span>
                    <span style={{ fontFamily:'monospace', fontSize:10, color:c.flagged>0?'#F59E0B':'rgba(255,255,255,0.25)', width:18, textAlign:'right', flexShrink:0 }}>{c.flagged}</span>
                  </div>
                  {c.flagged > 0 && <div style={{ fontSize:10, color:'var(--text-secondary,#9A927E)', paddingLeft:4 }}>{c.bias}</div>}
                </div>
              ))}
            </div>
            )}
          </Panel>

          <Panel title="Audit History" style={{ flex:1 }}>
            {loading ? (
              <div style={{ fontSize:12, color:'rgba(255,255,255,0.3)', fontFamily:'monospace' }}>Loading audit history…</div>
            ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
              <div style={{ display:'grid', gridTemplateColumns:'80px 80px 60px 60px 60px', gap:8, padding:'3px 8px', fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.25)', letterSpacing:'0.06em', textTransform:'uppercase' }}>
                <span>Date</span><span>Outputs</span><span>Flagged</span><span>Status</span><span></span>
              </div>
              {audits.map((a, i) => (
                <div key={i} style={{ display:'grid', gridTemplateColumns:'80px 80px 60px 60px 60px', gap:8, padding:'7px 8px', borderRadius:6, background:'var(--bg-elevated,#12141F)', border:`1px solid ${a.passed?'rgba(34,197,94,0.12)':'rgba(239,68,68,0.18)'}`, alignItems:'center' }}>
                  <span style={{ fontSize:10, color:'rgba(255,255,255,0.35)' }}>{a.date}</span>
                  <span style={{ fontFamily:'monospace', fontSize:10, color:'var(--text-secondary,#9A927E)' }}>{a.outputs}</span>
                  <span style={{ fontFamily:'monospace', fontSize:10, color:a.flagged>5?'#F59E0B':a.flagged>0?'rgba(255,255,255,0.5)':'#22C55E' }}>{a.flagged}</span>
                  <Badge label={a.passed?'PASS':'FAIL'} variant={a.passed?'green':'error'}/>
                </div>
              ))}
            </div>
            )}
          </Panel>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          <Panel title="Flagged Samples" bodyStyle={{ padding:8 }}>
            {loading ? (
              <div style={{ fontSize:11, color:'rgba(255,255,255,0.3)', fontFamily:'monospace' }}>Loading samples…</div>
            ) : !samples.length ? (
              <div style={{ fontSize:11, color:'#22C55E', fontFamily:'monospace' }}>✓ No flagged samples</div>
            ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
              {samples.map(s => (
                <div key={s.id} onClick={() => setSel(s)} style={{ padding:'8px 9px', borderRadius:7, border:`1px solid ${selS?.id===s.id?'rgba(245,158,11,0.4)':'rgba(229,199,107,0.08)'}`, background:selS?.id===s.id?'rgba(245,158,11,0.06)':'var(--bg-elevated,#12141F)', cursor:'pointer' }}>
                  <div style={{ display:'flex', gap:6, marginBottom:4 }}>
                    <Badge label={s.severity} variant={s.severity==='HIGH'?'error':'warn'}/>
                    <span style={{ fontFamily:'monospace', fontSize:9, color:'rgba(255,255,255,0.35)' }}>{s.flag.replace(/_/g,' ')}</span>
                  </div>
                  <div style={{ fontSize:10.5, color:'var(--text-secondary,#9A927E)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{s.output}</div>
                </div>
              ))}
            </div>
            )}
          </Panel>

          {selS && (
            <Panel title="Sample Detail" style={{ flex:1 }}>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', letterSpacing:'0.06em', marginBottom:5 }}>ORIGINAL</div>
              <div style={{ padding:'7px 9px', borderRadius:6, background:'rgba(239,68,68,0.05)', border:'1px solid rgba(239,68,68,0.18)', fontSize:11, color:'var(--text-secondary,#9A927E)', lineHeight:1.5, marginBottom:8 }}>{selS.output}</div>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', letterSpacing:'0.06em', marginBottom:5 }}>CORRECTED</div>
              <div style={{ padding:'7px 9px', borderRadius:6, background:'rgba(34,197,94,0.05)', border:'1px solid rgba(34,197,94,0.18)', fontSize:11, color:'var(--text-primary,#F0E9D2)', lineHeight:1.5 }}>{selS.corrected}</div>
              <button onClick={handleApplyCorrection} disabled={correcting} style={{ width:'100%', marginTop:10, padding:'7px', background: correcting ? 'rgba(229,199,107,0.1)' : corrected?.ok && corrected?.id === selS?.id ? 'rgba(34,197,94,0.15)' : 'linear-gradient(135deg,#FFD97A 0%,#E5C76B 40%,#B8923F 100%)', border: corrected?.id === selS?.id ? `1px solid ${corrected.ok?'rgba(34,197,94,0.4)':'rgba(239,68,68,0.4)'}` : 'none', borderRadius:7, color: correcting ? 'var(--gold,#E5C76B)' : corrected?.ok && corrected?.id === selS?.id ? '#22C55E' : '#1a1000', fontWeight:700, fontSize:9, cursor: correcting ? 'wait' : 'pointer', fontFamily:'monospace', letterSpacing:'0.08em' }}>
                {correcting ? 'APPLYING...' : corrected?.ok && corrected?.id === selS?.id ? '✓ APPLIED' : corrected?.id === selS?.id ? '✗ FAILED' : 'APPLY CORRECTION'}
              </button>
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}

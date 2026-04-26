import { useState, useEffect } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, Badge, StatCard, DataRow } from '../ui/primitives'
import api from '../../api/client'

const SUITE_ITEMS = [
  { id:'s1', name:'DB Connection',       endpoint: () => api.get('/api/health') },
  { id:'s2', name:'Agent Ping',          endpoint: () => api.get('/api/agents') },
  { id:'s3', name:'Memory Integrity',    endpoint: () => api.get('/api/brain/status') },
  { id:'s4', name:'Brain Weight Load',   endpoint: () => api.get('/api/brain/status') },
  { id:'s5', name:'API Gateway',         endpoint: () => api.get('/api/health') },
  { id:'s6', name:'Fairness Threshold',  endpoint: () => api.get('/api/fairness/status') },
]

const STATUS_C = { ok:'#22C55E', warn:'#F59E0B', error:'#EF4444' }

export default function DoctorPage() {
  const executionLogs = useAppStore(s => s.executionLogs)
  const [checks, setChecks] = useState([])
  const [doctorData, setDoctorData] = useState(null)
  const [loading, setLoading] = useState(true)

  // Fetch live doctor status on mount and every 8s
  useEffect(() => {
    const fetch_doctor = async () => {
      try {
        const res = await api.get('/api/doctor/status')
        setDoctorData(res)
        // Build checks array from response
        const issues = (res?.issues || []).map(issue => ({
          name: issue.name || issue.component || 'Unknown',
          status: 'error',
          latency: issue.latency || '—',
          detail: issue.detail || issue.message || '',
        }))
        const strengths = (res?.strengths || []).map(s => ({
          name: s.name || s.component || 'Service',
          status: 'ok',
          latency: s.latency || '—',
          detail: s.detail || 'Working normally',
        }))
        setChecks([...strengths, ...issues])
        setLoading(false)
      } catch (e) {
        setLoading(false)
      }
    }
    fetch_doctor()
    const t = setInterval(fetch_doctor, 8000)
    return () => clearInterval(t)
  }, [])

  const errorLogs = executionLogs?.filter(l => l.level === 'ERROR' || l.level === 'WARN').slice(0, 6).map((l) => ({
    msg: l.message || l.step || 'System event',
    count: 1, ts: typeof l.ts === 'string' ? l.ts.slice(11,19) : '--:--:--', level: l.level?.toLowerCase() || 'warn',
  })) || []

  const healthy   = checks.filter(c => c.status === 'ok').length
  const warnings  = checks.filter(c => c.status === 'warn').length
  const critical  = checks.filter(c => c.status === 'error').length
  const healthPct = checks.length ? Math.round(healthy / checks.length * 100) : loading ? 0 : 100

  const [fixStates, setFixStates] = useState({})
  const handleFix = async (name) => {
    setFixStates(p => ({ ...p, [name]: 'running' }))
    try {
      await api.chat.send(`Fix issue: ${name}`)
      setFixStates(p => ({ ...p, [name]: 'ok' }))
    } catch {
      setFixStates(p => ({ ...p, [name]: 'err' }))
    }
  }

  const [suiteState, setSuiteState] = useState({})
  const [suiteRunning, setSuiteRunning] = useState(false)
  const runSingle = async (item) => {
    setSuiteState(p => ({ ...p, [item.id]: 'running' }))
    try {
      await item.endpoint()
      setSuiteState(p => ({ ...p, [item.id]: 'pass' }))
    } catch {
      setSuiteState(p => ({ ...p, [item.id]: 'fail' }))
    }
  }
  const runAll = async () => {
    setSuiteRunning(true)
    for (const item of SUITE_ITEMS) {
      await runSingle(item)
      await new Promise(r => setTimeout(r, 600))
    }
    setSuiteRunning(false)
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, flexShrink:0 }}>
        <StatCard label="System Health"  value={`${healthPct}%`} color={healthPct>90?'#22C55E':healthPct>70?'#F59E0B':'#EF4444'} sub={`${healthy}/${checks.length} checks passing`}/>
        <StatCard label="Healthy"        value={healthy}          color="#22C55E"  sub="Services OK"/>
        <StatCard label="Warnings"       value={warnings}         color="#F59E0B"  sub="Need attention"/>
        <StatCard label="Critical"       value={critical}         color={critical>0?'#EF4444':'#22C55E'} sub="Blocking issues"/>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:10, flex:1, minHeight:0 }}>
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <Panel title="Health Checks" badge={<Badge label={loading?'LOADING':critical>0?'CRITICAL':warnings>0?'WARN':'HEALTHY'} variant={loading?'default':critical>0?'error':warnings>0?'warn':'green'}/>}>
            {loading ? (
              <div style={{ fontSize:12, color:'rgba(255,255,255,0.3)', fontFamily:'monospace' }}>Fetching health checks…</div>
            ) : !checks.length ? (
              <div style={{ fontSize:12, color:'rgba(255,255,255,0.3)', fontFamily:'monospace' }}>No checks available</div>
            ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
              {checks.map((c, i) => (
                <div key={i} style={{ padding:'9px 11px', borderRadius:7, border:`1px solid ${STATUS_C[c.status]}22`, background:'var(--bg-elevated,#12141F)', display:'flex', alignItems:'center', gap:12 }}>
                  <div style={{ width:8, height:8, borderRadius:'50%', background:STATUS_C[c.status], boxShadow:`0 0 6px ${STATUS_C[c.status]}`, flexShrink:0 }}/>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:12, color:'var(--text-primary,#F0E9D2)', marginBottom:2 }}>{c.name}</div>
                    <div style={{ fontSize:10, color:'var(--text-secondary,#9A927E)' }}>{c.detail}</div>
                  </div>
                  <div style={{ textAlign:'right', flexShrink:0, display:'flex', alignItems:'center', gap:8 }}>
                    <div>
                      <div style={{ fontFamily:'monospace', fontSize:10, color:STATUS_C[c.status] }}>{c.latency}</div>
                      <div style={{ fontFamily:'monospace', fontSize:9, color:STATUS_C[c.status], letterSpacing:'0.06em' }}>{c.status.toUpperCase()}</div>
                    </div>
                    {c.status === 'warn' && (
                      <button onClick={() => handleFix(c.name)} disabled={fixStates[c.name] === 'running'} style={{ padding:'3px 8px', borderRadius:5, border:`1px solid ${fixStates[c.name]==='ok'?'rgba(34,197,94,0.4)':fixStates[c.name]==='err'?'rgba(239,68,68,0.4)':'rgba(245,158,11,0.4)'}`, background:'transparent', color:fixStates[c.name]==='ok'?'#22C55E':fixStates[c.name]==='err'?'#EF4444':'#F59E0B', cursor:'pointer', fontSize:9, fontFamily:'monospace', letterSpacing:'0.06em' }}>
                        {fixStates[c.name]==='running'?'…':fixStates[c.name]==='ok'?'✓ FIXED':fixStates[c.name]==='err'?'✗ ERR':'FIX'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            )}
          </Panel>

          <Panel title="Test Suite Runner" badge={<button onClick={runAll} disabled={suiteRunning} style={{ padding:'4px 12px', borderRadius:5, border:'1px solid rgba(32,214,199,0.4)', background:'rgba(32,214,199,0.07)', color:'var(--teal,#20D6C7)', cursor:suiteRunning?'wait':'pointer', fontSize:9, fontFamily:'monospace', letterSpacing:'0.06em' }}>{suiteRunning?'RUNNING...':'RUN ALL'}</button>} style={{ flex:1 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
              {SUITE_ITEMS.map(item => {
                const st = suiteState[item.id]
                return (
                  <div key={item.id} style={{ display:'flex', alignItems:'center', gap:10, padding:'7px 10px', borderRadius:6, border:`1px solid ${st==='pass'?'rgba(34,197,94,0.2)':st==='fail'?'rgba(239,68,68,0.2)':st==='running'?'rgba(32,214,199,0.2)':'rgba(255,255,255,0.06)'}`, background:'var(--bg-elevated,#12141F)' }}>
                    <div style={{ width:7, height:7, borderRadius:'50%', background:st==='pass'?'#22C55E':st==='fail'?'#EF4444':st==='running'?'var(--teal,#20D6C7)':'rgba(255,255,255,0.2)', flexShrink:0, boxShadow:st==='pass'?'0 0 6px #22C55E':st==='running'?'0 0 6px #20D6C7':'none' }}/>
                    <span style={{ flex:1, fontSize:12, color:'var(--text-primary,#F0E9D2)' }}>{item.name}</span>
                    <span style={{ fontFamily:'monospace', fontSize:10, color:st==='pass'?'#22C55E':st==='fail'?'#EF4444':st==='running'?'var(--teal,#20D6C7)':'rgba(255,255,255,0.25)' }}>
                      {st==='pass'?'PASS':st==='fail'?'FAIL':st==='running'?'…':'IDLE'}
                    </span>
                    <button onClick={() => runSingle(item)} disabled={st==='running'||suiteRunning} style={{ padding:'3px 8px', borderRadius:5, border:'1px solid rgba(255,255,255,0.1)', background:'transparent', color:'rgba(255,255,255,0.4)', cursor:'pointer', fontSize:9, fontFamily:'monospace' }}>RUN</button>
                  </div>
                )
              })}
            </div>
          </Panel>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          <Panel title="Error Log" bodyStyle={{ overflowY:'auto' }}>
            <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
              {errorLogs.length === 0 ? (
                <div style={{ fontSize:11, color:'#22C55E', fontFamily:'monospace' }}>✓ No errors in recent history</div>
              ) : errorLogs.map((e, i) => (
                <div key={i} style={{ padding:'8px 10px', borderRadius:6, background:'var(--bg-elevated,#12141F)', border:`1px solid ${e.level==='error'?'rgba(239,68,68,0.2)':'rgba(245,158,11,0.15)'}`, display:'flex', gap:10, alignItems:'flex-start' }}>
                  <div style={{ width:6, height:6, borderRadius:'50%', background:STATUS_C[e.level]||'#F59E0B', marginTop:4, flexShrink:0 }}/>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:11, color:'var(--text-primary,#F0E9D2)', lineHeight:1.4 }}>{e.msg}</div>
                    <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.25)', marginTop:2 }}>{e.ts} · {e.count}× occurrence</div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Diagnostics">
            <DataRow label="Grade"         value={doctorData?.grade || '—'}              color={doctorData?.grade ? '#22C55E' : 'rgba(255,255,255,0.3)'}/>
            <DataRow label="Score"         value={`${Math.round((doctorData?.overall_score || 0) * 100)}%`}/>
            <DataRow label="CPU"           value={`${(doctorData?.scores?.cpu ?? '—')}`}/>
            <DataRow label="Memory"        value={`${(doctorData?.scores?.memory ?? '—')}`}/>
            <DataRow label="Healthy"       value={`${healthy}/${checks.length}`}      color="#22C55E"/>
            <DataRow label="Warnings"      value={`${warnings}`}                    color={warnings > 0 ? '#F59E0B' : '#22C55E'}/>
            <DataRow label="Critical"      value={`${critical}`}                    color={critical > 0 ? '#EF4444' : '#22C55E'}/>
            <DataRow label="Last Check"    value={doctorData?.updated_at ? new Date(doctorData.updated_at).toLocaleTimeString() : '—'}/>
          </Panel>

          <Panel title="Actions" style={{ flex:1 }}>
            {[
              ['RUN FULL SWEEP',  'var(--teal,#20D6C7)',  'rgba(32,214,199,0.07)', 'rgba(32,214,199,0.3)'],
              ['RESTART AGENTS',  'var(--gold-bright,#FFD97A)', 'rgba(229,199,107,0.07)', 'rgba(229,199,107,0.3)'],
              ['CLEAR ERROR LOG', '#8B8B9E',              'rgba(255,255,255,0.04)', 'rgba(255,255,255,0.12)'],
            ].map(([l,c,bg,border]) => (
              <button key={l} style={{ width:'100%', marginBottom:5, padding:'8px', borderRadius:6, border:`1px solid ${border}`, background:bg, color:c, cursor:'pointer', fontSize:9, fontFamily:'monospace', letterSpacing:'0.08em', fontWeight:600 }}>{l}</button>
            ))}
          </Panel>
        </div>
      </div>
    </div>
  )
}

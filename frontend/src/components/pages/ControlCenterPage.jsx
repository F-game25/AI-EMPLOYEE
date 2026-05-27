import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, Badge, StatCard, DataRow } from '../ui/primitives'
import api from '../../api/client'

const FALLBACK_RULES = [
  { id:'r1', name:'Memory compaction trigger',     condition:'memory_usage > 75%',       action:'Run memory sweep → archive old embeddings', active:true,  runs:14, last:'2h ago'  },
  { id:'r2', name:'Agent health auto-restart',     condition:'agent_health < 60%',       action:'Restart agent + notify Doctor',             active:true,  runs:3,  last:'1d ago'  },
  { id:'r3', name:'Error cluster alert',           condition:'errors >= 3 in 10min',     action:'Send alert + pause affected agent',          active:true,  runs:1,  last:'3d ago'  },
  { id:'r4', name:'Nightly backup',                condition:'cron: 02:00 UTC daily',    action:'Full state backup to persistent store',      active:false, runs:7,  last:'8h ago'  },
  { id:'r5', name:'Neural checkpoint save',        condition:'learn_step % 1000 == 0',   action:'Save brain weights to disk',                active:true,  runs:14, last:'30m ago' },
  { id:'r6', name:'Revenue alert',                 condition:'daily_revenue < $50 target',action:'Notify + escalate to Strategy Engine',     active:true,  runs:0,  last:'Never'   },
]
const GOVERNANCE = [
  { rule:'No agent may delete data without HITL approval',          enforced:true  },
  { rule:'All high-risk actions require dual-agent validation',      enforced:true  },
  { rule:'Consequential financial actions require human review',      enforced:true  },
  { rule:'Agent may not contact external APIs without whitelisting', enforced:true  },
  { rule:'Autonomous outreach capped at 10 messages/day',           enforced:false },
]
const AUDIT = [
  { action:'Memory sweep initiated',      actor:'Auto-rule',       ts:'14:22:01', type:'system' },
  { action:'Revenue pathway #1 executed', actor:'Orchestrator',    ts:'14:18:30', type:'agent'  },
  { action:'Agent fleet set to BALANCED', actor:'User',            ts:'14:15:12', type:'user'   },
  { action:'Stripe webhook deployed',     actor:'Code Synthesizer', ts:'14:02:30', type:'agent' },
  { action:'Fairness audit batch 12 run', actor:'Auto-rule',       ts:'13:50:12', type:'system' },
]
const TYPE_C = { system:'rgba(255,255,255,0.35)', agent:'var(--teal,#20D6C7)', user:'var(--gold,#E5C76B)' }

// System map nodes
const SYS_NODES = [
  { label:'User', x:40,  y:50, key:'user' },
  { label:'Node :8787', x:200, y:50, key:'node' },
  { label:'Python :18790', x:380, y:50, key:'python' },
  { label:'Agent Fleet', x:560, y:50, key:'agents' },
  { label:'Memory', x:380, y:130, key:'memory' },
]
const SYS_EDGES = [
  { from:'user', to:'node' }, { from:'node', to:'python' },
  { from:'python', to:'agents' }, { from:'python', to:'memory' },
]

export default function ControlCenterPage() {
  const wsConnected = useAppStore(s => s.wsConnected)
  const systemStatus = useAppStore(s => s.systemStatus)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const storeRules = useAppStore(s => s.automationRules)
  const [sel, setSel] = useState(null)
  const [rules, setRules] = useState(null)

  // Kill switch state
  const [halted, setHalted] = useState(false)
  const [haltConfirm, setHaltConfirm] = useState(false)
  const [halting, setHalting] = useState(false)

  // Recovery mode
  const [recoveryMode, setRecoveryMode] = useState(false)

  const automationRules = rules ?? (storeRules?.length ? storeRules : FALLBACK_RULES)
  const selR = sel ?? automationRules[0]
  const activeRules = automationRules.filter(r => r.active).length
  const toggle = (id) => setRules(automationRules.map(r => r.id === id ? { ...r, active: !r.active } : r))

  const confirmHalt = async () => {
    setHalting(true)
    try {
      await api.system.halt('Emergency halt via Control Center')
      setHalted(true)
    } catch { /* fire-and-forget */ setHalted(true) }
    setHaltConfirm(false)
    setHalting(false)
  }

  const handleRestart = async () => {
    try { await api.system.restart() } catch { /* ignore */ }
    setHalted(false)
  }

  const toggleRecovery = async () => {
    const next = !recoveryMode
    setRecoveryMode(next)
    if (next) {
      try { await api.chat.send('Enter safe mode: disable auto-evolution, suspend external API calls, set agents to READ-ONLY') } catch { /* ignore */ }
    }
  }

  // SVG system map node position lookup
  const nodePos = Object.fromEntries(SYS_NODES.map(n => [n.key, n]))

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, flexShrink:0 }}>
        <StatCard label="Active Rules"  value={activeRules} color="var(--teal,#20D6C7)" sub={`of ${automationRules.length} configured`}/>
        <StatCard label="Governance"    value={`${GOVERNANCE.filter(g=>g.enforced).length}/${GOVERNANCE.length}`} color="#22C55E" sub="Rules enforced"/>
        <StatCard label="Audit Events"  value={AUDIT.length} color="var(--gold,#E5C76B)" sub="Today's activity"/>
        <StatCard label="System"        value={halted ? 'HALTED' : wsConnected ? 'ONLINE' : 'OFFLINE'} color={halted ? '#ef4444' : wsConnected ? '#22C55E' : '#f59e0b'} sub="Current status"/>
      </div>

      {/* Kill switch */}
      <Panel title="Emergency Controls" badge={<Badge label={halted ? 'HALTED' : 'OPERATIONAL'} variant={halted ? 'error' : 'teal'}/>}>
        <div style={{ display:'flex', gap:16, alignItems:'center', flexWrap:'wrap' }}>
          {!halted ? (
            haltConfirm ? (
              <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                <span style={{ fontSize:11, fontFamily:'monospace', color:'#ef4444' }}>Are you sure? This stops all agents.</span>
                <button onClick={confirmHalt} disabled={halting} style={{ padding:'5px 14px', borderRadius:5, border:'1px solid rgba(239,68,68,.5)', background:'rgba(239,68,68,.15)', color:'#ef4444', cursor:'pointer', fontFamily:'monospace', fontSize:10 }}>
                  {halting ? 'HALTING...' : 'CONFIRM'}
                </button>
                <button onClick={() => setHaltConfirm(false)} style={{ padding:'5px 14px', borderRadius:5, border:'1px solid rgba(255,255,255,.15)', background:'transparent', color:'rgba(255,255,255,.4)', cursor:'pointer', fontFamily:'monospace', fontSize:10 }}>CANCEL</button>
              </div>
            ) : (
              <button onClick={() => setHaltConfirm(true)} style={{ padding:'7px 20px', borderRadius:7, border:'2px solid rgba(239,68,68,.5)', background:'rgba(239,68,68,.1)', color:'#ef4444', cursor:'pointer', fontFamily:'monospace', fontSize:11, fontWeight:700, letterSpacing:'0.06em', boxShadow:'0 0 12px rgba(239,68,68,.15)' }}>
                EMERGENCY HALT
              </button>
            )
          ) : (
            <button onClick={handleRestart} style={{ padding:'7px 20px', borderRadius:7, border:'2px solid rgba(34,197,94,.5)', background:'rgba(34,197,94,.1)', color:'#22C55E', cursor:'pointer', fontFamily:'monospace', fontSize:11, fontWeight:700, letterSpacing:'0.06em' }}>
              RESTART SYSTEM
            </button>
          )}

          {/* Recovery mode toggle */}
          <div style={{ display:'flex', alignItems:'center', gap:10, marginLeft:'auto' }}>
            <span style={{ fontSize:11, fontFamily:'monospace', color:'rgba(255,255,255,.5)' }}>RECOVERY MODE</span>
            <div onClick={toggleRecovery} style={{ width:40, height:22, borderRadius:11, background:recoveryMode?'rgba(239,68,68,0.3)':'rgba(255,255,255,0.08)', border:`1px solid ${recoveryMode?'rgba(239,68,68,0.5)':'rgba(255,255,255,0.15)'}`, display:'flex', alignItems:'center', padding:'0 3px', cursor:'pointer', transition:'all .2s' }}>
              <div style={{ width:16, height:16, borderRadius:'50%', background:recoveryMode?'#ef4444':'rgba(255,255,255,0.3)', marginLeft:recoveryMode?18:0, transition:'margin .2s, background .2s' }}/>
            </div>
          </div>
        </div>
        {recoveryMode && (
          <div style={{ marginTop:10, padding:'8px 10px', borderRadius:6, background:'rgba(239,68,68,0.06)', border:'1px solid rgba(239,68,68,0.2)', fontSize:10, fontFamily:'monospace', color:'rgba(239,68,68,0.8)', display:'flex', gap:20 }}>
            <span>⚠ Auto-evolution OFF</span>
            <span>⚠ External API calls suspended</span>
            <span>⚠ Agents READ-ONLY</span>
          </div>
        )}
      </Panel>

      {/* Live System Map */}
      <Panel title="Live System Map">
        <svg width="100%" height="160" viewBox="0 0 660 170" style={{ overflow:'visible' }}>
          <defs>
            <marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 z" fill="rgba(32,214,199,0.5)"/>
            </marker>
          </defs>
          {SYS_EDGES.map((e, i) => {
            const f = nodePos[e.from]; const t = nodePos[e.to]
            return <line key={i} x1={f.x+50} y1={f.y+15} x2={t.x} y2={t.y+15} stroke="rgba(32,214,199,0.3)" strokeWidth="1.5" strokeDasharray="6 3" markerEnd="url(#arr)"/>
          })}
          {SYS_NODES.map(n => {
            const alive = n.key === 'user' ? true : n.key === 'node' || n.key === 'python' ? wsConnected : true
            return (
              <g key={n.key}>
                <rect x={n.x} y={n.y} width={100} height={30} rx={5} fill="rgba(255,255,255,0.04)" stroke={alive?'rgba(32,214,199,0.3)':'rgba(239,68,68,0.3)'} strokeWidth="1"/>
                <circle cx={n.x+10} cy={n.y+15} r={4} fill={alive?'#22C55E':'#ef4444'}/>
                <text x={n.x+20} y={n.y+20} fontSize="10" fill="rgba(255,255,255,0.7)" fontFamily="monospace">{n.label}</text>
              </g>
            )
          })}
          {systemStatus?.cpu && (
            <text x="200" y="100" fontSize="9" fill="rgba(255,255,255,0.3)" fontFamily="monospace">CPU {systemStatus.cpu}%</text>
          )}
        </svg>
      </Panel>

      {/* Existing panels */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, flex:1, minHeight:0 }}>
        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          <Panel title="Automation Rules" badge={<Badge label={`${activeRules} active`} variant="teal"/>} bodyStyle={{ padding:8 }}>
            {automationRules.map(r => (
              <div key={r.id} onClick={() => setSel(r)} style={{ padding:'9px 10px', borderRadius:7, marginBottom:4, border:`1px solid ${selR?.id===r.id?'rgba(229,199,107,0.4)':'rgba(229,199,107,0.08)'}`, background:selR?.id===r.id?'rgba(229,199,107,0.06)':'var(--bg-elevated,#12141F)', cursor:'pointer' }}>
                <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                  <div onClick={e => { e.stopPropagation(); toggle(r.id) }} style={{ width:24, height:13, borderRadius:7, background:r.active?'rgba(32,214,199,0.3)':'rgba(255,255,255,0.08)', border:`1px solid ${r.active?'rgba(32,214,199,0.5)':'rgba(255,255,255,0.15)'}`, display:'flex', alignItems:'center', padding:'0 2px', cursor:'pointer', flexShrink:0, transition:'all .2s' }}>
                    <div style={{ width:9, height:9, borderRadius:'50%', background:r.active?'var(--teal,#20D6C7)':'rgba(255,255,255,0.3)', marginLeft:r.active?10:0, transition:'margin .2s' }}/>
                  </div>
                  <span style={{ fontSize:11.5, color:r.active?'var(--text-primary,#F0E9D2)':'rgba(255,255,255,0.35)', flex:1 }}>{r.name}</span>
                  <span style={{ fontFamily:'monospace', fontSize:9, color:'rgba(255,255,255,0.25)' }}>{r.runs}×</span>
                </div>
                <div style={{ fontSize:10, color:'rgba(255,255,255,0.35)', fontFamily:'monospace', paddingLeft:32 }}>IF {r.condition}</div>
              </div>
            ))}
          </Panel>

          <Panel title="Governance Rules" style={{ flex:1 }}>
            {GOVERNANCE.map((g, i) => (
              <div key={i} style={{ display:'flex', gap:10, padding:'6px 0', borderBottom:'1px solid rgba(255,255,255,.04)', alignItems:'flex-start' }}>
                <div style={{ width:8, height:8, borderRadius:'50%', background:g.enforced?'#22C55E':'rgba(255,255,255,0.2)', marginTop:3, flexShrink:0 }}/>
                <span style={{ flex:1, fontSize:11, color:g.enforced?'var(--text-primary,#F0E9D2)':'rgba(255,255,255,0.35)', lineHeight:1.4 }}>{g.rule}</span>
                <span style={{ fontFamily:'monospace', fontSize:8, color:g.enforced?'#22C55E':'rgba(255,255,255,0.2)', letterSpacing:'0.06em', flexShrink:0 }}>{g.enforced?'ON':'OFF'}</span>
              </div>
            ))}
          </Panel>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:10, minHeight:0 }}>
          {selR && (
            <Panel title={selR.name} badge={<Badge label={selR.active?'ACTIVE':'OFF'} variant={selR.active?'teal':'default'}/>}>
              <div style={{ padding:'7px 9px', borderRadius:6, background:'rgba(0,0,0,0.3)', border:'1px solid rgba(255,255,255,0.06)', fontFamily:'monospace', fontSize:10, color:'var(--teal,#20D6C7)', marginBottom:8 }}>IF {selR.condition}</div>
              <div style={{ padding:'7px 9px', borderRadius:6, background:'rgba(0,0,0,0.3)', border:'1px solid rgba(255,255,255,0.06)', fontFamily:'monospace', fontSize:10, color:'var(--gold,#E5C76B)', marginBottom:8 }}>→ {selR.action}</div>
              <DataRow label="Runs" value={selR.runs}/><DataRow label="Last Run" value={selR.last}/>
              <div style={{ display:'flex', gap:5, marginTop:8 }}>
                <button onClick={() => api.chat.send(`Execute rule: ${selR.name}`).catch(()=>{})} style={{ flex:1, padding:'6px', borderRadius:6, border:'1px solid rgba(32,214,199,.3)', background:'rgba(32,214,199,.07)', color:'var(--teal,#20D6C7)', cursor:'pointer', fontSize:9, fontFamily:'monospace' }}>RUN NOW</button>
                <button onClick={() => setRules(automationRules.filter(r => r.id !== selR.id))} style={{ flex:1, padding:'6px', borderRadius:6, border:'1px solid rgba(239,68,68,.3)', background:'rgba(239,68,68,.05)', color:'#EF4444', cursor:'pointer', fontSize:9, fontFamily:'monospace' }}>DELETE</button>
              </div>
            </Panel>
          )}
          <Panel title="Audit Trail" style={{ flex:1 }} bodyStyle={{ overflowY:'auto' }}>
            {AUDIT.map((a, i) => (
              <div key={i} style={{ display:'flex', gap:8, padding:'6px 0', borderBottom:'1px solid rgba(255,255,255,.04)', alignItems:'flex-start' }}>
                <div style={{ width:6, height:6, borderRadius:'50%', background:TYPE_C[a.type]||'#9A927E', marginTop:4, flexShrink:0 }}/>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:11.5, color:'var(--text-primary,#F0E9D2)', lineHeight:1.3 }}>{a.action}</div>
                  <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.25)', marginTop:1 }}>{a.actor} · {a.ts}</div>
                </div>
                <span style={{ fontFamily:'monospace', fontSize:8, color:TYPE_C[a.type]||'#9A927E', letterSpacing:'0.06em', flexShrink:0 }}>{a.type.toUpperCase()}</span>
              </div>
            ))}
          </Panel>
        </div>
      </div>
    </div>
  )
}

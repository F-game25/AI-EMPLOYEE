import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, Badge, StatusDot, MiniBar } from '../ui/primitives'

const REVIEWS = [
  { from: 'Risk Auditor',     to: 'Code Synthesizer',   verdict: 'APPROVED', msg: 'Integration layer passes security audit. Token efficiency +14%.', score: 94 },
  { from: 'Fairness Monitor', to: 'Data Harvester',     verdict: 'FLAGGED',  msg: 'Dataset skew detected in 3 sources. Suggest rebalancing vendor weights.', score: 62 },
  { from: 'Strategy Engine',  to: 'Orchestrator Prime', verdict: 'APPROVED', msg: 'Revenue pathway rank matches market signals. Execute.', score: 91 },
  { from: 'Memory Indexer',   to: 'Learning Loop',      verdict: 'REVISE',   msg: 'Pattern 0xA4F duplicates 2 existing clusters. Merge recommended.', score: 71 },
  { from: 'Prompt Inspector', to: 'Voice Gateway',      verdict: 'APPROVED', msg: 'Response tone matches user preference vector.', score: 88 },
]
const VC = { APPROVED: '#22C55E', FLAGGED: '#F59E0B', REVISE: 'var(--bronze, #CD7F32)' }

function DR({ label, value, color = 'var(--text-primary, #F0E9D2)' }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-secondary, #9A927E)' }}>{label}</span>
      <span style={{ fontFamily: 'monospace', fontSize: 12, color, fontWeight: 500 }}>{value}</span>
    </div>
  )
}

const FALLBACK_AGENTS = [
  { id: 'a1', name: 'Orchestrator Prime', status: 'running', task: 'Coordinating agent fleet dispatch', health: 98 },
  { id: 'a2', name: 'Data Harvester',     status: 'running', task: 'Scraping market intelligence feeds', health: 87 },
  { id: 'a3', name: 'Code Synthesizer',   status: 'running', task: 'Generating API integration layer',  health: 91 },
  { id: 'a4', name: 'Memory Indexer',     status: 'busy',    task: 'Compressing knowledge store',       health: 74 },
  { id: 'a5', name: 'Hermes Relay',       status: 'running', task: 'Processing inbound requests',       health: 96 },
  { id: 'a6', name: 'Strategy Engine',    status: 'running', task: 'Analyzing revenue pathways',        health: 83 },
  { id: 'a7', name: 'Risk Auditor',       status: 'idle',    task: 'Standing by',                       health: 62 },
  { id: 'a8', name: 'Learning Loop',      status: 'running', task: 'Training on session data delta',    health: 89 },
]

export default function AgentsPage() {
  const storeAgents = useAppStore(s => s.agents)
  const setAgents   = useAppStore(s => s.setAgents)
  const agents = storeAgents.length ? storeAgents : FALLBACK_AGENTS

  const [sel, setSel]           = useState(null)
  const [botState, setBotState] = useState('AUTO')

  const selAgent = sel ?? agents[0]

  const applyFleet = (state) => {
    setBotState(state)
    setAgents(agents.map(a => ({ ...a, status: state === 'SLEEP' ? 'idle' : state === 'AWAKE' ? 'running' : a.status })))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>
      {/* Fleet Control bar */}
      <div style={{ padding: '10px 12px', borderRadius: 10, background: 'linear-gradient(180deg, rgba(229,199,107,0.06), transparent)', border: '1px solid rgba(229,199,107,0.2)', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace', letterSpacing: '0.12em', textTransform: 'uppercase' }}>FLEET CONTROL</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[['AWAKE', 'Start All', 'var(--gold-bright,#FFD97A)', '#1a1000'], ['AUTO', 'Auto', 'var(--teal,#20D6C7)', '#001a18'], ['SLEEP', 'Sleep Bots', '#8B8B9E', '#fff']].map(([k, l, bg, fg]) => (
            <button key={k} onClick={() => applyFleet(k)} style={{ padding: '7px 15px', borderRadius: 7, border: botState === k ? `1px solid ${bg}` : '1px solid transparent', background: botState === k ? bg : 'rgba(255,255,255,0.04)', color: botState === k ? fg : 'var(--text-secondary,#9A927E)', cursor: 'pointer', fontSize: 10, fontFamily: 'monospace', letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600, boxShadow: botState === k ? `0 0 14px ${bg}55` : 'none' }}>{l}</button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 14, fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.08em' }}>
          <span>LIVE <span style={{ color: 'var(--teal,#20D6C7)' }}>{agents.filter(a => a.status === 'running').length}</span></span>
          <span>BUSY <span style={{ color: 'var(--gold-bright,#FFD97A)' }}>{agents.filter(a => a.status === 'busy').length}</span></span>
          <span>IDLE <span style={{ color: '#8B8B9E' }}>{agents.filter(a => a.status === 'idle').length}</span></span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr 1fr', gap: 10, flex: 1, minHeight: 0 }}>
        {/* Fleet Roster */}
        <Panel title="Fleet Roster" bodyStyle={{ padding: 8 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {agents.map(a => (
              <div key={a.id} onClick={() => setSel(a)} style={{ padding: '7px 10px', borderRadius: 7, border: `1px solid ${selAgent?.id === a.id ? 'rgba(229,199,107,0.4)' : 'rgba(229,199,107,0.08)'}`, background: selAgent?.id === a.id ? 'rgba(229,199,107,0.07)' : 'var(--bg-elevated,#12141F)', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <StatusDot status={a.status} />
                  <span style={{ fontSize: 11.5, color: 'var(--text-primary,#F0E9D2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                  <span style={{ fontFamily: 'monospace', fontSize: 10, color: (a.health ?? 80) > 80 ? 'var(--teal,#20D6C7)' : (a.health ?? 80) > 50 ? 'var(--gold-bright,#FFD97A)' : '#EF4444' }}>{a.health ?? 80}%</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        {/* Peer Review Feed */}
        <Panel title="Peer Review Feed" badge={<Badge label="SCI-FI LIVE" variant="teal" />} bodyStyle={{ padding: 12 }}>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace', letterSpacing: '0.08em', marginBottom: 10, textTransform: 'uppercase' }}>Agents auditing each other in real time</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {REVIEWS.map((r, i) => (
              <div key={i} style={{ padding: '10px 12px', borderRadius: 8, border: `1px solid ${VC[r.verdict]}33`, background: `linear-gradient(90deg, ${VC[r.verdict]}0A, transparent)`, position: 'relative', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 2, background: VC[r.verdict], boxShadow: `0 0 10px ${VC[r.verdict]}` }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, fontFamily: 'monospace', color: 'var(--text-secondary,#9A927E)', marginBottom: 5 }}>
                  <span style={{ color: 'var(--gold-bright,#FFD97A)' }}>{r.from}</span>
                  <svg width="12" height="6" viewBox="0 0 12 6" fill="none"><path d="M0 3 L11 3 M8 0 L11 3 L8 6" stroke={VC[r.verdict]} strokeWidth="1" /></svg>
                  <span style={{ color: 'var(--teal,#20D6C7)' }}>{r.to}</span>
                  <span style={{ flex: 1 }} />
                  <span style={{ color: VC[r.verdict], fontWeight: 600, letterSpacing: '0.08em' }}>{r.verdict} · {r.score}</span>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-primary,#F0E9D2)', lineHeight: 1.5 }}>{r.msg}</div>
              </div>
            ))}
          </div>
        </Panel>

        {/* Detail + Collaboration Map */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
          {selAgent && (
            <Panel title={selAgent.name} badge={<Badge label={selAgent.status} variant={selAgent.status === 'running' ? 'teal' : selAgent.status === 'busy' ? 'gold' : 'default'} />}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 12 }}>
                <div><DR label="Health" value={`${selAgent.health ?? 80}%`} color={(selAgent.health ?? 80) > 80 ? '#22C55E' : '#F59E0B'} /><DR label="Tasks" value="847" /><DR label="Cost/task" value="$0.012" /></div>
                <div><DR label="Success" value="98.9%" color="#22C55E" /><DR label="Latency" value="320ms" /><DR label="Errors" value="3" color="#EF4444" /></div>
              </div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace', letterSpacing: '0.08em', marginBottom: 5 }}>FAILURE DEBUGGER</div>
              <div style={{ padding: 9, borderRadius: 7, background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.18)', fontSize: 11, color: 'var(--text-secondary,#9A927E)', lineHeight: 1.5 }}>
                <div style={{ color: '#EF4444', fontWeight: 600, marginBottom: 3, fontSize: 10 }}>LAST FAILURE: prompt → logic → memory</div>
                Prompt depth exceeded context window at step 4. Recommend prompt compression + reindex.
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                <button style={{ flex: 1, padding: 7, borderRadius: 6, border: '1px solid rgba(32,214,199,.3)', background: 'rgba(32,214,199,.07)', color: 'var(--teal,#20D6C7)', cursor: 'pointer', fontSize: 10 }}>RESTART</button>
                <button style={{ flex: 1, padding: 7, borderRadius: 6, border: '1px solid rgba(229,199,107,.3)', background: 'rgba(229,199,107,.07)', color: 'var(--gold-bright,#FFD97A)', cursor: 'pointer', fontSize: 10 }}>TUNE</button>
                <button style={{ flex: 1, padding: 7, borderRadius: 6, border: '1px solid rgba(239,68,68,.3)', background: 'rgba(239,68,68,.05)', color: '#EF4444', cursor: 'pointer', fontSize: 10 }}>HALT</button>
              </div>
            </Panel>
          )}
          <Panel title="Collaboration Map" style={{ flex: 1 }} bodyStyle={{ padding: 0, display: 'flex' }}>
            <svg viewBox="0 0 280 200" style={{ width: '100%', height: '100%' }}>
              <defs><radialGradient id="ngx"><stop offset="0%" stopColor="#FFD97A" /><stop offset="100%" stopColor="#CD7F32" /></radialGradient></defs>
              {[[140,110,50,100,95,175],[140,110,230,60,210,180]].map((c,i)=><path key={i} d={`M${c[0]} ${c[1]} Q ${c[2]} ${c[3]} ${c[4]} ${c[5]}`} stroke="rgba(229,199,107,0.3)" strokeWidth="1" fill="none"/>)}
              <line x1="140" y1="110" x2="50"  y2="100" stroke="rgba(32,214,199,0.3)" strokeWidth="1"/>
              <line x1="140" y1="110" x2="230" y2="60"  stroke="rgba(32,214,199,0.3)" strokeWidth="1"/>
              <line x1="140" y1="110" x2="95"  y2="175" stroke="rgba(32,214,199,0.3)" strokeWidth="1"/>
              <line x1="140" y1="110" x2="210" y2="180" stroke="rgba(32,214,199,0.3)" strokeWidth="1"/>
              {[[140,110,'Prime',14],[50,100,'Harvest',9],[230,60,'Strategy',9],[95,175,'Memory',9],[210,180,'Risk',9]].map((n,i)=>(
                <g key={i}><circle cx={n[0]} cy={n[1]} r={n[3]} fill="url(#ngx)" opacity="0.9"/><circle cx={n[0]} cy={n[1]} r={n[3]+4} fill="none" stroke="rgba(229,199,107,0.3)" strokeWidth="1"/><text x={n[0]} y={n[1]+n[3]+14} textAnchor="middle" fontSize="10" fill="#9A927E" fontFamily="monospace">{n[2]}</text></g>
              ))}
            </svg>
          </Panel>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Panel, Badge, StatCard } from '../ui/primitives'
import api from '../../api/client'

const LEVEL_LABEL = (lvl) => {
  if (lvl >= 90) return { text: 'EXPERT',        color: 'var(--teal,#20D6C7)',  glow: '0 0 8px rgba(32,214,199,.5)' }
  if (lvl >= 70) return { text: 'ADVANCED',       color: 'var(--gold,#E5C76B)',  glow: 'none' }
  if (lvl >= 40) return { text: 'INTERMEDIATE',   color: 'var(--bronze,#CD7F32)',glow: 'none' }
  return              { text: 'NOVICE',           color: 'rgba(255,255,255,.3)', glow: 'none' }
}

const INITIAL_SKILLS = [
  { cat:'Reasoning', items:[{n:'Causal Inference',lvl:91},{n:'Multi-step Planning',lvl:87},{n:'Counterfactual Analysis',lvl:74}] },
  { cat:'Code',      items:[{n:'Python Generation',lvl:95},{n:'API Integration',lvl:88},{n:'Test Writing',lvl:72}] },
  { cat:'Research',  items:[{n:'Web Scraping',lvl:93},{n:'Data Synthesis',lvl:86},{n:'Citation Verification',lvl:61}] },
  { cat:'Comms',     items:[{n:'Email Drafting',lvl:89},{n:'Report Writing',lvl:78},{n:'Negotiation Prompts',lvl:55}] },
  { cat:'Finance',   items:[{n:'Revenue Analysis',lvl:82},{n:'Cost Optimization',lvl:70},{n:'Market Research',lvl:76}] },
]
const QUEUE = [
  { task:'Learn Rust code generation',      priority:'HIGH', eta:'~3 sessions' },
  { task:'Improve negotiation success rate', priority:'MED',  eta:'~5 sessions' },
  { task:'Expand finance domain knowledge',  priority:'MED',  eta:'~4 sessions' },
  { task:'Strengthen citation accuracy',     priority:'LOW',  eta:'~6 sessions' },
]
const IMPROVEMENTS = [
  { skill:'Python Generation', delta:'+2.1%', ts:'2h ago', c:'#22C55E' },
  { skill:'Causal Inference',  delta:'+1.4%', ts:'5h ago', c:'#22C55E' },
  { skill:'Market Research',   delta:'+3.2%', ts:'1d ago', c:'#22C55E' },
  { skill:'API Integration',   delta:'+0.8%', ts:'1d ago', c:'#22C55E' },
]

export default function LearningLadderPage() {
  const [skills, setSkills] = useState(INITIAL_SKILLS)
  const [topic, setTopic] = useState('')
  const [teaching, setTeaching] = useState(false)
  const [teachResult, setTeachResult] = useState(null)

  const allItems = skills.flatMap(s => s.items)
  const avgMastery = Math.round(allItems.reduce((a, b) => a + b.lvl, 0) / allItems.length)

  const handleTeach = async () => {
    if (!topic.trim()) return
    setTeaching(true); setTeachResult(null)
    // Optimistically add to queue
    const newSkill = { n: topic.trim(), lvl: 0, status: 'QUEUED' }
    setSkills(prev => {
      const updated = prev.map(cat => cat.cat === 'Research'
        ? { ...cat, items: [...cat.items, newSkill] }
        : cat
      )
      return updated
    })
    try {
      await api.chat.send(`Learn topic: ${topic.trim()}`)
      setTeachResult({ ok: true, msg: `Teaching initiated: "${topic.trim()}"` })
      setTopic('')
    } catch {
      setTeachResult({ ok: false, msg: 'Failed to initiate learning task' })
    } finally {
      setTeaching(false)
    }
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      {/* Stats */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10 }}>
        <StatCard label="Avg Mastery"    value={`${avgMastery}%`}     color="var(--gold,#E5C76B)" sub="Across all skills"/>
        <StatCard label="Skills Tracked" value={allItems.length}      color="var(--teal,#20D6C7)" sub={`${skills.length} categories`}/>
        <StatCard label="Recent Gains"   value={IMPROVEMENTS.length}  color="#22C55E" sub="Skills improved this week"/>
      </div>

      {/* Topic Input */}
      <Panel title="Teach New Topic">
        <div style={{ display:'flex', gap:8 }}>
          <input
            value={topic}
            onChange={e => setTopic(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleTeach()}
            placeholder="Enter learning topic (e.g. 'Kubernetes deployment strategies')..."
            style={{ flex:1, padding:'8px 12px', borderRadius:6, background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.1)', color:'var(--text-primary,#F0E9D2)', fontFamily:'monospace', fontSize:12 }}
          />
          <button onClick={handleTeach} disabled={teaching || !topic.trim()} style={{
            padding:'8px 20px', borderRadius:6, fontFamily:'monospace', fontSize:11, fontWeight:600,
            background: teaching ? 'rgba(229,199,107,0.05)' : 'rgba(229,199,107,0.15)',
            border:'1px solid rgba(229,199,107,0.4)', color:'var(--gold,#E5C76B)',
            cursor: teaching ? 'wait' : 'pointer', whiteSpace:'nowrap',
          }}>
            {teaching ? 'TEACHING...' : 'TEACH SYSTEM'}
          </button>
        </div>
        {teachResult && (
          <div style={{ marginTop:8, padding:'6px 10px', borderRadius:5, fontSize:11, fontFamily:'monospace', background: teachResult.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', border:`1px solid ${teachResult.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`, color: teachResult.ok ? '#22C55E' : '#ef4444' }}>
            {teachResult.ok ? '✓ ' : '✗ '}{teachResult.msg}
          </div>
        )}
      </Panel>

      {/* Main grid */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:10, flex:1, minHeight:0 }}>
        <Panel title="Skill Mastery" badge={<Badge label="Live" variant="green"/>} bodyStyle={{ overflowY:'auto' }}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {skills.map(cat => (
              <div key={cat.cat}>
                <div style={{ fontSize:10, fontFamily:'monospace', letterSpacing:'0.1em', textTransform:'uppercase', color:'rgba(255,255,255,0.35)', marginBottom:8 }}>{cat.cat}</div>
                <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                  {cat.items.map(sk => {
                    const lvlInfo = LEVEL_LABEL(sk.lvl)
                    return (
                      <div key={sk.n} style={{ display:'flex', alignItems:'center', gap:10 }}>
                        <span style={{ fontSize:12, color:'var(--text-secondary,#9A927E)', width:180, flexShrink:0 }}>{sk.n}</span>
                        <div style={{ flex:1, height:6, background:'rgba(255,255,255,.06)', borderRadius:3, overflow:'hidden' }}>
                          <div style={{ width:`${sk.lvl}%`, height:'100%', borderRadius:3, transition:'width .5s', background:sk.lvl>=90?'var(--teal,#20D6C7)':sk.lvl>=70?'var(--gold,#E5C76B)':sk.lvl>=40?'var(--bronze,#CD7F32)':'rgba(255,255,255,.2)', boxShadow:lvlInfo.glow }}/>
                        </div>
                        <span style={{ fontFamily:'monospace', fontSize:11, color: lvlInfo.color, width:34, textAlign:'right', flexShrink:0 }}>{sk.lvl}%</span>
                        <span style={{ fontSize:8, fontFamily:'monospace', letterSpacing:'0.06em', color: lvlInfo.color, width:72, textAlign:'right', flexShrink:0, textShadow: lvlInfo.glow !== 'none' ? lvlInfo.glow : 'none' }}>{sk.status === 'QUEUED' ? 'QUEUED' : lvlInfo.text}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          <Panel title="Learning Queue">
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {QUEUE.map((q,i) => (
                <div key={i} style={{ padding:'9px 10px', borderRadius:8, border:'1px solid rgba(229,199,107,0.08)', background:'var(--bg-elevated,#12141F)' }}>
                  <div style={{ fontSize:12, color:'var(--text-primary,#F0E9D2)', marginBottom:5 }}>{q.task}</div>
                  <div style={{ display:'flex', justifyContent:'space-between' }}>
                    <Badge label={q.priority} variant={q.priority==='HIGH'?'error':q.priority==='MED'?'warn':'default'}/>
                    <span style={{ fontSize:11, color:'rgba(255,255,255,0.35)', fontFamily:'monospace' }}>{q.eta}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Recent Improvements" style={{ flex:1 }}>
            {IMPROVEMENTS.map((r,i) => (
              <div key={i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'7px 0', borderBottom:'1px solid rgba(255,255,255,.04)' }}>
                <span style={{ fontSize:12, color:'var(--text-secondary,#9A927E)' }}>{r.skill}</span>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ fontFamily:'monospace', fontSize:12, color:r.c, fontWeight:600 }}>{r.delta}</span>
                  <span style={{ fontSize:11, color:'rgba(255,255,255,0.35)' }}>{r.ts}</span>
                </div>
              </div>
            ))}
          </Panel>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Panel, KPITile, StatusPill, HexButton, SectionLabel, LiveBadge } from '../nexus-ui'
import api from '../../api/client'
import './LearningLadderPage.css'

const LEVEL_LABEL = (lvl) => {
  if (lvl >= 90) return { text: 'EXPERT',        color: '#20D6C7',  glow: '0 0 8px rgba(32,214,199,.5)' }
  if (lvl >= 70) return { text: 'ADVANCED',       color: '#E5C76B',  glow: 'none' }
  if (lvl >= 40) return { text: 'INTERMEDIATE',   color: '#CD7F32',glow: 'none' }
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
    <div className="ll-page">
      <div className="ll-kpi-row">
        <KPITile label="Avg Mastery" value={`${avgMastery}%`} sub="Across all skills" icon="📊" iconTone="gold" accent />
        <KPITile label="Skills Tracked" value={allItems.length} sub={`${skills.length} categories`} icon="🎯" iconTone="cool" />
        <KPITile label="Recent Gains" value={IMPROVEMENTS.length} sub="Skills improved this week" icon="📈" iconTone="success" />
      </div>

      <Panel title="Teach New Topic" tone="gold">
        <div className="ll-teach-row">
          <input
            value={topic}
            onChange={e => setTopic(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleTeach()}
            placeholder="Enter learning topic (e.g. 'Kubernetes deployment strategies')..."
            className="ll-teach-input"
          />
          <HexButton onClick={handleTeach} disabled={teaching || !topic.trim()} variant="primary" tone="gold" size="md">
            {teaching ? 'TEACHING...' : 'TEACH SYSTEM'}
          </HexButton>
        </div>
        {teachResult && (
          <div className={`ll-teach-result ${teachResult.ok ? 'll-teach-result--ok' : 'll-teach-result--err'}`}>
            {teachResult.ok ? '✓ ' : '✗ '}{teachResult.msg}
          </div>
        )}
      </Panel>

      <div className="ll-main-grid">
        <Panel title="Skill Mastery" tone="gold" actions={<LiveBadge variant="live" />}>
          <div className="ll-skill-grid">
            {skills.map(cat => (
              <div key={cat.cat}>
                <SectionLabel tone="muted">{cat.cat}</SectionLabel>
                <div className="ll-skill-list">
                  {cat.items.map(sk => {
                    const lvlInfo = LEVEL_LABEL(sk.lvl)
                    return (
                      <div key={sk.n} className="ll-skill-item">
                        <span className="ll-skill-name">{sk.n}</span>
                        <div className="ll-skill-bar">
                          <div
                            className="ll-skill-bar-fill"
                            style={{
                              width: `${sk.lvl}%`,
                              background: lvlInfo.color,
                              boxShadow: lvlInfo.glow !== 'none' ? lvlInfo.glow : 'none'
                            }}
                          />
                        </div>
                        <span className="ll-skill-level" style={{ color: lvlInfo.color }}>{sk.lvl}%</span>
                        <span className="ll-skill-badge" style={{ color: lvlInfo.color, textShadow: lvlInfo.glow !== 'none' ? lvlInfo.glow : 'none' }}>
                          {sk.status === 'QUEUED' ? 'QUEUED' : lvlInfo.text}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <div className="ll-right">
          <Panel title="Learning Queue" tone="gold">
            <div className="ll-queue-list">
              {QUEUE.map((q, i) => (
                <div key={i} className="ll-queue-item">
                  <div className="ll-queue-task">{q.task}</div>
                  <div className="ll-queue-meta">
                    <StatusPill
                      label={q.priority}
                      tone={q.priority === 'HIGH' ? 'alert' : q.priority === 'MED' ? 'warning' : 'cool'}
                      size="sm"
                      dot={false}
                    />
                    <span className="ll-queue-eta">{q.eta}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Recent Improvements" tone="gold" style={{ flex: 1 }}>
            <div className="ll-improvements-list">
              {IMPROVEMENTS.map((r, i) => (
                <div key={i} className="ll-improvement-row">
                  <span className="ll-improvement-skill">{r.skill}</span>
                  <div className="ll-improvement-value">
                    <span className="ll-improvement-delta" style={{ color: r.c }}>{r.delta}</span>
                    <span className="ll-improvement-ts">{r.ts}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

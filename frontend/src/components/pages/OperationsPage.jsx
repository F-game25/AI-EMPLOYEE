import { useState } from 'react'
import { Panel, StatusPill, SectionLabel, HexButton } from '../nexus-ui'
import { MiniBar } from '../ui/primitives'
import './OperationsPage.css'

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

const COLS = [
  { id: 'todo',    label: 'Queued',       tone: 'idle',    icon: '◌', barColor: 'var(--nx-text-dim)'  },
  { id: 'running', label: 'In Progress',  tone: 'cool',    icon: '◐', barColor: 'var(--nx-info)'      },
  { id: 'review',  label: 'Review',       tone: 'gold',    icon: '◆', barColor: 'var(--nx-gold)'      },
  { id: 'done',    label: 'Completed',    tone: 'success', icon: '✓', barColor: 'var(--nx-success)'   },
]

const ERRC = [
  { cluster:'API timeout (vendor-x)', n:14, trend:'up'   },
  { cluster:'Token limit exceeded',   n:8,  trend:'flat' },
  { cluster:'JSON parse failure',     n:3,  trend:'down' },
]

const AUTO = [
  { rule:'If memory > 75% → run sweep',             active:true  },
  { rule:'If agent health < 60% → restart',         active:true  },
  { rule:'On failure cluster (≥3) → notify Doctor', active:true  },
  { rule:'Nightly (02:00 UTC) → full backup',       active:false },
]

const OPT = [
  { sug:'Batch memory writes every 5s → -38% write load', gain:'-38%'  },
  { sug:'Route quick queries to Haiku → -$0.08/task',     gain:'-$0.08' },
  { sug:'Pre-warm vector cache on idle → -42% latency',   gain:'-42%'  },
]

const PRIORITY_TONE = { HIGH: 'alert', MED: 'gold', LOW: 'idle' }

export default function OperationsPage() {
  const [sel, setSel] = useState(null)

  return (
    <div className="ops-grid">
      {/* Kanban */}
      <div className="ops-kanban">
        {COLS.map(col => {
          const items = TASKS.filter(t => t.col === col.id)
          return (
            <Panel
              key={col.id}
              icon={col.icon}
              title={col.label}
              actions={<StatusPill tone={col.tone} label={String(items.length)} dot={false} size="sm" />}
              tight
              hover
            >
              <div className="ops-col">
                {items.map(t => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setSel(t)}
                    className={`ops-card ${sel?.id === t.id ? 'is-selected' : ''}`}
                  >
                    <div className="ops-card__title">{t.title}</div>
                    {t.progress > 0 && t.progress < 100 && (
                      <MiniBar value={t.progress} color={col.barColor} style={{ marginBottom: 6 }} />
                    )}
                    <div className="ops-card__meta">
                      <span className="ops-card__agent">{t.agent}</span>
                      <StatusPill tone={PRIORITY_TONE[t.priority]} label={t.priority} dot={false} size="sm" />
                    </div>
                  </button>
                ))}
                {items.length === 0 && <div className="ops-empty">—</div>}
              </div>
            </Panel>
          )
        })}
      </div>

      {/* Bottom row: Detail · Errors · Automation */}
      <div className="ops-bottom">
        <Panel
          icon="◈"
          title={sel ? 'Task Detail' : 'Task Detail'}
          actions={sel && (
            <>
              <StatusPill tone={COLS.find(c => c.id === sel.col)?.tone || 'idle'} label={sel.col.toUpperCase()} dot={false} size="sm" />
              <StatusPill tone={PRIORITY_TONE[sel.priority]} label={sel.priority} size="sm" />
            </>
          )}
        >
          {sel ? (
            <div className="ops-detail">
              <div className="ops-detail__head">
                <div className="ops-detail__title">{sel.title}</div>
                <div className="ops-detail__sub">Started {sel.started} · {sel.agent}</div>
              </div>
              <DetailLine prefix="WHAT" tone="gold"    text={sel.title} />
              <DetailLine prefix="WHY"  tone="cool"    text={sel.why} />
              <DetailLine prefix="DID"  tone="bronze"  text={sel.did} />
              <DetailLine prefix="NEXT" tone="muted"   text={sel.next} />
              {sel.col === 'review' && (
                <div className="ops-detail__cta">
                  <HexButton variant="primary" size="sm" icon="✓">Approve</HexButton>
                  <HexButton variant="outline" size="sm" tone="alert" icon="✗">Reject</HexButton>
                </div>
              )}
            </div>
          ) : (
            <div className="ops-empty ops-empty--center">Click a task card to see details</div>
          )}
        </Panel>

        <Panel icon="!" title="Error Clustering">
          <div className="ops-err">
            {ERRC.map(e => (
              <div key={e.cluster} className="ops-err__row">
                <span className="ops-err__name">{e.cluster}</span>
                <span className={`ops-err__count ops-err__count--${e.trend}`}>{e.n}</span>
                <span className={`ops-err__arrow ops-err__arrow--${e.trend}`}>
                  {e.trend === 'up' ? '↑' : e.trend === 'down' ? '↓' : '→'}
                </span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel icon="⚙" title="Automation + Optimizer">
          <SectionLabel size="sm" tone="dim">Rules</SectionLabel>
          <div className="ops-rules">
            {AUTO.map(r => (
              <div key={r.rule} className={`ops-rule ${r.active ? 'is-on' : 'is-off'}`}>
                <span className="ops-rule__text">{r.rule}</span>
                <StatusPill
                  tone={r.active ? 'success' : 'idle'}
                  label={r.active ? 'ON' : 'OFF'}
                  dot={false}
                  size="sm"
                />
              </div>
            ))}
          </div>
          <SectionLabel size="sm" tone="dim" rule>Optimizer</SectionLabel>
          <div className="ops-opt">
            {OPT.map(o => (
              <div key={o.sug} className="ops-opt__row">
                <span className="ops-opt__gain">{o.gain}</span>
                <span className="ops-opt__sug">{o.sug}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}

function DetailLine({ prefix, tone, text }) {
  return (
    <div className="ops-detail__line">
      <span className={`ops-detail__prefix ops-detail__prefix--${tone}`}>{prefix} →</span>
      <span className="ops-detail__text">{text}</span>
    </div>
  )
}

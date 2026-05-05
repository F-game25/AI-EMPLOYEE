import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, KPITile, StatusPill, HexButton, Sparkline } from '../nexus-ui'
import './PromptInspectorPage.css'

const FALLBACK_TRACES = [
  { id:'pt-001', agent:'Orchestrator Prime', prompt:'Analyze revenue pathways for Q2 — rank by ROI, identify top 3 with rationale.', output:'Ranked 12 pathways. Top 3: SaaS upsell (3.2×), API licensing (2.8×), Data resale (1.9×).', tokens:{ in:284, out:412 }, latency:'1.4s', score:94, flags:[] },
  { id:'pt-002', agent:'Data Harvester',     prompt:'Scrape competitor pricing from 12 SaaS vendors. Return structured JSON.',           output:'{"vendors":12,"records":2413,"avg_price":"$89/mo","range":"$29-$499"}',             tokens:{ in:156, out:320 }, latency:'3.8s', score:88, flags:[] },
  { id:'pt-003', agent:'Strategy Engine',    prompt:'Compare our pricing to competitor data. Suggest 3 tactical moves.',                  output:'1. Launch $49 tier. 2. Bundle API access. 3. Annual discount 20%.',                  tokens:{ in:490, out:280 }, latency:'2.1s', score:79, flags:['generic_output'] },
  { id:'pt-004', agent:'Code Synthesizer',   prompt:'Generate Stripe webhook handler for subscription events.',                            output:'[48 lines of Python — 4 routes, auth, retry, idempotency]',                         tokens:{ in:320, out:890 }, latency:'4.2s', score:97, flags:[] },
  { id:'pt-005', agent:'Memory Indexer',     prompt:'',                                                                                    output:'',                                                                                   tokens:{ in:0,   out:0   }, latency:'—',    score:0,  flags:['empty_prompt','empty_output'] },
]
const FLAG_C = { empty_prompt:'#EF4444', empty_output:'#EF4444', generic_output:'#F59E0B', missing_context:'#F59E0B', error:'#EF4444' }
const QUALITY = [['Structure','94','#E5C76B'],['Clarity','88','#60a5fa'],['Specificity','82','#22C55E'],['Token Eff.','91','#8B8B9E']]
const SPARKLINE_DATA = [78, 80, 82, 81, 84, 86, 87, 88, 90, 92, 94]

export default function PromptInspectorPage() {
  const promptTraces = useAppStore(s => s.promptTraces)
  const [sel, setSel] = useState(null)
  const [editText, setEditText] = useState('')

  const traces = (promptTraces?.length ? promptTraces : FALLBACK_TRACES)
  const selT = sel ?? traces[0]

  const avgScore = Math.round(traces.filter(t=>t.score>0).reduce((a,t)=>a+t.score,0) / traces.filter(t=>t.score>0).length || 0)
  const flagged = traces.filter(t => t.flags?.length > 0).length
  const totalTok = traces.reduce((a,t) => a + (t.tokens?.in||0) + (t.tokens?.out||0), 0)

  return (
    <div className="pip-page">
      <div className="pip-kpi-row">
        <KPITile label="Avg Quality" value={`${avgScore}/100`} sub="Across all traces" icon="⭐" iconTone="gold" accent />
        <KPITile label="Prompts Today" value={traces.length} sub="Traced executions" icon="📋" iconTone="cool" />
        <KPITile label="Flagged" value={flagged} sub="Needs review" icon="⚠" iconTone={flagged > 0 ? 'alert' : 'success'} />
        <KPITile label="Total Tokens" value={totalTok.toLocaleString()} sub="In + out" icon="🔢" iconTone="purple" />
      </div>

      <div className="pip-main-grid">
        <div className="pip-left">
          <Panel title="Prompt Traces" tone="gold" actions={<StatusPill label="LIVE INSPECTION" tone="cool" size="sm" dot={true} />}>
            <div className="pip-trace-list">
              {traces.map(t => (
                <div
                  key={t.id}
                  onClick={() => { setSel(t); setEditText(t.prompt) }}
                  className={`pip-trace-item ${selT?.id === t.id ? 'pip-trace-item--selected' : ''}`}
                >
                  <div className="pip-trace-header">
                    <span className="pip-trace-agent">{t.agent}</span>
                    {t.flags?.length > 0 && t.flags.map(f => (
                      <StatusPill key={f} label={f.replace('_', ' ')} tone={f.includes('error') || f.includes('empty') ? 'alert' : 'warn'} size="xs" />
                    ))}
                    <span className={`pip-trace-score ${t.score > 85 ? 'pip-trace-score--high' : t.score > 60 ? 'pip-trace-score--med' : 'pip-trace-score--low'}`}>
                      {t.score || '—'}
                    </span>
                  </div>
                  <div className="pip-trace-prompt">{t.prompt || <span className="pip-trace-empty">empty prompt</span>}</div>
                  <div className="pip-trace-meta">
                    <span>IN: {t.tokens?.in||0}</span>
                    <span>OUT: {t.tokens?.out||0}</span>
                    <span>⏱ {t.latency}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Prompt Editor" tone="gold" style={{ flex: 1 }}>
            <div className="pip-editor-label">EDIT · RE-RUN · INJECT LIVE</div>
            <textarea
              value={editText}
              onChange={e => setEditText(e.target.value)}
              placeholder="Select a trace to edit its prompt…"
              className="pip-editor-textarea"
            />
            <div className="pip-editor-buttons">
              <HexButton variant="primary" tone="gold" size="md">RE-RUN</HexButton>
              <HexButton variant="outline" tone="cool" size="md">INJECT</HexButton>
              <HexButton variant="ghost" size="md">CLEAR</HexButton>
            </div>
          </Panel>
        </div>

        <div className="pip-right">
          {selT && (
            <Panel title="Trace Detail" tone="gold" actions={<StatusPill label={selT.flags?.length > 0 ? 'FLAGGED' : 'CLEAN'} tone={selT.flags?.length > 0 ? 'alert' : 'success'} size="sm" dot={false} />}>
              <div className="pip-detail-rows">
                <div className="pip-detail-row">
                  <span className="pip-detail-label">Agent</span>
                  <span className="pip-detail-value pip-detail-value--teal">{selT.agent}</span>
                </div>
                <div className="pip-detail-row">
                  <span className="pip-detail-label">Score</span>
                  <span className="pip-detail-value" style={{ color: selT.score > 85 ? '#22C55E' : selT.score > 60 ? '#E5C76B' : '#EF4444' }}>{selT.score || '—'}</span>
                </div>
                <div className="pip-detail-row">
                  <span className="pip-detail-label">Latency</span>
                  <span className="pip-detail-value">{selT.latency}</span>
                </div>
                <div className="pip-detail-row">
                  <span className="pip-detail-label">Tokens In</span>
                  <span className="pip-detail-value">{(selT.tokens?.in||0).toLocaleString()}</span>
                </div>
                <div className="pip-detail-row">
                  <span className="pip-detail-label">Tokens Out</span>
                  <span className="pip-detail-value">{(selT.tokens?.out||0).toLocaleString()}</span>
                </div>
              </div>
              {selT.flags?.length > 0 && (
                <div className="pip-detail-flags">
                  <div className="pip-flags-label">FLAGS</div>
                  <div className="pip-flags-grid">
                    {selT.flags.map(f => (
                      <StatusPill key={f} label={f.replace('_', ' ')} tone={f.includes('error') || f.includes('empty') ? 'alert' : 'warn'} size="xs" />
                    ))}
                  </div>
                </div>
              )}
              {selT.output && (
                <div className="pip-detail-output">
                  <div className="pip-output-label">OUTPUT</div>
                  <pre className="pip-output-block">{selT.output.slice(0, 200)}{selT.output.length > 200 ? '…' : ''}</pre>
                </div>
              )}
            </Panel>
          )}

          <Panel title="Quality Analysis" tone="gold">
            <div className="pip-quality-items">
              {QUALITY.map(([label, value, color]) => (
                <div key={label} className="pip-quality-item">
                  <div className="pip-quality-header">
                    <span>{label}</span>
                    <span>{value}</span>
                  </div>
                  <div className="pip-quality-bar">
                    <div className="pip-quality-bar-fill" style={{ width: `${value}%`, background: color }} />
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Quality Trend" tone="gold" style={{ flex: 1 }}>
            <Sparkline data={SPARKLINE_DATA} />
            <div className="pip-trend-label">+18% quality over 7 days</div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

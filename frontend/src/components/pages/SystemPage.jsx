import { useAppStore } from '../../store/appStore'
import { MiniBar, DataRow } from '../ui/primitives'
import { Panel, LiveBadge, KPITile, StatusPill } from '../nexus-ui'
import MiddlewareStatusWidget from '../dashboard/MiddlewareStatusWidget'
import './SystemPage.css'

const APIS = [
  { name:'Anthropic Claude',  status:'ok',   calls:4241, cost:'$1.82',  p99:'340ms' },
  { name:'OpenAI GPT-4',      status:'ok',   calls:612,  cost:'$0.64',  p99:'980ms' },
  { name:'Stripe Payments',   status:'ok',   calls:14,   cost:'$0.00',  p99:'280ms' },
  { name:'Tavily Search',     status:'ok',   calls:88,   cost:'$0.09',  p99:'440ms' },
  { name:'Ollama (local)',    status:'idle', calls:0,    cost:'$0.00',  p99:'—'     },
]
const SECURITY = [
  { item:'JWT rotation',        status:'ok',   note:'Rotated 3d ago'         },
  { item:'API key vault',       status:'ok',   note:'All keys encrypted'     },
  { item:'Rate limiter',        status:'ok',   note:'1200 req/min cap'       },
  { item:'CORS policy',         status:'ok',   note:'Whitelist enforced'     },
  { item:'Anomaly responder',   status:'warn', note:'1 alert in last 24h'    },
]

const STATUS_TONE = { ok: 'success', warn: 'warn', error: 'alert', idle: 'idle' }

const HW_TREND = [38, 42, 47, 51, 49, 54, 58, 62, 60, 65, 67, 64]

export default function SystemPage() {
  const systemStatus = useAppStore(s => s.systemStatus)
  const nnStatus     = useAppStore(s => s.nnStatus)

  const cpu     = systemStatus?.cpu     ?? 42
  const memory  = systemStatus?.memory  ?? 67
  const gpu     = systemStatus?.gpu     ?? 31
  const temp    = systemStatus?.temp    ?? 48
  const mode    = systemStatus?.mode    || 'BALANCED'
  const uptime  = systemStatus?.uptime  || '6h 14m'
  const agents  = systemStatus?.agentCount ?? 8
  const conf    = nnStatus?.confidence  ?? 0
  const brainPct = conf > 1 ? Math.round(conf) : Math.round(conf * 100)

  const totalAPICost = APIS.reduce((a, api) => a + parseFloat(api.cost.replace('$', '') || '0'), 0).toFixed(2)

  const cpuTone = cpu > 80 ? 'alert' : cpu > 60 ? 'warn' : 'success'
  const memTone = memory > 80 ? 'alert' : memory > 60 ? 'warn' : 'cool'

  return (
    <div className="sys-grid">
      {/* KPI strip */}
      <div className="sys-kpis">
        <KPITile icon="◴" iconTone={cpuTone} label="CPU" value={`${cpu}%`} sub={`Temp ${temp}°C`} trend={HW_TREND} />
        <KPITile icon="◰" iconTone={memTone} label="Memory" value={`${memory}%`} sub="System RAM" trend={HW_TREND} />
        <KPITile icon="✦" iconTone="gold"    label="GPU" value={`${gpu}%`} sub="Neural compute" accent trend={HW_TREND} />
        <KPITile icon="◷" iconTone="success" label="Uptime" value={uptime} sub={`Mode · ${mode}`} />
      </div>

      {/* Main two columns */}
      <div className="sys-cols">
        <div className="sys-col">
          <Panel icon="⎈" title="Hardware" actions={<LiveBadge variant="live" />}>
            {[
              ['CPU Load', cpu,     cpu > 80 ? 'var(--nx-danger)' : cpu > 60 ? 'var(--nx-warning)' : 'var(--nx-success)'],
              ['Memory',   memory,  memory > 80 ? 'var(--nx-danger)' : memory > 60 ? 'var(--nx-warning)' : 'var(--nx-info)'],
              ['GPU',      gpu,     'var(--nx-gold)'],
              ['Disk I/O', 34,      'var(--nx-text-dim)'],
            ].map(([l, v, c]) => (
              <div key={l} className="sys-bar">
                <div className="sys-bar__row">
                  <span>{l}</span>
                  <span style={{ color: c }}>{v}%</span>
                </div>
                <MiniBar value={v} color={c} />
              </div>
            ))}
            <div className="sys-grid-2">
              <DataRow label="CPU Temp"  value={`${temp}°C`} />
              <DataRow label="Fans"      value="1,840 RPM" />
              <DataRow label="Processes" value="247" />
              <DataRow label="Threads"   value="1,023" />
            </div>
          </Panel>

          <Panel icon="◈" title="Runtime" className="sys-col__grow">
            <DataRow label="Node.js"       value="v22.3.0"      color="var(--nx-info)" />
            <DataRow label="Python"        value="3.11.4"       color="var(--nx-gold)" />
            <DataRow label="Vite/React"    value="5.0 / 18.3" />
            <DataRow label="FastAPI"       value="0.104.1" />
            <DataRow label="Mode"          value={mode}         color="var(--nx-gold-bright)" />
            <DataRow label="Active Agents" value={agents}       color="var(--nx-info)" />
            <DataRow label="Bus Events"    value="18,920" />
            <DataRow label="LLM Calls"     value="4,241" />
          </Panel>
        </div>

        <div className="sys-col">
          <Panel
            icon="⊕"
            title="API Integrations"
            actions={<StatusPill tone="success" label={`$${totalAPICost} TODAY`} dot={false} size="sm" />}
          >
            <div className="sys-apis">
              {APIS.map(api => (
                <div key={api.name} className="sys-api">
                  <div className="sys-api__head">
                    <span className={`sys-api__dot sys-api__dot--${STATUS_TONE[api.status]}`} />
                    <span className="sys-api__name">{api.name}</span>
                    <StatusPill tone={STATUS_TONE[api.status]} label={api.status.toUpperCase()} dot={false} size="sm" />
                  </div>
                  <div className="sys-api__metrics">
                    <span>calls <em className="sys-api__calls">{api.calls}</em></span>
                    <span>cost <em className="sys-api__cost">{api.cost}</em></span>
                    <span>p99 <em className="sys-api__p99">{api.p99}</em></span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel
            icon="✺"
            title="Neural System"
            actions={<LiveBadge variant={nnStatus?.bg_running ? 'live' : 'idle'} />}
          >
            <DataRow label="Brain Confidence" value={`${brainPct}%`} color="var(--nx-gold)" />
            <div className="sys-brain-bar">
              <div className="sys-brain-bar__fill" style={{ width: `${brainPct}%` }} />
            </div>
            <DataRow label="Learn Step"   value={(nnStatus?.learn_step ?? 14820).toLocaleString()} color="var(--nx-info)" />
            <DataRow label="Success Rate" value={`${Math.round((nnStatus?.success_rate ?? 0.91) * 100)}%`} color="var(--nx-success)" />

            <div className="sys-brain-section">
              <div className="sys-brain-section__label">Recent Decisions</div>
              {nnStatus?.recent_outputs?.length > 0 ? (
                nnStatus.recent_outputs.slice(0, 5).map((d, i) => (
                  <div key={i} className="sys-brain-row">
                    <span className="sys-brain-row__dot" />
                    <span className="sys-brain-row__text">
                      {d.action || d.decision || JSON.stringify(d)}
                    </span>
                    {d.confidence != null && (
                      <span className="sys-brain-row__conf">
                        {Math.round((d.confidence > 1 ? d.confidence : d.confidence * 100))}%
                      </span>
                    )}
                  </div>
                ))
              ) : (
                <div className="sys-brain-empty">— no decisions yet —</div>
              )}
            </div>
            {nnStatus?.recent_learning_events?.length > 0 && (
              <div className="sys-brain-section">
                <div className="sys-brain-section__label">Learning Events</div>
                {nnStatus.recent_learning_events.slice(0, 3).map((e, i) => (
                  <div key={i} className="sys-brain-event">
                    {typeof e === 'string' ? e : JSON.stringify(e)}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <MiddlewareStatusWidget />

          <Panel
            icon="⛨"
            title="Security"
            actions={
              SECURITY.some(s => s.status === 'warn')
                ? <LiveBadge variant="warn" />
                : <LiveBadge variant="live" label="OK" />
            }
            className="sys-col__grow"
          >
            <div className="sys-sec">
              {SECURITY.map((s, i) => (
                <div key={i} className="sys-sec__row">
                  <span className={`sys-sec__dot sys-sec__dot--${STATUS_TONE[s.status]}`} />
                  <span className="sys-sec__item">{s.item}</span>
                  <span className={`sys-sec__note sys-sec__note--${STATUS_TONE[s.status]}`}>{s.note}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, KPITile, StatusPill, HexButton } from '../nexus-ui'
import api from '../../api/client'
import './ControlCenterPage.css'

const FALLBACK_RULES = [
  { id: 'r1', name: 'Memory compaction trigger', condition: 'memory_usage > 75%', action: 'Run memory sweep → archive old embeddings', active: true, runs: 14, last: '2h ago' },
  { id: 'r2', name: 'Agent health auto-restart', condition: 'agent_health < 60%', action: 'Restart agent + notify Doctor', active: true, runs: 3, last: '1d ago' },
  { id: 'r3', name: 'Error cluster alert', condition: 'errors >= 3 in 10min', action: 'Send alert + pause affected agent', active: true, runs: 1, last: '3d ago' },
  { id: 'r4', name: 'Nightly backup', condition: 'cron: 02:00 UTC daily', action: 'Full state backup to persistent store', active: false, runs: 7, last: '8h ago' },
  { id: 'r5', name: 'Neural checkpoint save', condition: 'learn_step % 1000 == 0', action: 'Save brain weights to disk', active: true, runs: 14, last: '30m ago' },
  { id: 'r6', name: 'Revenue alert', condition: 'daily_revenue < $50 target', action: 'Notify + escalate to Strategy Engine', active: true, runs: 0, last: 'Never' },
]

const GOVERNANCE = [
  { rule: 'No agent may delete data without HITL approval', enforced: true },
  { rule: 'All high-risk actions require dual-agent validation', enforced: true },
  { rule: 'Consequential financial actions require human review', enforced: true },
  { rule: 'Agent may not contact external APIs without whitelisting', enforced: true },
  { rule: 'Autonomous outreach capped at 10 messages/day', enforced: false },
]

const AUDIT = [
  { action: 'Memory sweep initiated', actor: 'Auto-rule', ts: '14:22:01', type: 'system' },
  { action: 'Revenue pathway #1 executed', actor: 'Orchestrator', ts: '14:18:30', type: 'agent' },
  { action: 'Agent fleet set to BALANCED', actor: 'User', ts: '14:15:12', type: 'user' },
  { action: 'Stripe webhook deployed', actor: 'Code Synthesizer', ts: '14:02:30', type: 'agent' },
  { action: 'Fairness audit batch 12 run', actor: 'Auto-rule', ts: '13:50:12', type: 'system' },
]

const SYS_NODES = [
  { label: 'User', x: 40, y: 50, key: 'user' },
  { label: 'Node :8787', x: 200, y: 50, key: 'node' },
  { label: 'Python :18790', x: 380, y: 50, key: 'python' },
  { label: 'Agent Fleet', x: 560, y: 50, key: 'agents' },
  { label: 'Memory', x: 380, y: 130, key: 'memory' },
]

const SYS_EDGES = [
  { from: 'user', to: 'node' }, { from: 'node', to: 'python' },
  { from: 'python', to: 'agents' }, { from: 'python', to: 'memory' },
]

export default function ControlCenterPage() {
  const wsConnected = useAppStore(s => s.wsConnected)
  const systemStatus = useAppStore(s => s.systemStatus)
  const storeRules = useAppStore(s => s.automationRules)
  const [sel, setSel] = useState(null)
  const [rules, setRules] = useState(null)

  const [halted, setHalted] = useState(false)
  const [haltConfirm, setHaltConfirm] = useState(false)
  const [halting, setHalting] = useState(false)

  const [recoveryMode, setRecoveryMode] = useState(false)

  const automationRules = rules ?? (storeRules?.length ? storeRules : FALLBACK_RULES)
  const selR = sel ?? automationRules[0]
  const activeRules = automationRules.filter(r => r.active).length
  const toggle = (id) => setRules(automationRules.map(r => r.id === id ? { ...r, active: !r.active } : r))

  const confirmHalt = async () => {
    setHalting(true)
    try {
      const endpoint = typeof api.system?.halt === 'function' ? api.system.halt : api.post
      if (typeof api.system?.halt === 'function') {
        await api.system.halt('Emergency halt via Control Center')
      } else {
        await fetch('/api/system/halt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'Emergency halt via Control Center' })
        })
      }
      setHalted(true)
    } catch (err) {
      console.error('Halt failed:', err)
    }
    setHaltConfirm(false)
    setHalting(false)
  }

  const handleRestart = async () => {
    try {
      if (typeof api.system?.restart === 'function') {
        await api.system.restart()
      } else {
        await fetch('/api/system/restart', { method: 'POST' })
      }
      setHalted(false)
    } catch (err) {
      console.error('Restart failed:', err)
    }
  }

  const toggleRecovery = async () => {
    const next = !recoveryMode
    setRecoveryMode(next)
    if (next) {
      try {
        if (typeof api.chat?.send === 'function') {
          await api.chat.send('Enter safe mode: disable auto-evolution, suspend external API calls, set agents to READ-ONLY')
        } else {
          await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: 'Enter safe mode: disable auto-evolution, suspend external API calls, set agents to READ-ONLY' })
          })
        }
      } catch (err) {
        console.error('Recovery mode toggle failed:', err)
      }
    }
  }

  const nodePos = Object.fromEntries(SYS_NODES.map(n => [n.key, n]))

  return (
    <div className="cc-grid">
      <div className="cc-kpis">
        <KPITile icon="⚙" iconTone="cyan" label="Active Rules" value={activeRules} sub={`of ${automationRules.length} configured`} />
        <KPITile icon="⊕" iconTone="success" label="Governance" value={`${GOVERNANCE.filter(g => g.enforced).length}/${GOVERNANCE.length}`} sub="Rules enforced" />
        <KPITile icon="◈" iconTone="gold" label="Audit Events" value={AUDIT.length} sub="Today's activity" />
        <KPITile icon="◯" iconTone={halted ? 'alert' : wsConnected ? 'success' : 'warning'} label="System" value={halted ? 'HALTED' : wsConnected ? 'ONLINE' : 'OFFLINE'} sub="Current status" />
      </div>

      <Panel
        icon="⛨"
        title="Emergency Controls"
        className="cc-panel"
        actions={<StatusPill tone={halted ? 'alert' : 'cyan'} label={halted ? 'HALTED' : 'OPERATIONAL'} dot={false} size="sm" />}
      >
        <div className="cc-emergency">
          {!halted ? (
            haltConfirm ? (
              <div className="cc-confirm">
                <span className="cc-confirm__text">Are you sure? This stops all agents.</span>
                <HexButton onClick={confirmHalt} disabled={halting} variant="primary" tone="alert" size="sm">{halting ? 'HALTING…' : 'CONFIRM'}</HexButton>
                <HexButton onClick={() => setHaltConfirm(false)} variant="outline" size="sm">CANCEL</HexButton>
              </div>
            ) : (
              <HexButton onClick={() => setHaltConfirm(true)} variant="primary" tone="alert" size="lg">EMERGENCY HALT</HexButton>
            )
          ) : (
            <HexButton onClick={handleRestart} variant="primary" tone="success" size="lg">RESTART SYSTEM</HexButton>
          )}

          <div className="cc-recovery-toggle">
            <span className="cc-recovery-label">RECOVERY MODE</span>
            <div onClick={toggleRecovery} className={`cc-toggle ${recoveryMode ? 'is-on' : ''}`}>
              <div className="cc-toggle__handle" />
            </div>
          </div>
        </div>

        {recoveryMode && (
          <div className="cc-recovery-alert">
            <span>⚠ Auto-evolution OFF</span>
            <span>⚠ External API calls suspended</span>
            <span>⚠ Agents READ-ONLY</span>
          </div>
        )}
      </Panel>

      <Panel icon="◐" title="Live System Map" className="cc-panel">
        <svg width="100%" height="160" viewBox="0 0 660 170" className="cc-sysmap" preserveAspectRatio="xMidYMid meet">
          <defs>
            <marker id="cc-arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 z" fill="rgba(16, 185, 129, 0.5)" />
            </marker>
          </defs>
          {SYS_EDGES.map((e, i) => {
            const f = nodePos[e.from]
            const t = nodePos[e.to]
            return <line key={i} x1={f.x + 50} y1={f.y + 15} x2={t.x} y2={t.y + 15} stroke="rgba(16, 185, 129, 0.3)" strokeWidth="1.5" strokeDasharray="6 3" markerEnd="url(#cc-arr)" />
          })}
          {SYS_NODES.map(n => {
            const alive = n.key === 'user' ? true : n.key === 'node' || n.key === 'python' ? wsConnected : true
            return (
              <g key={n.key}>
                <rect x={n.x} y={n.y} width={100} height={30} rx={5} fill="rgba(255, 255, 255, 0.04)" stroke={alive ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'} strokeWidth="1" />
                <circle cx={n.x + 10} cy={n.y + 15} r={4} fill={alive ? 'var(--nx-success)' : 'var(--nx-danger)'} />
                <text x={n.x + 20} y={n.y + 20} fontSize="10" fill="rgba(255, 255, 255, 0.7)" fontFamily="monospace">{n.label}</text>
              </g>
            )
          })}
          {systemStatus?.cpu && (
            <text x="200" y="100" fontSize="9" fill="rgba(255, 255, 255, 0.3)" fontFamily="monospace">CPU {systemStatus.cpu}%</text>
          )}
        </svg>
      </Panel>

      <div className="cc-cols">
        <div className="cc-col">
          <Panel icon="⚙" title="Automation Rules" className="cc-panel" actions={<StatusPill tone="cyan" label={`${activeRules} active`} dot={false} size="sm" />}>
            <div className="cc-rules">
              {automationRules.map(r => (
                <button key={r.id} onClick={() => setSel(r)} className={`cc-rule ${selR?.id === r.id ? 'is-selected' : ''}`}>
                  <div className="cc-rule__head">
                    <div className={`cc-rule__toggle ${r.active ? 'is-on' : ''}`} onClick={e => { e.stopPropagation(); toggle(r.id) }}>
                      <div className="cc-rule__toggle-handle" />
                    </div>
                    <span className="cc-rule__name">{r.name}</span>
                    <span className="cc-rule__runs">{r.runs}×</span>
                  </div>
                  <div className="cc-rule__condition">IF {r.condition}</div>
                </button>
              ))}
            </div>
          </Panel>

          <Panel icon="📋" title="Governance Rules" className="cc-panel cc-col__grow">
            <div className="cc-governance">
              {GOVERNANCE.map((g, i) => (
                <div key={i} className={`cc-gov-rule ${g.enforced ? 'is-enforced' : ''}`}>
                  <div className="cc-gov-rule__dot" />
                  <span className="cc-gov-rule__text">{g.rule}</span>
                  <span className="cc-gov-rule__status">{g.enforced ? 'ON' : 'OFF'}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div className="cc-col">
          {selR && (
            <Panel icon="◈" title={selR.name} className="cc-panel" actions={<StatusPill tone={selR.active ? 'cyan' : 'idle'} label={selR.active ? 'ACTIVE' : 'OFF'} dot={false} size="sm" />}>
              <div className="cc-rule-detail">
                <div className="cc-rule-detail__condition">IF {selR.condition}</div>
                <div className="cc-rule-detail__action">→ {selR.action}</div>
                <div className="cc-rule-detail__stats">
                  <div className="cc-rule-detail__stat">
                    <span className="cc-rule-detail__stat-label">Runs</span>
                    <span className="cc-rule-detail__stat-value">{selR.runs}</span>
                  </div>
                  <div className="cc-rule-detail__stat">
                    <span className="cc-rule-detail__stat-label">Last Run</span>
                    <span className="cc-rule-detail__stat-value">{selR.last}</span>
                  </div>
                </div>
                <div className="cc-rule-detail__cta">
                  <HexButton onClick={() => {
                    if (typeof api.chat?.send === 'function') {
                      api.chat.send(`Execute rule: ${selR.name}`).catch(() => {})
                    } else {
                      fetch('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: `Execute rule: ${selR.name}` })
                      }).catch(() => {})
                    }
                  }} variant="primary" tone="cyan" size="sm">RUN NOW</HexButton>
                  <HexButton onClick={() => setRules(automationRules.filter(r => r.id !== selR.id))} variant="primary" tone="alert" size="sm">DELETE</HexButton>
                </div>
              </div>
            </Panel>
          )}

          <Panel icon="◐" title="Audit Trail" className="cc-panel cc-col__grow">
            <div className="cc-audit">
              {AUDIT.map((a, i) => (
                <div key={i} className={`cc-audit-entry cc-audit-entry--${a.type}`}>
                  <div className="cc-audit-entry__dot" />
                  <div className="cc-audit-entry__body">
                    <div className="cc-audit-entry__action">{a.action}</div>
                    <div className="cc-audit-entry__meta">{a.actor} · {a.ts}</div>
                  </div>
                  <span className="cc-audit-entry__type">{a.type.toUpperCase()}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

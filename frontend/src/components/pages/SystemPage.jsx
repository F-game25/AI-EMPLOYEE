import { useState, useCallback, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

const MODE_CONFIG = {
  OFF: { color: 'var(--text-muted)', bg: 'rgba(102,102,112,0.1)', label: 'System Off' },
  ON: { color: 'var(--success)', bg: 'rgba(34,197,94,0.1)', label: 'Manual Mode' },
  AUTO: { color: 'var(--warning)', bg: 'rgba(245,158,11,0.1)', label: 'Autonomous' },
}

function SettingRow({ label, value, valueColor }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: 'var(--space-3) 0',
      borderBottom: '1px solid var(--border-subtle)',
      fontSize: '13px',
    }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ color: valueColor || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  )
}

function SectionCard({ title, children }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

function NeuralNetworkSection() {
  const nnStatus = useAppStore(s => s.nnStatus)

  useEffect(() => {
    const controller = new AbortController()
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${BASE}/api/brain/status`, { signal: controller.signal })
        const data = await res.json()
        if (data) useAppStore.getState().setNnStatus(data)
      } catch { /* ignore */ }
    }
    fetchStatus()
    const i = setInterval(fetchStatus, 5000)
    return () => { clearInterval(i); controller.abort() }
  }, [])

  return (
    <SectionCard title="Neural Network">
      <SettingRow label="Mode" value={nnStatus?.mode || 'Unknown'} />
      <SettingRow label="Confidence" value={`${Math.round((nnStatus?.confidence ?? 0) * 100)}%`} valueColor="var(--gold)" />
      <SettingRow label="Learn Step" value={nnStatus?.learn_step ?? 0} />
      <SettingRow label="Buffer" value={`${nnStatus?.buffer_size ?? 0} / ${nnStatus?.max_buffer_size ?? 0}`} />
      <SettingRow label="Device" value={nnStatus?.device ?? 'cpu'} />
      <SettingRow label="Experiences" value={nnStatus?.experiences ?? 0} />
    </SectionCard>
  )
}

function MemorySection() {
  const memoryTree = useAppStore(s => s.memoryTree)
  const dataSource = memoryTree?.data_source

  return (
    <SectionCard title="Memory">
      {dataSource === 'simulated' && (
        <div style={{
          fontSize: '11px',
          color: 'var(--warning)',
          marginBottom: 'var(--space-2)',
          padding: 'var(--space-1) var(--space-2)',
          background: 'rgba(245, 158, 11, 0.08)',
          borderRadius: 'var(--radius-sm)',
        }}>
          SIMULATED — Python backend offline
        </div>
      )}
      <SettingRow label="Total Entities" value={memoryTree?.total_entities ?? 0} />
      <SettingRow label="Nodes" value={memoryTree?.nodes?.length ?? 0} />
      {memoryTree?.nodes?.slice(0, 5).map((node, i) => (
        <div key={i} style={{
          padding: 'var(--space-2) 0',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          fontSize: '12px',
        }}>
          <span style={{ color: 'var(--text-muted)' }}>
            {node.type === 'user' ? '👤' : node.type === 'agent' ? '🤖' : node.type === 'task' ? '📋' : '◆'}
          </span>
          <span style={{ color: 'var(--text-primary)', flex: 1 }}>{node.entity_id || node.id}</span>
          <span style={{ color: 'var(--text-muted)' }}>{node.facts?.length ?? 0} facts</span>
        </div>
      ))}
    </SectionCard>
  )
}

function DoctorSection() {
  const doctor = useAppStore(s => s.doctorStatus)
  const gradeColors = { A: 'var(--success)', B: 'var(--info)', C: 'var(--warning)', D: 'var(--error)' }

  return (
    <SectionCard title="System Health (Doctor)">
      {doctor?.data_source === 'simulated' && (
        <div style={{
          fontSize: '11px',
          color: 'var(--warning)',
          marginBottom: 'var(--space-2)',
          padding: 'var(--space-1) var(--space-2)',
          background: 'rgba(245, 158, 11, 0.08)',
          borderRadius: 'var(--radius-sm)',
        }}>
          SIMULATED — Python backend offline
        </div>
      )}
      <SettingRow
        label="Grade"
        value={doctor?.grade || '—'}
        valueColor={gradeColors[doctor?.grade] || 'var(--text-muted)'}
      />
      <SettingRow label="Score" value={`${doctor?.overall_score ?? 0}%`} />
      {doctor?.issues?.length > 0 && (
        <div style={{ marginTop: 'var(--space-2)' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 'var(--space-1)' }}>Issues</div>
          {doctor.issues.slice(0, 5).map((issue, i) => (
            <div key={i} style={{
              fontSize: '12px',
              color: issue.severity === 'critical' ? 'var(--error)' : issue.severity === 'warning' ? 'var(--warning)' : 'var(--text-secondary)',
              padding: '4px 0',
            }}>
              {typeof issue === 'string' ? issue : issue.message || issue.description}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  )
}

function SelfImprovementSection() {
  const si = useAppStore(s => s.selfImprovement)

  useEffect(() => {
    const controller = new AbortController()
    const fetchSI = async () => {
      try {
        const res = await fetch(`${BASE}/api/self-improvement/status`, { signal: controller.signal })
        const data = await res.json()
        if (data) useAppStore.getState().setSelfImprovement(data)
      } catch { /* ignore */ }
    }
    fetchSI()
    const i = setInterval(fetchSI, 8000)
    return () => { clearInterval(i); controller.abort() }
  }, [])

  const asPct = (v) => v != null ? `${Math.round(v * 100)}%` : '—'

  return (
    <SectionCard title="Self-Improvement Pipeline">
      <SettingRow label="Queue Depth" value={si?.queue_depth ?? 0} />
      <SettingRow label="Processed" value={si?.total_tasks_processed ?? 0} />
      <SettingRow label="Deployed" value={si?.deployed ?? 0} valueColor="var(--success)" />
      <SettingRow label="Pass Rate" value={asPct(si?.pass_rate)} />
      <SettingRow label="Approval Rate" value={asPct(si?.approval_ratio)} />
      <SettingRow label="Rollback Rate" value={asPct(si?.rollback_ratio)} valueColor="var(--warning)" />
    </SectionCard>
  )
}

function GuardrailsSection() {
  return (
    <SectionCard title="Guardrails">
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
        Safety guardrails ensure the AI operates within defined boundaries.
      </div>
      <SettingRow label="Self-improvement" value="Sandbox Only" />
      <SettingRow label="Emergency Stop" value="Available" valueColor="var(--error)" />
      <SettingRow label="Diff Policy" value="Active" valueColor="var(--success)" />
      <SettingRow label="Test Gate" value="Required" />
    </SectionCard>
  )
}

export default function SystemPage() {
  const systemStatus = useAppStore(s => s.systemStatus)
  const autonomyStatus = useAppStore(s => s.autonomyStatus)
  const [modeLoading, setModeLoading] = useState(false)

  const currentMode = autonomyStatus?.mode?.mode || 'OFF'
  const cfg = MODE_CONFIG[currentMode] || MODE_CONFIG.OFF

  const setMode = useCallback(async (newMode) => {
    setModeLoading(true)
    try {
      await fetch(`${BASE}/api/autonomy/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode }),
      })
    } catch { /* ignore */ }
    setModeLoading(false)
  }, [])

  const emergencyStop = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/autonomy/emergency-stop`, { method: 'POST' })
    } catch { /* ignore */ }
  }, [])

  const daemon = autonomyStatus?.daemon || {}

  return (
    <div className="page-enter">
      <PageHeader title="System" subtitle="Settings, integrations, guardrails, and memory" />

      {/* Mode selector */}
      <div className="ds-card" style={{
        padding: 'var(--space-4)',
        marginBottom: 'var(--space-4)',
      }}>
        <h3 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
          System Mode
        </h3>
        <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
          {Object.entries(MODE_CONFIG).map(([mode, mcfg]) => (
            <button
              key={mode}
              onClick={() => setMode(mode)}
              disabled={modeLoading}
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                borderRadius: 'var(--radius-md)',
                border: currentMode === mode ? `1px solid ${mcfg.color}` : '1px solid var(--border-subtle)',
                background: currentMode === mode ? mcfg.bg : 'transparent',
                color: currentMode === mode ? mcfg.color : 'var(--text-muted)',
                fontSize: '13px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 150ms',
                fontFamily: 'inherit',
              }}
            >
              {mode}
              <div style={{ fontSize: '11px', fontWeight: 400, marginTop: '2px', opacity: 0.7 }}>
                {mcfg.label}
              </div>
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span className={`status-dot ${daemon.running ? 'status-dot--active status-dot--pulse' : 'status-dot--idle'}`} />
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Daemon {daemon.running ? 'Running' : 'Stopped'}
              {daemon.cycles > 0 && ` · ${daemon.cycles} cycles`}
            </span>
          </div>
          <button className="btn-danger" onClick={emergencyStop} style={{ fontSize: '12px' }}>
            Emergency Stop
          </button>
        </div>
      </div>

      {/* System settings + subsystem cards in grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: 'var(--space-4)',
      }}>
        {/* Settings */}
        <SectionCard title="Settings">
          <SettingRow label="CPU Usage" value={`${systemStatus?.cpu_usage ?? 0}%`} />
          <SettingRow label="GPU Usage (est.)" value={`${systemStatus?.gpu_usage ?? 0}%`} />
          <SettingRow label="Memory" value={`${systemStatus?.memory ?? 0}%`} />
          <SettingRow label="Running Agents" value={`${systemStatus?.running_agents ?? 0}/${systemStatus?.total_agents ?? 0}`} />
          <SettingRow label="Heartbeat" value={systemStatus?.heartbeat ?? 0} />
          <SettingRow label="Mode" value={systemStatus?.mode || 'MANUAL'} />
        </SectionCard>

        {/* Integrations - Neural Network */}
        <NeuralNetworkSection />

        {/* Memory */}
        <MemorySection />

        {/* Doctor */}
        <DoctorSection />

        {/* Self-Improvement */}
        <SelfImprovementSection />

        {/* Guardrails */}
        <GuardrailsSection />
      </div>
    </div>
  )
}

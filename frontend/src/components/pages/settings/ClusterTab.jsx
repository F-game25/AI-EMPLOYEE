import { useState, useEffect, useCallback } from 'react'
import api from '../../../api/client'

/* ── Tab: CLUSTER — Multi-PC compute mesh with 2FA pairing ──────────────── */

const MB = 1024
const GB = 1024

function fmtVram(mb) {
  if (!mb) return '—'
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`
}
function fmtRam(gb) {
  if (!gb) return '—'
  return `${Number(gb).toFixed(1)} GB`
}
function fmtPct(free, total) {
  if (!total) return null
  return Math.round((1 - free / total) * 100)
}

function GaugeBar({ pct, danger = 80, warn = 60 }) {
  if (pct == null) return null
  const color = pct >= danger ? '#ef4444' : pct >= warn ? '#f59e0b' : '#22c55e'
  return (
    <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 3, height: 6, width: '100%', marginTop: 4 }}>
      <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.4s' }} />
    </div>
  )
}

function NodeCard({ node, isLocal, onUnpair }) {
  const vramPct = fmtPct(node.vram_free_mb, node.vram_total_mb)
  const ramPct  = fmtPct(node.ram_free_gb,  node.ram_total_gb)

  return (
    <div className="cl-node-card">
      <div className="cl-node-header">
        <div className="cl-node-name">
          <span className={`cl-node-dot ${node.paired || isLocal ? 'cl-node-dot--online' : 'cl-node-dot--pending'}`} />
          <span className="cl-node-hostname">{node.hostname || node.node_id}</span>
          {isLocal && <span className="cl-badge cl-badge--primary">THIS NODE</span>}
          {!isLocal && node.paired && <span className="cl-badge cl-badge--paired">PAIRED ✓ 2FA</span>}
          {!isLocal && !node.paired && <span className="cl-badge cl-badge--warn">DISCOVERED — NOT PAIRED</span>}
        </div>
        <div className="cl-node-role">{(node.role || 'any').toUpperCase()}</div>
      </div>

      <div className="cl-node-gpu">{node.gpu_name || 'No GPU'}</div>

      <div className="cl-node-stats">
        <div className="cl-stat">
          <span className="cl-stat-label">VRAM</span>
          <span className="cl-stat-val">{fmtVram(node.vram_free_mb)} free / {fmtVram(node.vram_total_mb)}</span>
          <GaugeBar pct={vramPct} />
        </div>
        <div className="cl-stat">
          <span className="cl-stat-label">RAM</span>
          <span className="cl-stat-val">{fmtRam(node.ram_free_gb)} free / {fmtRam(node.ram_total_gb)}</span>
          <GaugeBar pct={ramPct} />
        </div>
        <div className="cl-stat">
          <span className="cl-stat-label">CPU</span>
          <span className="cl-stat-val">{node.cpu_cores || '?'} cores</span>
        </div>
        {node.ip && (
          <div className="cl-stat">
            <span className="cl-stat-label">IP</span>
            <span className="cl-stat-val">{node.ip}:{node.port || 18790}</span>
          </div>
        )}
      </div>

      {!isLocal && node.paired && (
        <button className="cl-btn cl-btn--danger cl-btn--sm" onClick={() => onUnpair(node.node_id)}>
          REMOVE PAIRING
        </button>
      )}
    </div>
  )
}

function PooledResourceBar({ pooled }) {
  if (!pooled || pooled.node_count < 2) return null
  const vramPct = fmtPct(pooled.vram_free_mb, pooled.vram_total_mb)
  const ramPct  = fmtPct(pooled.ram_free_gb,  pooled.ram_total_gb)

  return (
    <div className="cl-pool-bar">
      <div className="cl-pool-title">
        POOLED CLUSTER RESOURCES — {pooled.node_count} NODES ONLINE
      </div>
      <div className="cl-pool-stats">
        <div className="cl-pool-stat">
          <span className="cl-pool-label">TOTAL VRAM</span>
          <span className="cl-pool-val">{fmtVram(pooled.vram_total_mb)}</span>
          <span className="cl-pool-sub">{fmtVram(pooled.vram_free_mb)} free</span>
          <GaugeBar pct={vramPct} />
        </div>
        <div className="cl-pool-stat">
          <span className="cl-pool-label">TOTAL RAM</span>
          <span className="cl-pool-val">{fmtRam(pooled.ram_total_gb)}</span>
          <span className="cl-pool-sub">{fmtRam(pooled.ram_free_gb)} free</span>
          <GaugeBar pct={ramPct} />
        </div>
        <div className="cl-pool-stat">
          <span className="cl-pool-label">TOTAL CPU</span>
          <span className="cl-pool-val">{pooled.cpu_cores} cores</span>
          <span className="cl-pool-sub">across cluster</span>
        </div>
      </div>
    </div>
  )
}

/* ── Pairing wizard — step 1: generate code on this machine ──────────────── */
function GeneratePairSection({ onDone }) {
  const [pairData, setPairData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const generate = async () => {
    setBusy(true); setErr(null)
    try {
      const d = await api.post('/api/cluster/pair/generate', {})
      setPairData(d)
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  if (!pairData) return (
    <div className="cl-pair-box">
      <h3 className="cl-pair-title">INVITE ANOTHER MACHINE</h3>
      <p className="cl-pair-desc">
        Generate a one-time pairing code. Share the code and TOTP secret with the other machine's operator.
        The operator must enter both on the other machine. Codes expire in 5 minutes.
      </p>
      {err && <div className="cl-error">{err}</div>}
      <button className="cl-btn cl-btn--gold" onClick={generate} disabled={busy}>
        {busy ? 'GENERATING…' : 'GENERATE PAIRING CODE'}
      </button>
    </div>
  )

  return (
    <div className="cl-pair-box cl-pair-box--active">
      <h3 className="cl-pair-title">PAIRING CODE GENERATED</h3>
      <p className="cl-pair-desc">
        Share these with the operator of the other machine. They must enter both to complete pairing.
        <strong> Do not share over public channels.</strong>
      </p>

      <div className="cl-pair-field">
        <label className="cl-pair-label">PAIRING CODE (copy to other machine)</label>
        <div className="cl-pair-value">{pairData.code}</div>
      </div>

      <div className="cl-pair-field">
        <label className="cl-pair-label">TOTP SECRET (copy to other machine)</label>
        <div className="cl-pair-value cl-pair-value--mono">{pairData.totp_secret}</div>
      </div>

      <div className="cl-pair-field">
        <label className="cl-pair-label">OR SCAN QR URI (for authenticator app)</label>
        <div className="cl-pair-value cl-pair-value--uri">{pairData.totp_uri}</div>
      </div>

      <div className="cl-pair-expire">
        Code expires in {Math.round((pairData.expires_in_s || 300) / 60)} minutes.
        Once the other machine pairs, you will see it appear in the node list above.
      </div>

      <button className="cl-btn cl-btn--dim" onClick={() => { setPairData(null); onDone && onDone() }}>
        DONE / CANCEL
      </button>
    </div>
  )
}

/* ── Pairing wizard — step 2: join a cluster on the other machine ────────── */
function JoinClusterSection({ onDone }) {
  const [form, setForm] = useState({
    remote_ip: '', remote_port: '18790',
    code: '', totp_secret: '', totp_code: '',
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [success, setSuccess] = useState(null)

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))

  const submit = async () => {
    if (!form.remote_ip || !form.code || !form.totp_secret || !form.totp_code) {
      setErr('All fields are required'); return
    }
    if (!/^\d{6}$/.test(form.totp_code)) {
      setErr('TOTP code must be exactly 6 digits from your authenticator app'); return
    }
    setBusy(true); setErr(null)
    try {
      const d = await api.post('/api/cluster/pair/init', {
        remote_ip:    form.remote_ip,
        remote_port:  parseInt(form.remote_port, 10),
        code:         form.code.trim().toUpperCase(),
        totp_secret:  form.totp_secret.trim().toUpperCase(),
        totp_code:    form.totp_code.trim(),
      })
      setSuccess(`Paired with node ${d.paired_with || 'remote'}`)
      onDone && onDone()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  return (
    <div className="cl-pair-box">
      <h3 className="cl-pair-title">JOIN A CLUSTER</h3>
      <p className="cl-pair-desc">
        Enter the pairing code and TOTP secret from the other machine, then enter the 6-digit
        code from your authenticator app. <strong>You must enter this yourself — it cannot be automated.</strong>
      </p>

      {err && <div className="cl-error">{err}</div>}
      {success && <div className="cl-success">{success}</div>}

      <div className="cl-pair-form">
        <label className="cl-pair-label">OTHER MACHINE IP ADDRESS</label>
        <input className="cl-input" placeholder="192.168.1.x" value={form.remote_ip}
          onChange={e => set('remote_ip', e.target.value)} />

        <label className="cl-pair-label">PORT (default 18790)</label>
        <input className="cl-input" value={form.remote_port}
          onChange={e => set('remote_port', e.target.value)} />

        <label className="cl-pair-label">PAIRING CODE (from other machine)</label>
        <input className="cl-input cl-input--mono" placeholder="A3F9C201"
          value={form.code} onChange={e => set('code', e.target.value)} />

        <label className="cl-pair-label">TOTP SECRET (from other machine)</label>
        <input className="cl-input cl-input--mono" placeholder="JBSWY3DPEHPK3PXP…"
          value={form.totp_secret} onChange={e => set('totp_secret', e.target.value)} />

        <label className="cl-pair-label">YOUR 6-DIGIT TOTP CODE — enter now from authenticator</label>
        <input className="cl-input cl-input--totp" placeholder="000000" maxLength={6}
          inputMode="numeric" value={form.totp_code}
          onChange={e => set('totp_code', e.target.value.replace(/\D/g, '').slice(0, 6))} />

        <div className="cl-pair-totp-note">
          ⚠ This code changes every 30 seconds. Submit immediately after entering.
          The system cannot auto-fill this — only you can.
        </div>
      </div>

      <button className="cl-btn cl-btn--gold" onClick={submit} disabled={busy}>
        {busy ? 'PAIRING…' : 'PAIR WITH THIS CODE + TOTP'}
      </button>
    </div>
  )
}

/* ── Main ClusterTab ─────────────────────────────────────────────────────── */
export default function ClusterTab() {
  const [status, setStatus]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [view, setView]       = useState('status') // 'status' | 'invite' | 'join'
  const [unpairId, setUnpairId] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const d = await api.get('/api/cluster/status')
      setStatus(d)
    } catch { setStatus({ enabled: false, offline: true }) }
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 8000)
    return () => clearInterval(id)
  }, [refresh])

  const unpair = async (nodeId) => {
    try {
      await api.post('/api/cluster/unpair', { node_id: nodeId })
      refresh()
    } catch (e) { alert('Remove pairing failed: ' + e.message) }
    setUnpairId(null)
  }

  if (loading) return <div className="cl-loading">SCANNING CLUSTER…</div>

  const enabled    = status?.enabled
  const peers      = status?.peers || []
  const local      = status?.local
  const pooled     = status?.pooled
  const paired     = peers.filter(p => p.paired)
  const discovered = peers.filter(p => !p.paired)

  return (
    <div className="cl-tab">
      {/* ── Header ── */}
      <div className="cl-header">
        <div>
          <h2 className="cl-title">COMPUTE CLUSTER</h2>
          <p className="cl-subtitle">
            Link multiple machines into one AI compute mesh. Every connection requires
            2FA — a shared token plus a time-based one-time code you enter manually.
            No node can join without your explicit approval.
          </p>
        </div>
        <div className="cl-status-pill">
          <span className={`cl-dot ${enabled ? 'cl-dot--on' : 'cl-dot--off'}`} />
          {enabled
            ? `CLUSTER ACTIVE — ${1 + paired.length} node${paired.length ? 's' : ''}`
            : 'CLUSTER DISABLED'}
        </div>
      </div>

      {!enabled && (
        <div className="cl-setup-hint">
          <strong>Enable cluster:</strong> add <code>AI_CLUSTER_TOKEN=your-secret-phrase</code> to{' '}
          <code>~/.ai-employee/.env</code> on every machine, then restart.
          Use the same token on all machines. Keep it private — it is half of your 2FA.
        </div>
      )}

      {/* ── Pooled resources ── */}
      {enabled && <PooledResourceBar pooled={pooled} />}

      {/* ── Node list ── */}
      {enabled && (
        <div className="cl-nodes-section">
          <div className="cl-section-label">NODES</div>
          <div className="cl-nodes-grid">
            {local && (
              <NodeCard node={local} isLocal onUnpair={() => {}} />
            )}
            {paired.map(p => (
              <NodeCard key={p.node_id} node={p} isLocal={false}
                onUnpair={id => setUnpairId(id)} />
            ))}
          </div>

          {discovered.length > 0 && (
            <div className="cl-discovered">
              <div className="cl-section-label cl-section-label--warn">
                DISCOVERED (NOT YET PAIRED) — {discovered.length} machine{discovered.length > 1 ? 's' : ''}
              </div>
              <div className="cl-nodes-grid">
                {discovered.map(p => (
                  <NodeCard key={p.node_id} node={p} isLocal={false} onUnpair={() => {}} />
                ))}
              </div>
              <p className="cl-pair-hint">
                These machines broadcast the same cluster token but have not completed 2FA pairing.
                Use INVITE or JOIN below to pair them securely.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Pairing actions ── */}
      {enabled && (
        <div className="cl-pair-actions">
          <div className="cl-action-tabs">
            <button className={`cl-action-tab ${view === 'invite' ? 'cl-action-tab--active' : ''}`}
              onClick={() => setView(view === 'invite' ? 'status' : 'invite')}>
              + INVITE MACHINE (generate code)
            </button>
            <button className={`cl-action-tab ${view === 'join' ? 'cl-action-tab--active' : ''}`}
              onClick={() => setView(view === 'join' ? 'status' : 'join')}>
              + JOIN CLUSTER (enter code)
            </button>
          </div>

          {view === 'invite' && <GeneratePairSection onDone={() => { setView('status'); refresh() }} />}
          {view === 'join'   && <JoinClusterSection  onDone={() => { setView('status'); refresh() }} />}
        </div>
      )}

      {/* ── Unpair confirm ── */}
      {unpairId && (
        <div className="cl-modal-overlay" onClick={() => setUnpairId(null)}>
          <div className="cl-modal" onClick={e => e.stopPropagation()}>
            <h3 className="cl-modal-title">REMOVE PAIRING</h3>
            <p className="cl-modal-body">
              Remove the 2FA pairing with node <code>{unpairId}</code>?
              The node will no longer be able to receive tasks. You can re-pair at any time.
            </p>
            <div className="cl-modal-actions">
              <button className="cl-btn cl-btn--dim" onClick={() => setUnpairId(null)}>CANCEL</button>
              <button className="cl-btn cl-btn--danger" onClick={() => unpair(unpairId)}>REMOVE</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Security note ── */}
      <div className="cl-security-note">
        <strong>Security:</strong> All cluster connections use two factors — (1) shared token in your .env file,
        (2) a 6-digit TOTP code that rotates every 30 seconds and must be entered by you.
        No machine can join automatically. If you lose the token, remove it from .env on all machines and restart.
      </div>
    </div>
  )
}

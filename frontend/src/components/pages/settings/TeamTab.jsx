import { useState, useEffect } from 'react'
import api from '../../../api/client'
import { NxField, NxSaveBtn, SafetyConfirmModal } from './controls'

/* ── Tab 9: TEAM & ACCESS ──────────────────────────────────────────────── */

const BUILT_IN_ROLES = [
  { id: 'admin',    label: 'Admin',    desc: 'Full system access — can modify settings, manage agents, and control all operations.' },
  { id: 'operator', label: 'Operator', desc: 'Can run tasks and manage agents. Cannot change security settings or billing.' },
  { id: 'viewer',   label: 'Viewer',   desc: 'Read-only access to dashboards, logs, and agent status. No write permissions.' },
]

const PERM_RESOURCES = ['Agents', 'Tasks', 'Security', 'Settings', 'Economy', 'Knowledge']
const PERM_LEVELS    = ['None', 'Read', 'Write']

function TeamTab() {
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState(BUILT_IN_ROLES)
  const [permMatrix, setPermMatrix] = useState({})
  const [showInvite, setShowInvite] = useState(false)
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'viewer' })
  const [inviting, setInviting] = useState(false)
  const [pendingUserRemoval, setPendingUserRemoval] = useState(null)

  useEffect(() => {
    api.get('/api/users').then(d => setUsers(Array.isArray(d?.users) ? d.users : [])).catch(() => {})
    api.get('/api/roles').then(d => { if (Array.isArray(d?.roles) && d.roles.length) setRoles(d.roles) }).catch(() => {})
    api.get('/api/permissions-matrix').then(d => { if (d?.matrix) setPermMatrix(d.matrix) }).catch(() => {})
  }, [])

  const defaultPerm = (resource, role) => {
    if (role === 'admin') return 'Write'
    if (role === 'operator') return resource === 'Security' || resource === 'Settings' ? 'None' : 'Write'
    return 'Read'
  }

  const getPerm = (resource, roleId) => permMatrix[resource]?.[roleId] ?? defaultPerm(resource, roleId)
  const setPerm = (resource, roleId, val) => setPermMatrix(p => ({
    ...p, [resource]: { ...(p[resource] || {}), [roleId]: val }
  }))

  const [savingPerms, setSavingPerms] = useState(false)
  const [savedPerms, setSavedPerms] = useState(false)
  const savePerms = async () => {
    setSavingPerms(true)
    await api.put('/api/permissions-matrix', { matrix: permMatrix }).catch(() => {})
    setSavingPerms(false); setSavedPerms(true)
    setTimeout(() => setSavedPerms(false), 2000)
  }

  const invite = async () => {
    setInviting(true)
    try {
      await api.post('/api/users', inviteForm)
      const d = await api.get('/api/users').catch(() => null)
      if (d?.users) setUsers(d.users)
      setInviteForm({ email: '', role: 'viewer' })
      setShowInvite(false)
    } catch {}
    setInviting(false)
  }

  const removeUser = async id => {
    const user = users.find(u => u.id === id)
    setPendingUserRemoval({
      label: 'REMOVE USER',
      warning: `Remove ${user?.email || id} from the system.`,
      confirmText: 'REMOVE USER',
      endpoint: `DELETE /api/users/${id}`,
      risk: 'high',
      userId: id,
    })
  }

  const confirmRemoveUser = async (action, safety) => {
    setPendingUserRemoval(null)
    await api.delete(`/api/users/${action.userId}`).catch(() => {})
    await api.post('/api/admin/safety-audit', {
      label: action.label,
      endpoint: action.endpoint,
      reason: safety.reason,
      confirmation: safety.confirmation,
      risk: action.risk,
      executed: true,
    }).catch(() => {})
    setUsers(p => p.filter(u => u.id !== action.userId))
  }

  return (
    <div className="nx-tab-content">
      {pendingUserRemoval && (
        <SafetyConfirmModal
          action={pendingUserRemoval}
          onConfirm={confirmRemoveUser}
          onCancel={() => setPendingUserRemoval(null)}
        />
      )}
      <div className="nx-section">
        <div className="nx-section-label">USERS</div>
        <div className="nx-sec-table-wrap">
          <div className="nx-sec-thead nx-sec-thead--users">
            <span>Email</span><span>Role</span><span>Last Active</span><span>Status</span><span>Actions</span>
          </div>
          {users.length === 0 && <div className="nx-sec-empty">No users found</div>}
          {users.map(u => (
            <div key={u.id} className="nx-sec-row nx-sec-row--users">
              <span className="nx-sec-name">{u.email}</span>
              <span className="nx-sec-muted">{u.role}</span>
              <span className="nx-sec-muted">{u.last_active ? new Date(u.last_active).toLocaleDateString() : '—'}</span>
              <span className={`nx-sec-status nx-sec-status--${u.status || 'active'}`}>{(u.status || 'active').toUpperCase()}</span>
              <button className="nx-save-btn nx-save-btn--danger nx-save-btn--xs" onClick={() => removeUser(u.id)}>Remove</button>
            </div>
          ))}
        </div>
        <button className="nx-save-btn nx-save-btn--outline" style={{ marginTop: 12 }} onClick={() => setShowInvite(v => !v)}>
          {showInvite ? 'CANCEL' : '+ INVITE USER'}
        </button>
        {showInvite && (
          <div className="nx-sec-token-form">
            <div className="nx-form-grid">
              <NxField label="EMAIL ADDRESS">
                <input className="nx-input" type="email" value={inviteForm.email} onChange={e => setInviteForm(p => ({ ...p, email: e.target.value }))} placeholder="user@company.com" />
              </NxField>
              <NxField label="ROLE">
                <select className="nx-input" value={inviteForm.role} onChange={e => setInviteForm(p => ({ ...p, role: e.target.value }))}>
                  {roles.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                </select>
              </NxField>
            </div>
            <NxSaveBtn label="SEND INVITE" saving={inviting} saved={false} onClick={invite} />
          </div>
        )}
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">ROLES</div>
        <div className="nx-team-roles-grid">
          {BUILT_IN_ROLES.map(r => (
            <div key={r.id} className="nx-team-role-card">
              <div className="nx-team-role-name">{r.label}</div>
              <div className="nx-team-role-desc">{r.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">PERMISSIONS MATRIX</div>
        <div className="nx-perm-table">
          <div className="nx-perm-thead">
            <span className="nx-perm-resource-col">Resource</span>
            {BUILT_IN_ROLES.map(r => <span key={r.id} className="nx-perm-role-col">{r.label}</span>)}
          </div>
          {PERM_RESOURCES.map(res => (
            <div key={res} className="nx-perm-row">
              <span className="nx-perm-resource-col nx-sec-name">{res}</span>
              {BUILT_IN_ROLES.map(r => (
                <span key={r.id} className="nx-perm-role-col">
                  <select className="nx-input nx-input--sm" value={getPerm(res, r.id)} onChange={e => setPerm(res, r.id, e.target.value)}>
                    {PERM_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                </span>
              ))}
            </div>
          ))}
        </div>
        <NxSaveBtn label="SAVE PERMISSIONS" saving={savingPerms} saved={savedPerms} onClick={savePerms} />
      </div>
    </div>
  )
}

export default TeamTab

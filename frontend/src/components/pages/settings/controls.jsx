import { useState, useEffect } from 'react'
import api from '../../../api/client'

/* Shared Settings primitives — extracted from SettingsPage so tabs can live in
   their own files. Styling comes from SettingsPage.css (global once imported). */

export function NxToggle({ checked, onChange }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      className={`nx-toggle ${checked ? 'nx-toggle--on' : ''}`}
      onClick={() => onChange(!checked)}
      type="button"
    >
      <span className="nx-toggle-thumb" />
    </button>
  )
}

export function NxSlider({ value, min, max, step = 0.01, onChange, format = v => v }) {
  return (
    <div className="nx-slider-wrap">
      <input
        type="range"
        className="nx-slider"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
      <span className="nx-slider-val">{format(value)}</span>
    </div>
  )
}

export function NxField({ label, children, full }) {
  return (
    <div className={`nx-field ${full ? 'nx-field--full' : ''}`}>
      <span className="nx-field-label">{label}</span>
      {children}
    </div>
  )
}

export function NxSaveBtn({ label = 'SAVE', saving, saved, onClick, danger }) {
  return (
    <button
      className={`nx-save-btn ${danger ? 'nx-save-btn--danger' : ''} ${saved ? 'nx-save-btn--saved' : ''}`}
      onClick={onClick}
      disabled={saving || saved}
    >
      {saved ? '✓ SAVED' : saving ? 'SAVING…' : label}
    </button>
  )
}

export function useSave(endpoint, data) {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const save = async () => {
    setSaving(true)
    await api.post(endpoint, data).catch(() => {})
    setSaving(false); setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }
  return { saving, saved, save }
}

export function SafetyConfirmModal({ action, onConfirm, onCancel }) {
  const [text, setText] = useState('')
  const [reason, setReason] = useState('')
  const [countdown, setCountdown] = useState(action.countdown ?? 5)
  const confirmText = action.confirmText || action.label || 'CONFIRM'
  const canConfirm = text === confirmText && reason.trim().length >= 8 && countdown === 0

  useEffect(() => {
    setCountdown(action.countdown ?? 5)
    const timer = setInterval(() => {
      setCountdown(v => Math.max(0, v - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [action])

  return (
    <div className="nx-modal-backdrop" role="dialog" aria-modal="true">
      <div className="nx-modal">
        <div className="nx-modal-title">{action.label}</div>
        <div className="nx-modal-body">
          <p className="nx-modal-warning">{action.warning}</p>
          <div className="nx-safety-meta">
            <span>Risk: <strong>{action.risk || 'high'}</strong></span>
            <span>Endpoint: <code>{action.endpoint || 'internal'}</code></span>
            <span>Execution: <strong>{action.executionLabel || 'staged for approval/audit'}</strong></span>
          </div>
          <p className="nx-modal-prompt">Type <strong>{confirmText}</strong> to proceed:</p>
          <input className="nx-input nx-input--danger" value={text} onChange={e => setText(e.target.value)} autoFocus />
          <p className="nx-modal-prompt">Reason for this action:</p>
          <textarea
            className="nx-input nx-input--danger nx-safety-reason"
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="Required for audit trail..."
            rows={3}
          />
          <div className="nx-safety-countdown">
            {countdown > 0 ? `Available in ${countdown}s` : 'Confirmation window ready'}
          </div>
        </div>
        <div className="nx-modal-actions">
          <button className="nx-save-btn nx-save-btn--outline" onClick={onCancel}>CANCEL</button>
          <button className="nx-save-btn nx-save-btn--danger" disabled={!canConfirm} onClick={() => onConfirm(action, { reason, confirmation: text })}>
            {action.label}
          </button>
        </div>
      </div>
    </div>
  )
}

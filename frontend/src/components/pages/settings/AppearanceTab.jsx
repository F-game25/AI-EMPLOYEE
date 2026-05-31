import { useState, useEffect } from 'react'
import { NxToggle, NxField, NxSaveBtn, NxSlider, useSave } from './controls'

const THEMES = [
  { id: 'nexus-dark',   label: 'NEXUS DARK',   colors: ['#e5c76b', '#07080f', '#10131f'] },
  { id: 'cyber-blue',   label: 'CYBER BLUE',   colors: ['#20d6c7', '#040c1a', '#0b1629'] },
  { id: 'matrix-green', label: 'MATRIX GREEN', colors: ['#22c55e', '#030903', '#0a160a'] },
]

// Rendering (GPU) mode — controllable in-app instead of a terminal env var.
// Only shown inside the Electron launcher (window.ai present). Applies on restart.
const RENDER_LABELS = { auto: 'Auto (recommended)', hardware: 'Hardware (GPU)', software: 'Software (most stable)' }
const RENDER_DESC = {
  auto: 'Use the GPU; fall back to software if the WebGL context is lost.',
  hardware: 'Force GPU rendering — fastest, but unstable on some Linux drivers.',
  software: 'SwiftShader software rendering — slower, but never loses the WebGL context. Use this if pages flicker or go blank.',
}

function RenderingSection() {
  const [mode, setMode] = useState(null)
  const [options, setOptions] = useState(['auto', 'hardware', 'software'])
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    if (!window.ai?.getRenderMode) { setMode('unavailable'); return }
    window.ai.getRenderMode()
      .then(r => { setMode(r.mode || 'auto'); if (Array.isArray(r.options)) setOptions(r.options) })
      .catch(() => setMode('unavailable'))
  }, [])
  if (mode === 'unavailable' || mode === null) return null   // browser mode — no launcher
  const choose = async (m) => {
    setMode(m)
    try { await window.ai.setRenderMode(m); setDirty(true) } catch { /* */ }
  }
  return (
    <>
      <div className="nx-divider" />
      <div className="nx-section">
        <div className="nx-section-label">RENDERING (GPU)</div>
        <div className="nx-render-opts" role="radiogroup" aria-label="Rendering mode">
          {options.map(o => (
            <button key={o} type="button" role="radio" aria-checked={mode === o}
              className={`nx-render-opt ${mode === o ? 'nx-render-opt--active' : ''}`} onClick={() => choose(o)}>
              <span className="nx-render-opt__title">{RENDER_LABELS[o] || o}{mode === o && ' ✓'}</span>
              <span className="nx-render-opt__desc">{RENDER_DESC[o] || ''}</span>
            </button>
          ))}
        </div>
        {dirty && (
          <div className="nx-render-restart">
            <span>Saved — restart the app to apply.</span>
            <button className="nx-save-btn" onClick={() => window.ai?.restartSystem?.()}>Restart now</button>
          </div>
        )}
      </div>
    </>
  )
}

export default function AppearanceTab() {
  const [cfg, setCfg] = useState({ theme: 'nexus-dark', sidebar_collapsed: false, reduced_motion: false, font_size: 13 })
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings', cfg)

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">THEME</div>
        <div className="nx-theme-grid">
          {THEMES.map(t => (
            <button
              key={t.id}
              type="button"
              className={`nx-theme-tile ${cfg.theme === t.id ? 'nx-theme-tile--active' : ''}`}
              onClick={() => set('theme', t.id)}
            >
              <div className="nx-theme-preview" style={{ background: t.colors[1] }}>
                <div className="nx-theme-swatch" style={{ background: t.colors[0] }} />
                <div className="nx-theme-swatch nx-theme-swatch--2" style={{ background: t.colors[2] }} />
              </div>
              <span className="nx-theme-label">{t.label}</span>
              {cfg.theme === t.id && <span className="nx-theme-check">✓</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">DISPLAY OPTIONS</div>
        <div className="nx-toggle-list">
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">COLLAPSED SIDEBAR</span>
              <span className="nx-toggle-desc">Start with navigation rail collapsed by default</span>
            </div>
            <NxToggle checked={cfg.sidebar_collapsed} onChange={v => set('sidebar_collapsed', v)} />
          </div>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">REDUCED MOTION</span>
              <span className="nx-toggle-desc">Override prefers-reduced-motion — disable all animations</span>
            </div>
            <NxToggle checked={cfg.reduced_motion} onChange={v => set('reduced_motion', v)} />
          </div>
        </div>

        <div className="nx-divider" />

        <div className="nx-form-grid">
          <NxField label={`FONT SIZE — ${cfg.font_size}px`} full>
            <NxSlider value={cfg.font_size} min={12} max={18} step={1} onChange={v => set('font_size', v)} format={v => `${v}px`} />
          </NxField>
        </div>

        <NxSaveBtn label="APPLY APPEARANCE" saving={saving} saved={saved} onClick={save} />
      </div>

      <RenderingSection />
    </div>
  )
}

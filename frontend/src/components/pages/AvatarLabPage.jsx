import { useState, useEffect, useRef } from 'react'
import CognitiveEye from '../avatar/CognitiveEye'

export default function AvatarLabPage() {
  const [size, setSize] = useState(380)
  const [mode, setMode] = useState('dashboard')
  const [fps, setFps] = useState(0)
  const lastRef = useRef(performance.now())
  const frameRef = useRef(0)

  // FPS counter
  useEffect(() => {
    let id
    function measure(ts) {
      frameRef.current++
      if (ts - lastRef.current >= 1000) {
        setFps(frameRef.current)
        frameRef.current = 0
        lastRef.current = ts
      }
      id = requestAnimationFrame(measure)
    }
    id = requestAnimationFrame(measure)
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <div style={{
      minHeight: '100%', background: '#07080F', color: '#E5C76B',
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: '2rem', gap: '2rem', fontFamily: 'ui-monospace, monospace',
    }}>
      <div style={{ display: 'flex', gap: '2rem', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'center' }}>
        <h2 style={{ margin: 0, fontSize: 14, letterSpacing: '0.12em', textTransform: 'uppercase', opacity: 0.7 }}>
          Avatar Lab
        </h2>
        <span style={{ fontSize: 12, color: '#27c27c' }}>⬤ {fps} FPS</span>
      </div>

      {/* Main preview */}
      <div style={{
        background: '#0E1020', border: '1px solid rgba(229,199,107,0.15)',
        borderRadius: 20, padding: '2rem', display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: '1.5rem',
      }}>
        <CognitiveEye size={size} mode={mode} onClick={() => alert('Companion toggled')} />
        <div style={{ fontSize: 11, opacity: 0.45, textAlign: 'center' }}>
          {size}px · {mode} mode · move mouse to track pupil
        </div>
      </div>

      {/* Toolbar preview */}
      <div style={{
        background: '#0E1020', border: '1px solid rgba(229,199,107,0.10)',
        borderRadius: 10, padding: '0.75rem 1.5rem',
        display: 'flex', alignItems: 'center', gap: '1rem',
      }}>
        <span style={{ fontSize: 11, opacity: 0.4 }}>Toolbar preview:</span>
        <CognitiveEye size={32} mode="toolbar" onClick={() => alert('Toolbar click')} />
        <span style={{ fontSize: 11, opacity: 0.3 }}>← same component, 32px</span>
      </div>

      {/* Controls */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '1rem', width: '100%', maxWidth: 640,
      }}>
        <label style={ctrlStyle}>
          <span>Size: {size}px</span>
          <input type="range" min="80" max="500" value={size} onChange={e => setSize(+e.target.value)} style={{ width: '100%' }} />
        </label>
        <label style={ctrlStyle}>
          <span>Mode</span>
          <div style={{ display: 'flex', gap: 8 }}>
            {['dashboard', 'toolbar'].map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                padding: '4px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                background: mode === m ? '#E5C76B' : 'rgba(229,199,107,0.1)',
                color: mode === m ? '#07080F' : '#E5C76B',
                border: '1px solid rgba(229,199,107,0.3)',
              }}>{m}</button>
            ))}
          </div>
        </label>
      </div>

      <div style={{ fontSize: 11, opacity: 0.3, maxWidth: 480, textAlign: 'center' }}>
        Pupil tracking: zero React re-renders per frame (direct SVG DOM mutation via ref).
        CSS ring animations run on the compositor. Build uses only SVG — no WebGL/Canvas.
      </div>
    </div>
  )
}

const ctrlStyle = {
  display: 'flex', flexDirection: 'column', gap: 8,
  background: '#0E1020', border: '1px solid rgba(229,199,107,0.10)',
  borderRadius: 10, padding: '0.75rem 1rem', fontSize: 12,
}

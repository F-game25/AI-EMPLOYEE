import { useState, useCallback } from 'react'

// Wraps a Three.js Canvas with automatic WebGL context loss/restore recovery.
// On context loss the canvas unmounts (showing a brief fallback); on restore
// it remounts via a key increment so Three.js reinitialises cleanly.
//
// Usage:
//   <WebGLRecovery style={containerStyle}>
//     {({ onCreated }) => <Canvas onCreated={onCreated} ...>...</Canvas>}
//   </WebGLRecovery>
export default function WebGLRecovery({ children, fallback, style }) {
  const [key, setKey] = useState(0)
  const [lost, setLost] = useState(false)

  const onCreated = useCallback(({ gl }) => {
    const canvas = gl.domElement
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault()
      setLost(true)
    })
    canvas.addEventListener('webglcontextrestored', () => {
      setLost(false)
      setKey(k => k + 1)
    })
  }, [])

  if (lost) {
    return fallback ?? (
      <div style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.25)', fontSize: 11 }}>
        GPU context restoring…
      </div>
    )
  }

  return (
    <div key={key} style={style}>
      {typeof children === 'function' ? children({ onCreated }) : children}
    </div>
  )
}

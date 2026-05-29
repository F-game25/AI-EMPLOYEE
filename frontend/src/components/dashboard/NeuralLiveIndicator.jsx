import { useState, useEffect, useRef } from 'react'
import { useBrainStore } from '../../store/brainStore'
import { useAppStore } from '../../store/appStore'
import './NeuralLiveIndicator.css'

function WritesPerSec(timestamps) {
  if (!timestamps.length) return 0
  const now = Date.now()
  const recent = timestamps.filter(t => now - t < 5000)
  return (recent.length / 5).toFixed(1)
}

export default function NeuralLiveIndicator() {
  const reasoningSteps = useBrainStore(s => s.reasoningSteps)
  const memoryWrites   = useBrainStore(s => s.memoryWrites)
  const nodes          = useBrainStore(s => s.nodes)
  const agents         = useAppStore(s => s.agents)
  const writeTimestamps = useRef([])

  const [wps, setWps] = useState('0.0')

  useEffect(() => {
    if (!memoryWrites.length) return
    writeTimestamps.current.push(Date.now())
    if (writeTimestamps.current.length > 20) writeTimestamps.current.shift()
    setWps(WritesPerSec(writeTimestamps.current))
  }, [memoryWrites])

  const latest = reasoningSteps.at(-1)
  const activeAgents = agents.filter(a => a.status === 'running' || a.status === 'active' || a.active).length
  const isReasoning = latest?.status === 'active'

  const stats = [
    { label: 'REASONING', value: latest ? `${latest.node || latest.step || '—'}` : '—', active: isReasoning, color: 'var(--neon-teal, #20D6C7)' },
    { label: 'MEM WRITES', value: `${wps}/s`, active: parseFloat(wps) > 0, color: '#9333EA' },
    { label: 'GRAPH NODES', value: nodes.length, active: nodes.length > 0, color: '#60A5FA' },
    { label: 'AGENTS', value: `${activeAgents} active`, active: activeAgents > 0, color: '#E5C76B' },
  ]

  return (
    <div className="nli">
      <div className="nli__header">
        <span className="nli__title">NEURAL BRAIN</span>
        <span className={`nli__live ${isReasoning ? 'nli__live--on' : ''}`}>
          {isReasoning ? '● ACTIVE' : '○ IDLE'}
        </span>
      </div>
      <div className="nli__stats">
        {stats.map(s => (
          <div key={s.label} className="nli__row">
            <div className="nli__row-top">
              <span className="nli__label">{s.label}</span>
              <span className="nli__value" style={{ color: s.color }}>{s.value}</span>
            </div>
            <div className="nli__bar-track">
              <div
                className={`nli__bar-fill ${s.active ? 'nli__bar-fill--active' : ''}`}
                style={{ background: s.color, width: s.active ? '70%' : '10%' }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

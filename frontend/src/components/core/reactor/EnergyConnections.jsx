import { useEffect, useRef, useState } from 'react'

const CORNERS = [
  { id: 'tl', label: 'cognition',      color: '#22d3ee', from: [-260, -260], to: [-50, -30] },
  { id: 'tr', label: 'operations',     color: '#fbbf24', from: [ 260, -260], to: [ 50, -30] },
  { id: 'bl', label: 'economy',        color: '#a855f7', from: [-260,  260], to: [-50,  30] },
  { id: 'br', label: 'infrastructure', color: '#22c55e', from: [ 260,  260], to: [ 50,  30] },
]

const EVENT_TO_CORNER = {
  'nb:reasoning_step': 'tl',
  'nb:memory_write':   'tl',
  'cognitive:*':       'tl',
  'task:update':       'tr',
  'task:*':            'tr',
  'agent:update':      'tr',
  'revenue:event':     'bl',
  'economy:*':         'bl',
  'money:*':           'bl',
  'system:tick':       'br',
  'system:*':          'br',
  'heartbeat':         'br',
}

function buildPath(from, to) {
  const [x1, y1] = from
  const [x2, y2] = to
  const mid1x = x1 * 0.6
  const mid1y = y1 * 0.6
  const mid2x = x2 * 1.4
  const mid2y = y2 * 1.4
  return `M ${x1} ${y1} C ${mid1x} ${mid1y}, ${mid2x} ${mid2y}, ${x2} ${y2}`
}

function getCornerForEvent(eventType) {
  if (!eventType) return null
  if (EVENT_TO_CORNER[eventType]) return EVENT_TO_CORNER[eventType]
  if (eventType.startsWith('nb:') || eventType.startsWith('cognitive:') || eventType.startsWith('brain:')) return 'tl'
  if (eventType.startsWith('task:') || eventType.startsWith('agent:') || eventType.startsWith('execution:')) return 'tr'
  if (eventType.startsWith('revenue:') || eventType.startsWith('economy:') || eventType.startsWith('money:') || eventType.startsWith('objective:')) return 'bl'
  if (eventType.startsWith('system:') || eventType === 'heartbeat') return 'br'
  return null
}

export default function EnergyConnections() {
  const [pulses, setPulses] = useState([])
  const pulseId = useRef(0)
  const timeoutsRef = useRef([])

  useEffect(() => {
    const handler = (e) => {
      const eventType = e.detail?.type || ''
      const cornerId = getCornerForEvent(eventType)
      if (!cornerId) return
      const id = ++pulseId.current
      setPulses(prev => {
        const filtered = prev.filter(p => p.cornerId !== cornerId).slice(-5)
        return [...filtered, { id, cornerId, startTime: performance.now() }]
      })
      const t = setTimeout(() => {
        setPulses(prev => prev.filter(p => p.id !== id))
      }, 800)
      timeoutsRef.current.push(t)
    }
    window.addEventListener('ws:any', handler)
    return () => {
      window.removeEventListener('ws:any', handler)
      timeoutsRef.current.forEach(clearTimeout)
      timeoutsRef.current = []
    }
  }, [])

  return (
    <svg
      viewBox="-300 -300 600 600"
      className="ec-svg"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      aria-hidden="true"
    >
      <defs>
        {CORNERS.map(c => (
          <linearGradient
            key={c.id}
            id={`ec-grad-${c.id}`}
            gradientUnits="userSpaceOnUse"
            x1={c.from[0]} y1={c.from[1]}
            x2={c.to[0]}   y2={c.to[1]}
          >
            <stop offset="0%"   stopColor={c.color} stopOpacity="0.35" />
            <stop offset="50%"  stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="0.55" />
            <stop offset="100%" stopColor={c.color} stopOpacity="0.35" />
          </linearGradient>
        ))}
        <filter id="ec-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {CORNERS.map(c => (
        <path
          key={c.id}
          id={`ec-path-${c.id}`}
          d={buildPath(c.from, c.to)}
          fill="none"
          stroke={`url(#ec-grad-${c.id})`}
          strokeWidth="1.2"
          opacity="0.45"
          filter="url(#ec-glow)"
        />
      ))}

      {pulses.map(p => {
        const corner = CORNERS.find(c => c.id === p.cornerId)
        if (!corner) return null
        return (
          <circle key={p.id} r="3" fill={corner.color} filter="url(#ec-glow)">
            <animateMotion dur="800ms" fill="freeze" rotate="auto">
              <mpath href={`#ec-path-${p.cornerId}`} />
            </animateMotion>
            <animate attributeName="opacity" from="1" to="0" dur="800ms" fill="freeze" />
            <animate attributeName="r" from="3" to="6" dur="800ms" fill="freeze" />
          </circle>
        )
      })}

      <style>{`
        @keyframes ec-permanent-pulse { 0%, 100% { opacity: 0.35; } 50% { opacity: 0.55; } }
        .ec-svg path { animation: ec-permanent-pulse 6s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) { .ec-svg path { animation: none; } }
      `}</style>
    </svg>
  )
}

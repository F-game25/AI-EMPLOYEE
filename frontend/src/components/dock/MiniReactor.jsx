/**
 * MiniReactor — compact cognitive core for CommandDock.
 * Iris core + single thin ring, no chrome. ~120 LOC.
 *
 * Props:
 *   state  string  IDLE | LISTENING | THINKING | EXECUTING | ERROR
 *   size   number  px (default 72)
 */
const STATE_COLOR = {
  IDLE:      { core: '#22d3ee', halo: '#22d3ee', spin: '32s' },
  LISTENING: { core: '#22d3ee', halo: '#fbbf24', spin: '20s' },
  THINKING:  { core: '#a855f7', halo: '#a855f7', spin: '12s' },
  EXECUTING: { core: '#fbbf24', halo: '#fbbf24', spin: '8s'  },
  ERROR:     { core: '#ef4444', halo: '#ef4444', spin: '6s'  },
}

export default function MiniReactor({ state = 'IDLE', size = 72 }) {
  const cfg = STATE_COLOR[state] || STATE_COLOR.IDLE
  const r = 50

  return (
    <div
      className="mr-root"
      style={{ width: size, height: size, '--mr-spin': cfg.spin }}
      role="img"
      aria-label={`Mini reactor — ${state.toLowerCase()}`}
    >
      <svg viewBox="-60 -60 120 120" className="mr-svg">
        <defs>
          <radialGradient id="mr-core-grad" cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="#ffffff" stopOpacity="0.95" />
            <stop offset="30%"  stopColor={cfg.core} stopOpacity="0.85" />
            <stop offset="70%"  stopColor={cfg.core} stopOpacity="0.35" />
            <stop offset="100%" stopColor={cfg.core} stopOpacity="0" />
          </radialGradient>
          <linearGradient id="mr-ring-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%"   stopColor="#1a1a24" />
            <stop offset="100%" stopColor="#0a0a14" />
          </linearGradient>
          <filter id="mr-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Outer mechanical ring */}
        <circle cx="0" cy="0" r={r} fill="url(#mr-ring-grad)" stroke={cfg.halo} strokeOpacity="0.35" strokeWidth="1.2" />

        {/* Thin animated halo ring */}
        <g className="mr-halo">
          <circle
            cx="0" cy="0" r={r - 4}
            fill="none"
            stroke={cfg.halo}
            strokeOpacity="0.55"
            strokeWidth="0.8"
            strokeDasharray="4 3"
          />
        </g>

        {/* Plasma core */}
        <circle cx="0" cy="0" r={r - 12} fill="url(#mr-core-grad)" filter="url(#mr-glow)" />

        {/* Pupil slit */}
        <rect x="-1" y={-(r - 18)} width="2" height={(r - 18) * 2} fill="#0a0a14" opacity="0.85" rx="1" />

        {/* Small focal triangle */}
        <polygon points={`0,${-(r - 22)} 3,${-(r - 28)} -3,${-(r - 28)}`} fill={cfg.core} opacity="0.9" />
      </svg>

      <style>{`
        .mr-root { position: relative; display: inline-block; }
        .mr-svg { width: 100%; height: 100%; display: block; }
        .mr-halo { transform-origin: 0 0; animation: mr-halo-spin var(--mr-spin, 20s) linear infinite; }
        @keyframes mr-halo-spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) { .mr-halo { animation: none; } }
      `}</style>
    </div>
  )
}

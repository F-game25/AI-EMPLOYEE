/**
 * ScanSweep — Z6 dual radar-style rotating arcs at r=200 and r=280.
 * Speed + opacity respond to state; respects reduced motion.
 */
export default function ScanSweep({ state = 'idle' }) {
  const stateLower = String(state).toLowerCase()
  return (
    <svg
      viewBox="-300 -300 600 600"
      className={`ss-sweep ss-sweep--${stateLower}`}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="ss-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="0" />
          <stop offset="50%"  stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="0.85" />
          <stop offset="100%" stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="0" />
        </linearGradient>
      </defs>

      <g className="ss-arc-group ss-arc-primary">
        <path
          d="M 200 0 A 200 200 0 0 1 -141 141"
          fill="none"
          stroke="url(#ss-grad)"
          strokeWidth="1.6"
        />
      </g>
      <g className="ss-arc-group ss-arc-secondary" style={{ animationDelay: '-1s' }}>
        <path
          d="M 280 0 A 280 280 0 0 1 -198 198"
          fill="none"
          stroke="url(#ss-grad)"
          strokeWidth="1.0"
          strokeOpacity="0.5"
        />
      </g>

      <style>{`
        .ss-arc-group {
          transform-origin: center;
          transform-box: view-box;
          animation: ss-rotate 8s linear infinite;
          will-change: transform;
        }
        .ss-sweep--idle      .ss-arc-group { animation-duration: 16s; opacity: 0.45; }
        .ss-sweep--listening .ss-arc-group { animation-duration: 10s; opacity: 0.7;  }
        .ss-sweep--thinking  .ss-arc-group { animation-duration: 7s;  opacity: 0.85; }
        .ss-sweep--executing .ss-arc-group { animation-duration: 4s;  opacity: 0.95; }
        .ss-sweep--error     .ss-arc-group { animation-duration: 6s;  opacity: 0.85; filter: hue-rotate(-90deg); }
        @keyframes ss-rotate {
          from { transform: rotate(0deg);   }
          to   { transform: rotate(360deg); }
        }
        @media (prefers-reduced-motion: reduce) {
          .ss-arc-group { animation: none !important; }
        }
      `}</style>
    </svg>
  )
}

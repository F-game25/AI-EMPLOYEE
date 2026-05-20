/**
 * EnergyField — Z0 volumetric warm background gradient.
 * Pure DOM + CSS; state-aware filter shifts.
 */
export default function EnergyField({ state = 'idle' }) {
  const s = String(state).toLowerCase()
  return (
    <div className={`ef-field ef-field--${s}`} aria-hidden="true">
      <style>{`
        .ef-field {
          position: absolute; inset: 0;
          pointer-events: none;
          background:
            radial-gradient(circle at 50% 50%, rgba(245,158,11,0.18) 0%, transparent 35%),
            radial-gradient(circle at 50% 50%, rgba(220,38,38,0.06) 5%, transparent 50%),
            radial-gradient(ellipse at 50% 60%, rgba(15,23,42,0.4) 40%, rgba(0,0,0,0.85) 100%);
          filter: blur(8px);
          opacity: 0.95;
          animation: ef-breathe 12s ease-in-out infinite;
          will-change: opacity, filter;
        }
        .ef-field--listening { filter: blur(8px) saturate(1.15); }
        .ef-field--thinking  { filter: blur(8px) hue-rotate(40deg); }
        .ef-field--executing { filter: blur(6px) saturate(1.3); }
        .ef-field--error     { filter: blur(8px) hue-rotate(-30deg) saturate(1.5); }
        @keyframes ef-breathe {
          0%, 100% { opacity: 0.88; }
          50%      { opacity: 1.0;  }
        }
        @media (prefers-reduced-motion: reduce) {
          .ef-field { animation: none !important; }
        }
      `}</style>
    </div>
  )
}

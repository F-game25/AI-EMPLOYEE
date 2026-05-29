/**
 * NebulaFog — Z2 slow-rotating multi-hue nebula tint.
 * Conic gradient + heavy blur, screen-blended atop EnergyField.
 */
export default function NebulaFog() {
  return (
    <div className="nf-fog" aria-hidden="true">
      <style>{`
        .nf-fog {
          position: absolute;
          inset: 10% 10% 10% 10%;
          pointer-events: none;
          background: conic-gradient(from 0deg at 50% 50%,
            rgba(245,158,11,0.08)   0deg,
            rgba(14,116,144,0.06)  90deg,
            rgba(168,85,247,0.04) 180deg,
            rgba(245,158,11,0.08) 270deg,
            rgba(245,158,11,0.08) 360deg);
          filter: blur(40px);
          animation: nf-rotate 180s linear infinite;
          opacity: 0.6;
          mix-blend-mode: screen;
          will-change: transform;
        }
        @keyframes nf-rotate {
          from { transform: rotate(0deg);   }
          to   { transform: rotate(360deg); }
        }
        @media (prefers-reduced-motion: reduce) {
          .nf-fog { animation: none !important; }
        }
      `}</style>
    </div>
  )
}

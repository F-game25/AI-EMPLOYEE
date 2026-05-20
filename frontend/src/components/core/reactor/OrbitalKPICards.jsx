function formatNum(n) {
  if (n == null) return '—'
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  return String(Math.round(n))
}

const CARDS = [
  { pos: 'n', label: 'REASONING SHARDS', accent: '#a855f7' },
  { pos: 'e', label: 'TOKENS / SEC',     accent: '#fbbf24' },
  { pos: 's', label: 'CONTEXT DEPTH',    accent: '#22d3ee' },
  { pos: 'w', label: 'MEMORY WRITES',    accent: '#22c55e' },
]

export default function OrbitalKPICards({
  reasoningCount = 0,
  tokensRate = 0,
  contextDepth = 0,
  memoryRate = 0,
}) {
  const values = {
    n: formatNum(reasoningCount),
    e: formatNum(tokensRate),
    s: formatNum(contextDepth),
    w: `${formatNum(memoryRate)}/s`,
  }
  return (
    <div className="okc-root" aria-hidden="false">
      {CARDS.map(c => (
        <div
          key={c.pos}
          className={`okc-card okc-card--${c.pos}`}
          style={{ '--card-accent': c.accent }}
          role="status"
          aria-label={`${c.label}: ${values[c.pos]}`}
        >
          <div className="okc-card__label">{c.label}</div>
          <div className="okc-card__value">{values[c.pos]}</div>
          <div className="okc-card__chevron" aria-hidden="true">▸</div>
        </div>
      ))}
      <style>{`
        .okc-root { position: absolute; inset: 0; pointer-events: none; }
        .okc-card {
          position: absolute;
          min-width: 168px;
          padding: 10px 14px;
          background: rgba(13,13,24,0.78);
          border: 1px solid color-mix(in srgb, var(--card-accent) 50%, transparent);
          border-left: 3px solid var(--card-accent);
          border-radius: 4px;
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          box-shadow:
            0 0 14px rgba(0,0,0,0.7),
            inset 0 0 10px color-mix(in srgb, var(--card-accent) 12%, transparent);
          animation: okc-pulse 4s ease-in-out infinite;
          pointer-events: auto;
        }
        .okc-card--n { top: 0;    left: 50%; transform: translateX(-50%); }
        .okc-card--s { bottom: 0; left: 50%; transform: translateX(-50%); }
        .okc-card--e { right: 0;  top: 50%;  transform: translateY(-50%); }
        .okc-card--w { left: 0;   top: 50%;  transform: translateY(-50%); }
        .okc-card__label {
          font-family: 'JetBrains Mono', monospace;
          font-size: 8px;
          color: rgba(255,255,255,0.55);
          letter-spacing: 1.5px;
          margin-bottom: 4px;
        }
        .okc-card__value {
          font-family: 'JetBrains Mono', monospace;
          font-size: 24px;
          font-weight: 700;
          color: var(--card-accent);
          text-shadow: 0 0 10px color-mix(in srgb, var(--card-accent) 60%, transparent);
          line-height: 1;
        }
        .okc-card__chevron {
          position: absolute; top: 8px; right: 8px;
          color: var(--card-accent); opacity: 0.4; font-size: 10px;
        }
        @keyframes okc-pulse {
          0%, 100% {
            box-shadow:
              0 0 14px rgba(0,0,0,0.7),
              inset 0 0 10px color-mix(in srgb, var(--card-accent) 12%, transparent);
          }
          50% {
            box-shadow:
              0 0 22px color-mix(in srgb, var(--card-accent) 28%, transparent),
              inset 0 0 14px color-mix(in srgb, var(--card-accent) 22%, transparent);
          }
        }
        @media (prefers-reduced-motion: reduce) { .okc-card { animation: none; } }
      `}</style>
    </div>
  )
}

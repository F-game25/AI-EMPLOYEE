import './AIAvatar.css'

// Pure SVG animated glyph — no JS animation loops
// State controlled via data-state attribute → CSS handles transitions
export default function AvatarGlyph({ state = 'idle' }) {
  return (
    <div className="avatar-glyph" data-state={state}>
      <svg viewBox="0 0 160 160" width="160" height="160" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="avatar-glow">
            <feGaussianBlur stdDeviation="2.5" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <linearGradient id="avatar-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#20D6C7"/>
            <stop offset="100%" stopColor="#9333EA"/>
          </linearGradient>
        </defs>

        {/* Outermost ring — slowest rotation */}
        <circle
          className="avatar-ring avatar-ring--outer"
          cx="80" cy="80" r="72"
          stroke="url(#avatar-grad)"
          strokeWidth="0.6"
          fill="none"
          strokeDasharray="12 6"
        />

        {/* Middle ring */}
        <circle
          className="avatar-ring avatar-ring--mid"
          cx="80" cy="80" r="56"
          stroke="#20D6C7"
          strokeWidth="0.8"
          fill="none"
          strokeDasharray="4 12"
          opacity="0.6"
        />

        {/* Inner ring */}
        <circle
          className="avatar-ring avatar-ring--inner"
          cx="80" cy="80" r="40"
          stroke="#9333EA"
          strokeWidth="1"
          fill="none"
          strokeDasharray="8 4"
          opacity="0.5"
        />

        {/* Core background */}
        <circle
          cx="80" cy="80" r="28"
          fill="#070910"
          opacity="0.92"
        />

        {/* Hexagonal eye — the "face" of the AI */}
        <polygon
          className="avatar-eye"
          points="80,54 97,64 97,84 80,94 63,84 63,64"
          fill="none"
          stroke="url(#avatar-grad)"
          strokeWidth="1.2"
          filter="url(#avatar-glow)"
        />

        {/* Inner eye dot */}
        <circle
          className="avatar-pupil"
          cx="80" cy="74"
          r="5"
          fill="url(#avatar-grad)"
        />

        {/* Corner accent marks */}
        {[[80,22],[22,80],[80,138],[138,80]].map(([cx,cy], i) => (
          <circle key={i} cx={cx} cy={cy} r="2" fill="#20D6C7" opacity="0.5"
            className="avatar-accent"
            style={{ animationDelay: `${i * 0.3}s` }}
          />
        ))}
      </svg>
    </div>
  )
}

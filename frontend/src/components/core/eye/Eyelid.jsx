/* ─────────────────────────────────────────────────────────────────────────
 * Eyelid.jsx
 * ----------
 * Upper + lower eyelid SVG group rendered inside RoboticEye's main SVG
 * (viewBox -120 -120 240 240). Closes vertically on blink driven by the
 * `--eyelid-close` CSS var (0 = open, 1 = closed). Parent owns timing.
 * ──────────────────────────────────────────────────────────────────────── */

export default function Eyelid({ blinkPhase = 0 }) {
  return (
    <g className="el-root" style={{ '--eyelid-close': blinkPhase }}>
      {/* Upper lid — fills from top edge down to the iris meet line.
          Curve = inverse almond top so when scaleY=1 it caps the iris. */}
      <path
        className="el-upper"
        d="M -120 -120 L 120 -120 L 120 -55 Q 0 -45 -120 -55 Z"
        fill="#000"
      />
      <path
        className="el-upper-edge"
        d="M -120 -55 Q 0 -45 120 -55"
        fill="none"
        stroke="var(--eye-halo-color, #FFD27A)"
        strokeWidth="1.5"
        strokeOpacity="0.5"
      />
      {/* Lower lid — mirror, fills from bottom edge up to meet upper lid. */}
      <path
        className="el-lower"
        d="M -120 120 L 120 120 L 120 -5 Q 0 -15 -120 -5 Z"
        fill="#000"
      />
      <path
        className="el-lower-edge"
        d="M -120 -5 Q 0 -15 120 -5"
        fill="none"
        stroke="var(--eye-halo-color, #FFD27A)"
        strokeWidth="1.5"
        strokeOpacity="0.5"
      />
    </g>
  )
}

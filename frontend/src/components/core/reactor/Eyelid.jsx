/* ─────────────────────────────────────────────────────────────────────────
 * Eyelid.jsx (reactor edition)
 * ----------------------------
 * Adapted from frontend/src/components/core/eye/Eyelid.jsx — same SVG paths,
 * same props, same behavior. Wrapped in a standalone <svg> root because the
 * reactor uses absolutely positioned DOM layers rather than a single nested
 * SVG tree. viewBox preserved as -120 -120 240 240 so the path geometry from
 * the original file works unchanged.
 *
 * Closes vertically on blink driven by the `--eyelid-close` CSS var
 * (0 = open, 1 = closed). Parent owns timing.
 * ──────────────────────────────────────────────────────────────────────── */

export default function Eyelid({ blinkPhase = 0 }) {
  return (
    <svg
      className="el-svg"
      viewBox="-120 -120 240 240"
      width="100%"
      height="100%"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
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
    </svg>
  )
}

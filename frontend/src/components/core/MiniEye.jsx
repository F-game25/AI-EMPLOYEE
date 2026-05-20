import { useEffect, useRef, useState } from 'react'
import { useRouteTheme } from '../../theme/routeThemes'
import './MiniEye.css'

const ROUTE_LABELS = {
  gold:   'MAIN',
  cyan:   'MEMORY',
  green:  'LEARNING',
  purple: 'SECURITY',
  red:    'CRITICAL',
  gray:   'OFFLINE',
}

/**
 * MiniEye — 22px route-aware eye for topbar / secondary surfaces.
 * Consumes useRouteTheme() — changes color with 200ms transition.
 * On critical: 100ms switch + 1.2Hz pulse.
 * On offline: gray + 65% opacity + frozen.
 */
export default function MiniEye({ size = 22, className = '', onClick }) {
  const theme = useRouteTheme()
  const [label, setLabel] = useState(null)
  const prevKey = useRef(theme.key)
  const labelTimer = useRef(null)

  // Show label for 1.5s on theme change
  useEffect(() => {
    if (prevKey.current === theme.key) return
    prevKey.current = theme.key
    clearTimeout(labelTimer.current)
    setLabel(ROUTE_LABELS[theme.key] || theme.key.toUpperCase())
    labelTimer.current = setTimeout(() => setLabel(null), 1500)
    return () => clearTimeout(labelTimer.current)
  }, [theme.key])

  const isCritical = theme.key === 'red'
  const isOffline  = theme.key === 'gray'

  const outerCls = [
    'mini-eye',
    isCritical && 'mini-eye--critical',
    isOffline  && 'mini-eye--offline',
    className,
  ].filter(Boolean).join(' ')

  return (
    <div
      className={outerCls}
      style={{ width: size, height: size }}
      onClick={onClick}
      title={`${(ROUTE_LABELS[theme.key] || theme.key).toUpperCase()} — ${isCritical ? 'CRITICAL ALERT' : isOffline ? 'OFFLINE' : 'ACTIVE'}`}
    >
      <svg
        viewBox="-12 -8 24 16"
        width={size}
        height={size * 0.67}
        style={{
          '--eye-iris-color': theme.iris,
          '--eye-halo-color': theme.halo,
          overflow: 'visible',
        }}
      >
        <defs>
          <radialGradient id="me-iris" cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="#fff8e7" stopOpacity="0.9" />
            <stop offset="30%"  stopColor="var(--eye-iris-color, #e5c76b)" />
            <stop offset="75%"  stopColor="var(--eye-iris-color, #e5c76b)" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#1a1000" />
          </radialGradient>
          <radialGradient id="me-cornea" cx="45%" cy="30%" r="55%">
            <stop offset="0%"  stopColor="rgba(150,220,255,0.55)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
          {/* almond clip */}
          <clipPath id="me-almond">
            <ellipse cx="0" cy="0" rx="11" ry="6.8" />
          </clipPath>
        </defs>

        {/* Housing rim */}
        <ellipse cx="0" cy="0" rx="11.5" ry="7.2" fill="#1a1a22" stroke="var(--eye-halo-color, #e5c76b)" strokeWidth="0.5" opacity="0.6" />

        {/* Iris */}
        <g clipPath="url(#me-almond)">
          <ellipse cx="0" cy="0" rx="8" ry="5" fill="url(#me-iris)" />

          {/* 16 reduced vertical fiber lines */}
          {Array.from({ length: 16 }, (_, i) => {
            const angle = (i / 16) * Math.PI
            const x = Math.cos(angle) * 7.5
            return (
              <line
                key={i}
                x1={x} y1="-5" x2={x} y2="5"
                stroke="var(--eye-iris-color, #e5c76b)"
                strokeWidth="0.25"
                opacity="0.25"
              />
            )
          })}

          {/* Inner glow */}
          <ellipse cx="0" cy="0" rx="3" ry="1.8" fill="white" opacity="0.25" />

          {/* Pupil slit */}
          <ellipse cx="0" cy="0" rx="1.2" ry="3.2" fill="#080808" />

          {/* Pulse triangle ▽ in pupil */}
          <polygon
            points="0,-1 1,0.7 -1,0.7"
            fill="var(--eye-iris-color, #e5c76b)"
            opacity="0.85"
            transform="scale(0.7)"
          />

          {/* Cornea specular */}
          <ellipse cx="-1" cy="-2" rx="3.5" ry="2" fill="url(#me-cornea)" style={{ mixBlendMode: 'screen' }} />
        </g>

        {/* Rim glow */}
        <ellipse cx="0" cy="0" rx="11.5" ry="7.2" fill="none"
          stroke="var(--eye-halo-color, #e5c76b)" strokeWidth="0.8"
          opacity="0.45" filter="url(#me-bloom)" />
        <defs>
          <filter id="me-bloom" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
      </svg>

      {label && <span className="mini-eye__label">{label}</span>}
    </div>
  )
}

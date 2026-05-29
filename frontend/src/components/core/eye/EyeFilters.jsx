// EyeFilters.jsx — Surface-realism SVG filter defs for the cognitive eye.
// Returns ONLY <defs> children (a fragment) — meant to be embedded inside
// the parent <svg><defs>...</defs></svg>. All IDs are prefixed `ef-`.
//
// Filters provided:
//   ef-specular       — moving specular highlight, azimuth via CSS var
//   ef-noise          — subtle grayscale surface noise for metal areas
//   ef-chromatic      — 3-channel RGB offset (use mix-blend-mode: screen)
//   ef-heat-shimmer   — animated turbulence displacement (GPU-hot only)
//   ef-glitch         — hard RGB split + scan-line tear (ERROR state)
//
// CSS vars consumed:
//   --ef-light-azimuth (default: 135deg, the consumer may animate toward cursor)

import React from 'react'

export default function EyeFilters() {
  return (
    <>
      {/* ─── (a) Specular highlight ─────────────────────────────────────── */}
      {/* Soft moving spec light; azimuth is driven by a CSS var so the
          consumer can redirect the highlight toward the cursor. */}
      <filter id="ef-specular" x="-20%" y="-20%" width="140%" height="140%">
        <feSpecularLighting
          in="SourceGraphic"
          result="ef-spec-light"
          surfaceScale="3"
          specularConstant="1.2"
          specularExponent="28"
          lightingColor="#fff6dc"
        >
          <feDistantLight
            azimuth="var(--ef-light-azimuth, 135)"
            elevation="55"
          />
        </feSpecularLighting>
        <feComposite
          in="ef-spec-light"
          in2="SourceGraphic"
          operator="in"
          result="ef-spec-clipped"
        />
        <feMerge>
          <feMergeNode in="SourceGraphic" />
          <feMergeNode in="ef-spec-clipped" />
        </feMerge>
      </filter>

      {/* ─── (b) Procedural surface noise ───────────────────────────────── */}
      {/* Low-amplitude grayscale grain to break up perfectly smooth metal. */}
      <filter id="ef-noise" x="0%" y="0%" width="100%" height="100%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.9 0.4"
          numOctaves="2"
          seed="3"
          result="ef-turb"
        />
        <feColorMatrix
          in="ef-turb"
          type="matrix"
          values="0 0 0 0 1
                  0 0 0 0 1
                  0 0 0 0 1
                  0 0 0 0.05 0"
          result="ef-grain"
        />
        <feComposite
          in="ef-grain"
          in2="SourceGraphic"
          operator="in"
          result="ef-grain-clipped"
        />
        <feMerge>
          <feMergeNode in="SourceGraphic" />
          <feMergeNode in="ef-grain-clipped" />
        </feMerge>
      </filter>

      {/* ─── (c) Chromatic aberration ───────────────────────────────────── */}
      {/* 3 stacked offset copies. Consumer should set mix-blend-mode: screen. */}
      <filter id="ef-chromatic" x="-10%" y="-10%" width="120%" height="120%">
        {/* Red channel — shifted -1px on X */}
        <feColorMatrix
          in="SourceGraphic"
          type="matrix"
          values="1 0 0 0 0
                  0 0 0 0 0
                  0 0 0 0 0
                  0 0 0 1 0"
          result="ef-r"
        />
        <feOffset in="ef-r" dx="-1" dy="0" result="ef-r-off" />
        {/* Green channel — centered */}
        <feColorMatrix
          in="SourceGraphic"
          type="matrix"
          values="0 0 0 0 0
                  0 1 0 0 0
                  0 0 0 0 0
                  0 0 0 1 0"
          result="ef-g"
        />
        {/* Blue channel — shifted +1px on X */}
        <feColorMatrix
          in="SourceGraphic"
          type="matrix"
          values="0 0 0 0 0
                  0 0 0 0 0
                  0 0 1 0 0
                  0 0 0 1 0"
          result="ef-b"
        />
        <feOffset in="ef-b" dx="1" dy="0" result="ef-b-off" />
        <feMerge>
          <feMergeNode in="ef-r-off" />
          <feMergeNode in="ef-g" />
          <feMergeNode in="ef-b-off" />
        </feMerge>
      </filter>

      {/* ─── (d) Heat-shimmer displacement ──────────────────────────────── */}
      {/* Animated turbulence + displacement for subtle vertical wobble.
          Parent toggles via class (.re--hot) — keep scale modest. */}
      <filter id="ef-heat-shimmer" x="-10%" y="-10%" width="120%" height="120%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.02 0.04"
          numOctaves="2"
          seed="7"
          result="ef-shimmer-turb"
        >
          <animate
            attributeName="baseFrequency"
            dur="3s"
            values="0.02 0.04;0.04 0.06;0.02 0.04"
            repeatCount="indefinite"
          />
        </feTurbulence>
        <feDisplacementMap
          in="SourceGraphic"
          in2="ef-shimmer-turb"
          scale="2"
          xChannelSelector="R"
          yChannelSelector="G"
        />
      </filter>

      {/* ─── (e) Glitch RGB-split (ERROR only) ──────────────────────────── */}
      {/* Hard 3-way RGB offset + horizontal scan-line tear. */}
      <filter id="ef-glitch" x="-15%" y="-15%" width="130%" height="130%">
        {/* Red — strong +3 / -1 split */}
        <feColorMatrix
          in="SourceGraphic"
          type="matrix"
          values="1 0 0 0 0
                  0 0 0 0 0
                  0 0 0 0 0
                  0 0 0 1 0"
          result="ef-gl-r"
        />
        <feOffset in="ef-gl-r" dx="3" dy="-1" result="ef-gl-r-off" />
        {/* Green — centered */}
        <feColorMatrix
          in="SourceGraphic"
          type="matrix"
          values="0 0 0 0 0
                  0 1 0 0 0
                  0 0 0 0 0
                  0 0 0 1 0"
          result="ef-gl-g"
        />
        {/* Blue — opposite split -3 / +1 */}
        <feColorMatrix
          in="SourceGraphic"
          type="matrix"
          values="0 0 0 0 0
                  0 0 0 0 0
                  0 0 1 0 0
                  0 0 0 1 0"
          result="ef-gl-b"
        />
        <feOffset in="ef-gl-b" dx="-3" dy="1" result="ef-gl-b-off" />
        {/* Scan-line tear: a thin horizontal flood band composited in */}
        <feFlood
          floodColor="#ffffff"
          floodOpacity="0.35"
          result="ef-gl-flood"
        />
        <feComposite
          in="ef-gl-flood"
          in2="SourceGraphic"
          operator="in"
          result="ef-gl-scan"
        />
        <feOffset in="ef-gl-scan" dx="0" dy="2" result="ef-gl-scan-off">
          <animate
            attributeName="dy"
            dur="0.9s"
            values="-30;30;-30"
            repeatCount="indefinite"
          />
        </feOffset>
        <feMerge>
          <feMergeNode in="ef-gl-r-off" />
          <feMergeNode in="ef-gl-g" />
          <feMergeNode in="ef-gl-b-off" />
          <feMergeNode in="ef-gl-scan-off" />
        </feMerge>
      </filter>
    </>
  )
}

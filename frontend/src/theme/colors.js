/**
 * AI Employee — centralized design tokens.
 *
 * Single source of truth for every color, spacing, and animation value.
 * Import these in JavaScript/JSX; the corresponding CSS custom properties
 * in index.css are kept in sync with these values.
 */

// ── Brand ─────────────────────────────────────────────────────────────────
export const GOLD          = '#D4AF37'
export const GOLD_BRIGHT   = '#E8C84A'
export const GOLD_DIM      = '#a38600'
export const GOLD_GRADIENT = 'linear-gradient(135deg, #D4AF37 0%, #E8C84A 60%, #D4AF37 100%)'

// ── Backgrounds ───────────────────────────────────────────────────────────
export const BG_BASE     = '#0B0B0F'
export const BG_CARD     = '#111118'
export const BG_ELEVATED = '#1A1A24'

// ── Borders ───────────────────────────────────────────────────────────────
export const BORDER_SUBTLE   = 'rgba(255, 255, 255, 0.06)'
export const BORDER_GOLD     = 'rgba(212, 175, 55, 0.30)'
export const BORDER_GOLD_DIM = 'rgba(212, 175, 55, 0.10)'

// ── Text ──────────────────────────────────────────────────────────────────
export const TEXT_PRIMARY   = '#EAEAF0'
export const TEXT_SECONDARY = '#9A9AA5'
export const TEXT_MUTED     = '#666670'

// ── Status ────────────────────────────────────────────────────────────────
export const SUCCESS = '#22C55E'
export const WARNING = '#F59E0B'
export const ERROR   = '#EF4444'
export const INFO    = '#60A5FA'

// ── Radius ────────────────────────────────────────────────────────────────
export const RADIUS_SM = '6px'
export const RADIUS_MD = '8px'
export const RADIUS_LG = '16px'
export const RADIUS_XL = '20px'

// ── Spacing (8px grid) ────────────────────────────────────────────────────
export const SPACE = {
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  5: '24px',
  6: '32px',
  8: '48px',
}

// ── Typography ────────────────────────────────────────────────────────────
export const FONT_SANS = "'Inter', system-ui, -apple-system, sans-serif"
export const FONT_MONO = "'JetBrains Mono', monospace"

// ── Transitions ───────────────────────────────────────────────────────────
export const EASE_OUT       = 'cubic-bezier(0.16, 1, 0.3, 1)'
export const DURATION_FAST  = '150ms'
export const DURATION_NORM  = '250ms'

export const Colors = {
  // Core palette — matches dashboard CSS vars
  bg:          '#000000',
  bgDeep:      '#080810',
  surface1:    '#0d0d18',
  surface2:    '#111122',
  surface3:    '#16162a',

  // Accent
  gold:        '#e5c76b',
  goldBright:  '#fbbf24',
  goldDim:     '#b89a3e',
  cyan:        '#22d3ee',
  cyanDim:     '#06b6d4',
  green:       '#22c55e',
  greenDim:    '#10b981',
  purple:      '#d946ef',
  purpleDim:   '#a855f7',
  red:         '#dc2626',
  redDim:      '#991b1b',
  orange:      '#f97316',

  // Text
  text:        '#f4f4f8',
  textMuted:   '#8a8a96',
  textDim:     '#55555f',

  // Borders
  border:      '#1e1e30',
  borderFaint: '#12121e',
  borderGold:  'rgba(229,199,107,0.3)',

  // Status
  success:     '#22c55e',
  warning:     '#f59e0b',
  danger:      '#dc2626',

  // Transparent
  goldGlow:    'rgba(229,199,107,0.15)',
  goldOverlay: 'rgba(229,199,107,0.05)',
} as const

export type ColorKey = keyof typeof Colors

/**
 * Nexus UI — barrel export.
 * Import primitives from a single path: `from '../nexus-ui'`
 */

export { default as Panel } from './Panel'
export { default as HexFrame } from './HexFrame'
export { SectionLabel, LiveBadge, default as SectionLabelDefault } from './SectionLabel'
export { default as Sparkline } from './Sparkline'
export { WaveformStrip } from './WaveformStrip'
export { default as KPITile } from './KPITile'
export { default as StatusPill } from './StatusPill'
export { default as HexButton } from './HexButton'
export { default as NavRailItem } from './NavRailItem'
export { default as CommandPill } from './CommandPill'
export { default as ClockModule } from './ClockModule'

// Phase A — data-lifecycle primitives
export { default as AsyncPanel } from './AsyncPanel'
export { default as LoadingSkeleton } from './LoadingSkeleton'
export { default as EmptyState } from './EmptyState'
export { default as ErrorState } from './ErrorState'
export { default as KPIDelta } from './KPIDelta'
export { default as Toaster, toast, toastSuccess, toastError, toastWarn } from './Toaster'

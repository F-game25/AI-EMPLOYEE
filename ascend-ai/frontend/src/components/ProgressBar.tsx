interface ProgressBarProps {
  value: number
  label: string
  unit?: string
  variant?: 'gold' | 'bronze'
}

export function ProgressBar({ value, label, unit, variant = 'bronze' }: ProgressBarProps) {
  const color = variant === 'gold' ? 'var(--gold)' : 'var(--bronze)'
  const clamped = Math.min(Math.max(value, 0), 100)

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1 }}>
          {label}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color }}>
          {Math.round(clamped)}{unit || '%'}
        </span>
      </div>
      <div style={{ height: 4, background: 'rgba(212,175,55,0.08)', borderRadius: 2 }}>
        <div style={{
          height: '100%',
          width: `${clamped}%`,
          background: color,
          borderRadius: 2,
          transition: 'width 0.5s ease',
          boxShadow: `0 0 8px ${color}44`,
        }} />
      </div>
    </div>
  )
}

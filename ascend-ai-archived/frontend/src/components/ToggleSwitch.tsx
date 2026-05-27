interface ToggleSwitchProps {
  value: string
  onChange: (v: string) => void
}

const OPTIONS = ['off', 'on', 'auto'] as const

export function ToggleSwitch({ value, onChange }: ToggleSwitchProps) {
  return (
    <div style={{ display: 'flex', gap: 0, borderRadius: 6, overflow: 'hidden', border: 'var(--border-gold)' }}>
      {OPTIONS.map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          style={{
            padding: '6px 14px',
            background: value === opt ? 'var(--gold)' : 'transparent',
            color: value === opt ? '#0A0A0A' : 'var(--text-dim)',
            border: 'none',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            fontWeight: 700,
            cursor: 'pointer',
            letterSpacing: 1,
            textTransform: 'uppercase',
          }}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}

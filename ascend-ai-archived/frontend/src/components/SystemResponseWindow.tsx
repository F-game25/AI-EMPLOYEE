import { useEffect, useRef } from 'react'

interface SystemResponseWindowProps {
  title: string
  lines: string[]
  active: boolean
  accentColor?: 'gold' | 'bronze'
}

export function SystemResponseWindow({ title, lines, active, accentColor = 'bronze' }: SystemResponseWindowProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const color = accentColor === 'gold' ? 'var(--gold)' : 'var(--bronze)'

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lines])

  return (
    <div className="panel" style={{
      border: active ? `1px solid ${accentColor === 'gold' ? 'rgba(212,175,55,0.3)' : 'rgba(205,127,50,0.3)'}` : 'var(--border-gold)',
    }}>
      <div style={{
        padding: '10px 16px',
        borderBottom: 'var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        <span className={`dot ${active ? 'online' : 'offline'}`} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color, letterSpacing: 1 }}>{title}</span>
      </div>
      <div
        ref={scrollRef}
        style={{
          height: 200,
          overflowY: 'auto',
          padding: 16,
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          lineHeight: 1.8,
          color: 'var(--text-secondary)',
        }}
      >
        {lines.map((line, i) => (
          <div key={i} style={{
            color: line.includes('ERROR') ? 'var(--offline)' : line.includes('WARN') ? 'var(--warning)' : 'var(--text-secondary)',
          }}>
            {line}
          </div>
        ))}
      </div>
    </div>
  )
}

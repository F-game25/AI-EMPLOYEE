import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'

interface ModeButtonProps {
  icon: string
  name: string
  description: string
  status: 'online' | 'offline' | 'starting'
  route: string
}

export function ModeButton({ icon, name, description, status, route }: ModeButtonProps) {
  const nav = useNavigate()

  return (
    <motion.div
      onClick={() => nav(route)}
      whileHover={{ scale: 1.01, boxShadow: 'var(--glow-gold)' }}
      whileTap={{ scale: 0.98 }}
      className="panel"
      style={{
        padding: 16,
        marginBottom: 12,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
      }}
    >
      <span style={{ fontSize: 24 }}>{icon}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: 0.5 }}>
          {name}
        </div>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
          {description}
        </div>
      </div>
      <span className={`dot ${status}`} />
    </motion.div>
  )
}

import { useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../store/appStore'

export default function LoginScreen() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const login = useAppStore(s => s.login)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!username.trim()) return
    setLoading(true)
    setTimeout(() => login(username || 'operator'), 1000)
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 flex items-center justify-center"
      style={{ background: '#050505' }}
    >
      {/* Scanlines */}
      <div className="scanlines" />

      {/* Glow background */}
      <div
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at 50% 50%, rgba(245,196,0,0.04) 0%, transparent 70%)',
        }}
      />

      <motion.div
        initial={{ scale: 0.9, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.4, ease: 'easeOut' }}
        className="relative w-full max-w-md p-8"
        style={{
          background: 'rgba(10,10,10,0.95)',
          border: '1px solid rgba(245,196,0,0.3)',
          borderRadius: '8px',
          boxShadow: '0 0 60px rgba(245,196,0,0.15), 0 0 120px rgba(245,196,0,0.05)',
        }}
      >
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="font-mono text-xs mb-3" style={{ color: '#F5C400', letterSpacing: '4px' }}>
            AI-EMPLOYEE OS
          </div>
          <h1 className="text-2xl font-semibold mb-1" style={{ color: '#e8e8e8' }}>
            Welcome back
          </h1>
          <p className="text-sm" style={{ color: '#555' }}>
            Authenticate to access the system
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block font-mono text-xs mb-2" style={{ color: '#666', letterSpacing: '1px' }}>
              OPERATOR ID
            </label>
            <div className="input-field-wrap">
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="operator"
                className="w-full font-mono text-sm px-4 py-3 outline-none transition-all duration-200"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: '4px',
                  color: '#e8e8e8',
                }}
              />
            </div>
          </div>
          <div>
            <label className="block font-mono text-xs mb-2" style={{ color: '#666', letterSpacing: '1px' }}>
              ACCESS CODE
            </label>
            <div className="input-field-wrap">
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full font-mono text-sm px-4 py-3 outline-none transition-all duration-200"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: '4px',
                  color: '#e8e8e8',
                }}
              />
            </div>
          </div>

          <motion.button
            type="submit"
            disabled={loading}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            className="w-full font-mono text-sm py-3 mt-2 font-semibold tracking-widest transition-all duration-200"
            style={{
              background: loading ? 'rgba(245,196,0,0.1)' : 'rgba(245,196,0,0.15)',
              border: '1px solid rgba(245,196,0,0.5)',
              borderRadius: '4px',
              color: '#F5C400',
              cursor: loading ? 'not-allowed' : 'pointer',
              boxShadow: loading ? 'none' : '0 0 20px rgba(245,196,0,0.2)',
            }}
          >
            {loading ? 'AUTHENTICATING...' : 'ACCESS SYSTEM'}
          </motion.button>
        </form>

        {/* Corner decorations */}
        <div className="absolute top-3 left-3 w-3 h-3" style={{ borderTop: '1px solid #F5C400', borderLeft: '1px solid #F5C400' }} />
        <div className="absolute top-3 right-3 w-3 h-3" style={{ borderTop: '1px solid #F5C400', borderRight: '1px solid #F5C400' }} />
        <div className="absolute bottom-3 left-3 w-3 h-3" style={{ borderBottom: '1px solid #F5C400', borderLeft: '1px solid #F5C400' }} />
        <div className="absolute bottom-3 right-3 w-3 h-3" style={{ borderBottom: '1px solid #F5C400', borderRight: '1px solid #F5C400' }} />
      </motion.div>
    </motion.div>
  )
}

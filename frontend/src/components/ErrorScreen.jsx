import { motion } from 'framer-motion'
import { useAppStore } from '../store/appStore'

export default function ErrorScreen() {
  const { errorMessage, setAppState } = useAppStore()

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 flex items-center justify-center"
      style={{ background: '#050505' }}
    >
      <div className="text-center max-w-md px-8">
        <div className="font-mono text-5xl mb-4" style={{ color: '#ff3366' }}>⚠</div>
        <div className="font-mono text-xl font-bold mb-2" style={{ color: '#ff3366' }}>
          SYSTEM ERROR
        </div>
        <p className="font-mono text-sm mb-6" style={{ color: '#666' }}>
          {errorMessage || 'Connection to backend failed'}
        </p>
        <button
          onClick={() => setAppState('boot')}
          className="font-mono text-sm px-6 py-2"
          style={{
            border: '1px solid rgba(255,51,102,0.5)',
            color: '#ff3366',
            background: 'rgba(255,51,102,0.1)',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          RETRY
        </button>
      </div>
    </motion.div>
  )
}

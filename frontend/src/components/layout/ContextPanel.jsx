import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

export default function ContextPanel() {
  const contextPanel = useAppStore(s => s.contextPanel)
  const closeContextPanel = useAppStore(s => s.closeContextPanel)

  return (
    <AnimatePresence>
      {contextPanel && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeContextPanel}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.3)',
              zIndex: 'var(--z-panel)',
            }}
          />
          {/* Panel */}
          <motion.aside
            initial={{ x: 380 }}
            animate={{ x: 0 }}
            exit={{ x: 380 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="context-panel"
            style={{ zIndex: 51 }}
          >
            <div style={{
              padding: 'var(--space-4)',
              borderBottom: '1px solid var(--border-subtle)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <h3 style={{ fontSize: '14px', fontWeight: 500 }}>
                {contextPanel.title || 'Details'}
              </h3>
              <button
                onClick={closeContextPanel}
                className="btn-secondary"
                style={{ padding: '4px 8px', fontSize: '12px' }}
              >
                ✕
              </button>
            </div>
            <div style={{ padding: 'var(--space-4)' }}>
              {contextPanel.content}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

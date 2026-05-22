import { Component } from 'react'

const RELOAD_FLAG_KEY = 'nx:reload-once-on-chunk-error'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info.componentStack)
    try {
      window.ai?.notifyUiFailed?.({
        message: `${this.props.label || 'Application'} failed to render: ${error?.message || 'Unknown error'}`,
        severity: this.props.severity || 'fatal',
        stack: error?.stack,
        componentStack: info?.componentStack,
      })
    } catch {
      // Recovery still renders locally if Electron IPC is unavailable.
    }
    // Stale-chunk auto-recovery: if a lazy import 404s, reload exactly once.
    // sessionStorage ensures we don't loop on a real error.
    const msg = error?.message || ''
    const isChunkError = /Failed to fetch dynamically imported module|Loading chunk|Loading CSS chunk|Importing a module script failed/i.test(msg)
    if (isChunkError && !sessionStorage.getItem(RELOAD_FLAG_KEY)) {
      sessionStorage.setItem(RELOAD_FLAG_KEY, '1')
      window.location.reload()
    }
  }

  render() {
    if (!this.state.hasError) {
      // Successful render — clear the reload-once flag so future stale chunks can recover too.
      if (sessionStorage.getItem(RELOAD_FLAG_KEY)) sessionStorage.removeItem(RELOAD_FLAG_KEY)
      return this.props.children
    }

    // Caller-supplied fallback (e.g. a 2D graph when the 3D renderer throws).
    if (this.props.fallback !== undefined) return this.props.fallback

    const label = this.props.label || 'component'
    const msg = this.state.error?.message || 'Unknown error'
    // Stale chunk after rebuild — hard reload fetches fresh index.html + new hashes
    const isChunkError = /Failed to fetch dynamically imported module|Loading chunk|Loading CSS chunk/i.test(msg)
    const canReturnToLauncher = typeof window !== 'undefined' && window.ai?.returnToLauncher

    return (
      <div style={{
        padding: '24px',
        margin: '12px',
        background: 'rgba(255,60,60,0.08)',
        border: '1px solid rgba(255,60,60,0.3)',
        borderRadius: '10px',
        fontFamily: 'var(--nx-font-mono, monospace)',
        color: 'var(--text-dim, #aaa)',
      }}>
        <div style={{ color: '#f87171', fontWeight: 600, marginBottom: 8 }}>
          ⚠ {label} failed to render
        </div>
        <div style={{ fontSize: 12, marginBottom: 16, opacity: 0.7 }}>
          {isChunkError ? 'App was updated — reload to get the latest version.' : msg}
        </div>
        <button
          onClick={() => isChunkError ? window.location.reload() : this.setState({ hasError: false, error: null })}
          style={{
            padding: '6px 16px',
            background: 'rgba(229,199,107,0.15)',
            border: '1px solid rgba(229,199,107,0.4)',
            borderRadius: 6,
            color: 'var(--gold, #E5C76B)',
            cursor: 'pointer',
            fontFamily: 'inherit',
            fontSize: 12,
          }}
        >
          {isChunkError ? 'Reload App' : 'Retry'}
        </button>
        <button
          onClick={() => window.location.reload()}
          style={{
            marginLeft: 8,
            padding: '6px 16px',
            background: 'transparent',
            border: '1px solid rgba(32,214,199,0.32)',
            borderRadius: 6,
            color: '#20D6C7',
            cursor: 'pointer',
            fontFamily: 'inherit',
            fontSize: 12,
          }}
        >
          Reload
        </button>
        {canReturnToLauncher && (
          <button
            onClick={() => window.ai.returnToLauncher()}
            style={{
              marginLeft: 8,
              padding: '6px 16px',
              background: 'transparent',
              border: '1px solid rgba(229,199,107,0.32)',
              borderRadius: 6,
              color: 'var(--gold, #E5C76B)',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: 12,
            }}
          >
            Return to Launcher
          </button>
        )}
      </div>
    )
  }
}

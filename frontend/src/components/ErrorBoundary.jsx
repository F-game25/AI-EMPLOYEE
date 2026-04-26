import { Component } from 'react'

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
  }

  render() {
    if (!this.state.hasError) return this.props.children

    const label = this.props.label || 'component'
    const msg = this.state.error?.message || 'Unknown error'

    return (
      <div style={{
        padding: '24px',
        margin: '12px',
        background: 'rgba(255,60,60,0.08)',
        border: '1px solid rgba(255,60,60,0.3)',
        borderRadius: '10px',
        fontFamily: 'var(--font-mono, monospace)',
        color: 'var(--text-dim, #aaa)',
      }}>
        <div style={{ color: '#f87171', fontWeight: 600, marginBottom: 8 }}>
          ⚠ {label} failed to render
        </div>
        <div style={{ fontSize: 12, marginBottom: 16, opacity: 0.7 }}>{msg}</div>
        <button
          onClick={() => this.setState({ hasError: false, error: null })}
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
          Retry
        </button>
      </div>
    )
  }
}

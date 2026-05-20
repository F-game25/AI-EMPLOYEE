import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import RingPanel from './RingPanel'

describe('RingPanel Component', () => {
  it('renders with title', () => {
    render(<RingPanel title="Test Ring" />)
    expect(screen.getByText(/TEST RING/i)).toBeInTheDocument()
  })

  it('renders with icon', () => {
    render(<RingPanel title="Brain Ring" icon="brain" />)
    expect(screen.getByText('🧠')).toBeInTheDocument()
  })

  it('renders metrics array', () => {
    const metrics = [
      { label: 'Test Metric', value: 42, unit: 'units' },
    ]
    render(<RingPanel title="Test" metrics={metrics} />)
    expect(screen.getByText(/TEST METRIC/i)).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('units')).toBeInTheDocument()
  })

  it('converts metrics object to array', () => {
    const metrics = {
      'Active Agents': 5,
      'Running Tasks': 12,
    }
    render(<RingPanel title="Test" metrics={metrics} color="cyan" />)
    expect(screen.getByText(/ACTIVE AGENTS/i)).toBeInTheDocument()
    expect(screen.getByText(/RUNNING TASKS/i)).toBeInTheDocument()
  })

  it('displays trend indicators', () => {
    const metrics = [
      { label: 'Revenue', value: 1500, trend: 12.5, color: 'gold' },
      { label: 'Errors', value: 3, trend: -5.2, color: 'red' },
    ]
    render(<RingPanel title="Economy" metrics={metrics} />)
    expect(screen.getByText(/↑/)).toBeInTheDocument()
    expect(screen.getByText(/↓/)).toBeInTheDocument()
  })

  it('supports color variants', () => {
    const { container } = render(<RingPanel title="Test" color="gold" />)
    const panel = container.querySelector('.ring-panel')
    expect(panel).toHaveClass('ring-panel--gold')
  })

  it('handles metric value formatting', () => {
    const metrics = [
      { label: 'Large Number', value: 1500000 },
      { label: 'Small Number', value: 42.567 },
    ]
    render(<RingPanel title="Test" metrics={metrics} />)
    expect(screen.getByText('1.5M')).toBeInTheDocument()
    expect(screen.getByText('42.6')).toBeInTheDocument()
  })

  it('renders empty state when no metrics', () => {
    render(<RingPanel title="Empty" />)
    expect(screen.getByText(/No metrics/i)).toBeInTheDocument()
  })

  it('applies animation class when animated is true', () => {
    const { container } = render(<RingPanel title="Test" animated={true} />)
    const panel = container.querySelector('.ring-panel')
    expect(panel).toHaveClass('ring-panel--animated')
  })

  it('renders with gauge data', () => {
    const { container } = render(
      <RingPanel title="Test" gaugeData={{ value: 75, max: 100 }} />
    )
    expect(container.querySelector('.gauge-container')).toBeInTheDocument()
  })

  it('renders with sparkline data', () => {
    const { container } = render(
      <RingPanel title="Test" sparklineData={[10, 20, 30, 40, 50]} />
    )
    expect(container.querySelector('.sparkline')).toBeInTheDocument()
  })

  it('has fixed dimensions in CSS', () => {
    const { container } = render(<RingPanel title="Test" />)
    const panel = container.querySelector('.ring-panel')
    const styles = window.getComputedStyle(panel)
    expect(styles.width).toBe('280px')
    expect(styles.height).toBe('160px')
  })
})

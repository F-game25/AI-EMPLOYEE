import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ErrorBoundary from '../components/ErrorBoundary'

const Bomb = ({ explode }) => {
  if (explode) throw new Error('Test explosion')
  return <div>All good</div>
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary label="Test">
        <Bomb explode={false} />
      </ErrorBoundary>
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('shows fallback UI when child throws', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary label="Widget">
        <Bomb explode={true} />
      </ErrorBoundary>
    )
    expect(screen.getByText(/Widget failed to render/i)).toBeInTheDocument()
    expect(screen.getByText(/Test explosion/i)).toBeInTheDocument()
    spy.mockRestore()
  })

  it('recovery button resets error state', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    // Mutable flag — change it before clicking Retry so re-render succeeds
    const state = { explode: true }
    const ControlledBomb = () => {
      if (state.explode) throw new Error('Controlled explosion')
      return <div>All good</div>
    }
    render(
      <ErrorBoundary label="Widget">
        <ControlledBomb />
      </ErrorBoundary>
    )
    expect(screen.getByText(/Widget failed to render/i)).toBeInTheDocument()
    state.explode = false
    fireEvent.click(screen.getByText('Retry'))
    expect(screen.getByText('All good')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('shows Electron launcher recovery action when available', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const returnToLauncher = vi.fn()
    const notifyUiFailed = vi.fn()
    window.ai = { returnToLauncher, notifyUiFailed }
    render(
      <ErrorBoundary label="Application">
        <Bomb explode={true} />
      </ErrorBoundary>
    )
    expect(notifyUiFailed).toHaveBeenCalledWith(expect.objectContaining({
      message: expect.stringContaining('Application failed to render'),
    }))
    fireEvent.click(screen.getByText('Return to Launcher'))
    expect(returnToLauncher).toHaveBeenCalled()
    delete window.ai
    spy.mockRestore()
  })

  it('sends configured severity to the launcher', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const notifyUiFailed = vi.fn()
    window.ai = { notifyUiFailed }
    render(
      <ErrorBoundary label="neural-graph" severity="widget">
        <Bomb explode={true} />
      </ErrorBoundary>
    )
    expect(notifyUiFailed).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'widget',
      message: expect.stringContaining('neural-graph failed to render'),
    }))
    delete window.ai
    spy.mockRestore()
  })
})

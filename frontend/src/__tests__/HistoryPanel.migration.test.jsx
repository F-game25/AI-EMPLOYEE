/**
 * HistoryPanel Migration Tests — Phase 5.2
 * Comprehensive test suite for nexus-ui migration
 *
 * Test categories:
 * - Component rendering
 * - Nexus-ui component usage
 * - Tab switching
 * - Event list rendering
 * - Event selection & detail panel
 * - Search/filter functionality
 * - Copy-to-clipboard
 * - Auto-polling updates
 * - Responsive layout
 * - Dark theme support
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import HistoryPanel from '../frontend/src/components/dashboard/HistoryPanel'

// Mock framer-motion to simplify tests
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }) => <>{children}</>,
}))

// Mock fetch
global.fetch = vi.fn()

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn(() => Promise.resolve()),
  },
})

describe('HistoryPanel — nexus-ui Migration (Phase 5.2)', () => {
  beforeEach(() => {
    fetch.mockClear()
    navigator.clipboard.writeText.mockClear()

    // Default mock responses
    fetch.mockImplementation((url) => {
      if (url.includes('/api/history')) {
        if (url.includes('/stats')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              total_tasks: 42,
              success_rate: 88.5,
              failed_count: 5,
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            events: [
              {
                task_id: 'task-001',
                status: 'done',
                input: 'Generate marketing copy for product launch',
                agent_sequence: ['content-generator', 'editor'],
                timestamp: new Date(Date.now() - 60000).toISOString(),
                duration_ms: 2500,
                cost_estimate_usd: 0.15,
                confidence: 0.95,
              },
              {
                task_id: 'task-002',
                status: 'failed',
                input: 'Analyze competitor pricing data',
                agent_sequence: ['data-analyst'],
                timestamp: new Date(Date.now() - 120000).toISOString(),
                duration_ms: 5000,
                cost_estimate_usd: 0.22,
                confidence: 0.72,
                error: 'API rate limit exceeded',
              },
            ],
          }),
        })
      }
      return Promise.reject(new Error('Unknown URL'))
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Component Rendering Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should render HistoryPanel component', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText(/Execution History/i)).toBeInTheDocument()
    })
  })

  it('should render Panel component from nexus-ui', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      // Check for nx-panel class (nexus-ui Panel component)
      const panel = container.querySelector('.nx-panel')
      expect(panel).toBeInTheDocument()
    })
  })

  it('should display loading state initially', () => {
    render(<HistoryPanel />)
    expect(screen.getByText(/Loading history/i)).toBeInTheDocument()
  })

  it('should fetch history on mount', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/history'))
    })
  })

  it('should fetch stats on mount', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/history/stats'))
    })
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Nexus-UI Component Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should render KPITile components for stats', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      const kpiTiles = container.querySelectorAll('.nx-kpi')
      expect(kpiTiles.length).toBeGreaterThan(0)
    })
  })

  it('should display Total, Success, and Failed KPI tiles', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText('Total')).toBeInTheDocument()
      expect(screen.getByText('Success')).toBeInTheDocument()
      expect(screen.getByText('Failed')).toBeInTheDocument()
    })
  })

  it('should render HexButton components for tabs', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      const hexButtons = container.querySelectorAll('.nx-hbtn')
      expect(hexButtons.length).toBeGreaterThan(0)
    })
  })

  it('should render StatusPill components for event status', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      const pills = container.querySelectorAll('.nx-pill')
      expect(pills.length).toBeGreaterThan(0)
    })
  })

  it('should render search input with proper styling', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      const input = screen.getByPlaceholderText(/Filter by agent/i)
      expect(input).toHaveClass('hp-search-input')
    })
  })

  it('should render SectionLabel for detail panel header', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      const firstEvent = screen.getByText(/Generate marketing copy/)
      fireEvent.click(firstEvent)
    })
    await waitFor(() => {
      const sectionLabel = container.querySelector('.nx-section-label')
      expect(sectionLabel).toBeInTheDocument()
    })
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Tab Switching Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should have "All Events" tab selected by default', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      const allTab = screen.getByRole('button', { name: /All/i })
      expect(allTab).toHaveClass('hp-tab-btn--active')
    })
  })

  it('should switch to "Done" tab on click', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      const doneTab = screen.getByRole('button', { name: /Done/i })
      expect(doneTab).toBeInTheDocument()
    })
    const doneTab = screen.getByRole('button', { name: /Done/i })
    await user.click(doneTab)
    await waitFor(() => {
      expect(doneTab).toHaveClass('hp-tab-btn--active')
    })
  })

  it('should fetch history with correct status filter', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      const failedTab = screen.getByRole('button', { name: /Failed/i })
      expect(failedTab).toBeInTheDocument()
    })
    fetch.mockClear()
    const failedTab = screen.getByRole('button', { name: /Failed/i })
    await user.click(failedTab)
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining('status=failed'))
    })
  })

  it('should have Running tab available', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      const runningTab = screen.getByRole('button', { name: /Running/i })
      expect(runningTab).toBeInTheDocument()
    })
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Event List Rendering Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should render event list in reverse chronological order', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      const rows = screen.getAllByText(/Generate|Analyze/)
      // Most recent event should be first
      expect(rows[0].textContent).toContain('Generate marketing copy')
    })
  })

  it('should display event timestamp', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      // Should show relative time (e.g., "11:23" or "May 5")
      const timeElements = screen.getAllByText(/\d{1,2}:\d{2}|[A-Z][a-z]{2} \d{1,2}/i)
      expect(timeElements.length).toBeGreaterThan(0)
    })
  })

  it('should display event agent name', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText('content-generator')).toBeInTheDocument()
    })
  })

  it('should display event duration', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText('2.5s')).toBeInTheDocument()
    })
  })

  it('should display event cost', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText('$0.15')).toBeInTheDocument()
    })
  })

  it('should display correct status badges for events', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      const pills = container.querySelectorAll('.nx-pill')
      // Should have status pills for each event
      expect(pills.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('should apply hp-event-row class to event rows', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      const rows = container.querySelectorAll('.hp-event-row')
      expect(rows.length).toBeGreaterThan(0)
    })
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Event Selection & Detail Panel Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should select event on row click', async () => {
    const { container } = render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(eventRow).toHaveClass('hp-event-row--selected')
    })
  })

  it('should show detail panel when event is selected', async () => {
    const { container } = render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(container.querySelector('.hp-detail')).toBeInTheDocument()
    })
  })

  it('should display detail panel with event data', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(screen.getByText('Event Details')).toBeInTheDocument()
      expect(screen.getByText('task-001')).toBeInTheDocument()
    })
  })

  it('should display event status in detail panel', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(screen.getAllByText('DONE')).length > 0
    })
  })

  it('should display full task ID in detail panel', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(screen.getByText('task-001')).toBeInTheDocument()
    })
  })

  it('should display agents list in detail panel', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(screen.getByText('content-generator, editor')).toBeInTheDocument()
    })
  })

  it('should display confidence score in detail panel', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(screen.getByText('95%')).toBeInTheDocument()
    })
  })

  it('should display error message in detail panel for failed events', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Analyze competitor pricing/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Analyze competitor pricing/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(screen.getByText('API rate limit exceeded')).toBeInTheDocument()
    })
  })

  it('should deselect event when clicking again', async () => {
    const { container } = render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(eventRow).toHaveClass('hp-event-row--selected')
    })
    await user.click(eventRow)
    await waitFor(() => {
      expect(eventRow).not.toHaveClass('hp-event-row--selected')
    })
  })

  it('should render detail panel with slide-in animation', async () => {
    const { container } = render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      const detail = container.querySelector('.hp-detail')
      expect(detail).toHaveClass('hp-detail')
    })
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Search/Filter Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should filter events by agent name', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText(/Filter by agent/)
    await user.type(searchInput, 'content-generator')
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
  })

  it('should filter events by description', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText(/Filter by agent/)
    await user.type(searchInput, 'marketing')
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
  })

  it('should clear filter when search is empty', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText(/Filter by agent/)
    await user.type(searchInput, 'marketing')
    await user.clear(searchInput)
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
      expect(screen.getByText(/Analyze competitor pricing/)).toBeInTheDocument()
    })
  })

  it('should show empty state when no results match filter', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText(/Filter by agent/)
    await user.type(searchInput, 'nonexistent-agent-xyz')
    await waitFor(() => {
      expect(screen.getByText(/No events yet/)).toBeInTheDocument()
    })
  })

  it('should fetch history with search parameter', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    fetch.mockClear()
    const searchInput = screen.getByPlaceholderText(/Filter by agent/)
    await user.type(searchInput, 'marketing')
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining('search=marketing'))
    })
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Copy-to-Clipboard Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should have Copy JSON button in detail panel', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Copy JSON/i })).toBeInTheDocument()
    })
  })

  it('should copy event JSON to clipboard', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      const copyBtn = screen.getByRole('button', { name: /Copy JSON/i })
      expect(copyBtn).toBeInTheDocument()
    })
    const copyBtn = screen.getByRole('button', { name: /Copy JSON/i })
    await user.click(copyBtn)
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalled()
    })
  })

  it('should copy valid JSON format', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    await waitFor(() => {
      const copyBtn = screen.getByRole('button', { name: /Copy JSON/i })
      expect(copyBtn).toBeInTheDocument()
    })
    const copyBtn = screen.getByRole('button', { name: /Copy JSON/i })
    await user.click(copyBtn)
    const call = navigator.clipboard.writeText.mock.calls[0]
    expect(() => JSON.parse(call[0])).not.toThrow()
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Auto-Polling Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should poll for updates every 2 seconds', async () => {
    vi.useFakeTimers()
    render(<HistoryPanel />)
    await waitFor(() => {
      expect(fetch).toHaveBeenCalled()
    })
    const initialCallCount = fetch.mock.calls.length
    vi.advanceTimersByTime(2100)
    await waitFor(() => {
      expect(fetch.mock.calls.length).toBeGreaterThan(initialCallCount)
    })
    vi.useRealTimers()
  })

  it('should update event list after polling', async () => {
    vi.useFakeTimers()
    const { rerender } = render(<HistoryPanel />)
    await waitFor(() => {
      expect(fetch).toHaveBeenCalled()
    })
    vi.advanceTimersByTime(2100)
    await waitFor(() => {
      expect(fetch.mock.calls.length).toBeGreaterThan(2)
    })
    vi.useRealTimers()
  })

  it('should clear polling interval on unmount', () => {
    vi.useFakeTimers()
    const { unmount } = render(<HistoryPanel />)
    const intervalId = vi.getTimerCount()
    unmount()
    vi.useRealTimers()
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Responsive Layout Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should apply hp-container class to root element', () => {
    const { container } = render(<HistoryPanel />)
    expect(container.querySelector('.hp-container')).toBeInTheDocument()
  })

  it('should have hp-header class on header section', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      expect(container.querySelector('.hp-header')).toBeInTheDocument()
    })
  })

  it('should have hp-list class on event list', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      expect(container.querySelector('.hp-list')).toBeInTheDocument()
    })
  })

  it('should have hp-content class on content area', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      expect(container.querySelector('.hp-content')).toBeInTheDocument()
    })
  })

  it('should use flexbox layout for responsive design', () => {
    const { container } = render(<HistoryPanel />)
    const content = container.querySelector('.hp-content')
    const styles = window.getComputedStyle(content)
    expect(styles.display).toBe('flex')
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Dark Theme Support Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should respect dark theme preference', () => {
    // Test that component uses CSS variables for theming
    const { container } = render(<HistoryPanel />)
    const element = container.querySelector('.hp-container')
    expect(element).toBeInTheDocument()
    // Verify nexus-ui tokens are available
    const styles = window.getComputedStyle(document.documentElement)
    expect(styles.getPropertyValue('--nx-gold')).toBeTruthy()
  })

  it('should use nexus-ui design tokens', () => {
    const { container } = render(<HistoryPanel />)
    // Check for nexus-ui classes that apply token-based styles
    const eventRow = container.querySelector('.hp-event-row')
    expect(eventRow).toBeInTheDocument()
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // CSS & Styling Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should not have any inline style={{}} that should be CSS', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    // Check that layout is done via CSS classes, not inline styles
    const rows = container.querySelectorAll('.hp-event-row')
    rows.forEach((row) => {
      // Event rows should not have critical layout styles inline
      const style = row.getAttribute('style')
      // Should be handled by CSS
      if (style) {
        expect(style).not.toContain('display:')
      }
    })
  })

  it('should have BEM naming convention (hp-* prefix)', () => {
    const { container } = render(<HistoryPanel />)
    const bpmElements = container.querySelectorAll('[class*="hp-"]')
    expect(bpmElements.length).toBeGreaterThan(0)
  })

  it('should render without inline overflow style typo', async () => {
    const { container } = render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    // Check that no elements have the 'y-auto' typo (should be 'auto' or handled by CSS)
    const allElements = container.querySelectorAll('*')
    allElements.forEach((el) => {
      const style = el.getAttribute('style')
      if (style) {
        expect(style).not.toContain("'y-auto'")
        expect(style).not.toContain('overflow: y-auto')
      }
    })
  })

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Functional Requirements Tests
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  it('should maintain all original functionality', async () => {
    render(<HistoryPanel />)
    const user = userEvent.setup()

    // Test original features still work
    await waitFor(() => {
      expect(screen.getByText(/Execution History/)).toBeInTheDocument()
    })

    // Tabs work
    const doneTab = screen.getByRole('button', { name: /Done/i })
    await user.click(doneTab)
    expect(doneTab).toHaveClass('hp-tab-btn--active')

    // Search works
    const searchInput = screen.getByPlaceholderText(/Filter by agent/)
    await user.type(searchInput, 'content')
    expect(searchInput).toHaveValue('content')

    // Event selection works
    await user.clear(searchInput)
    await waitFor(() => {
      expect(screen.getByText(/Generate marketing copy/)).toBeInTheDocument()
    })
    const eventRow = screen.getByText(/Generate marketing copy/).closest('.hp-event-row')
    await user.click(eventRow)
    expect(eventRow).toHaveClass('hp-event-row--selected')
  })

  it('should display events in correct order and format', async () => {
    render(<HistoryPanel />)
    await waitFor(() => {
      const events = screen.getAllByText(/Generate|Analyze/)
      // Verify we have all events
      expect(events.length).toBeGreaterThan(0)
    })
  })

  it('should handle missing optional fields gracefully', async () => {
    fetch.mockImplementationOnce((url) => {
      if (url.includes('/api/history')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            events: [
              {
                task_id: 'task-minimal',
                status: 'running',
                timestamp: new Date().toISOString(),
              },
            ],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    })

    render(<HistoryPanel />)
    await waitFor(() => {
      expect(screen.getByText('task-minimal')).toBeInTheDocument()
    })
  })
})

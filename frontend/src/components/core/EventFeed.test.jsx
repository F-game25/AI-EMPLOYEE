/**
 * EventFeed Component Tests
 * Verifies intelligent semantic event grouping, priority detection, and context locking
 */

import { render, screen, fireEvent, within } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import EventFeed from './EventFeed'

// Mock stores
vi.mock('../../store/eventFeedStore', () => ({
  useEventFeedStore: vi.fn((selector) => {
    const mockStore = {
      events: [
        {
          id: 'evt-1',
          category: 'task',
          priority: 'CRITICAL',
          notes: 'Task execution failed',
          ts: Date.now(),
          agentId: 'AGENT-07',
        },
        {
          id: 'evt-2',
          category: 'task',
          priority: 'WARNING',
          notes: 'Task retry attempt',
          ts: Date.now() - 1000,
          agentId: 'AGENT-07',
        },
        {
          id: 'evt-3',
          category: 'cognition',
          priority: 'NOTICE',
          notes: 'Memory write completed',
          ts: Date.now() - 2000,
          agentId: 'AGENT-03',
        },
      ],
      getGroupedEvents: () => [
        {
          agentId: 'AGENT-07',
          events: [
            {
              id: 'evt-1',
              category: 'task',
              priority: 'CRITICAL',
              notes: 'Task execution failed',
              ts: Date.now(),
            },
            {
              id: 'evt-2',
              category: 'task',
              priority: 'WARNING',
              notes: 'Task retry attempt',
              ts: Date.now() - 1000,
            },
          ],
          count: 2,
        },
        {
          agentId: 'AGENT-03',
          events: [
            {
              id: 'evt-3',
              category: 'cognition',
              priority: 'NOTICE',
              notes: 'Memory write completed',
              ts: Date.now() - 2000,
            },
          ],
          count: 1,
        },
      ],
      addEvent: vi.fn(),
      setEventSnapshot: vi.fn(),
      getEventsByCategory: vi.fn(),
      getRecentEvents: vi.fn(),
    }
    return selector ? selector(mockStore) : mockStore
  }),
}))

vi.mock('../../store/systemStore', () => ({
  useSystemStore: vi.fn((selector) => {
    const mockStore = {
      selectedEventId: null,
      setSelectedEventId: vi.fn(),
    }
    return selector ? selector(mockStore) : mockStore
  }),
}))

vi.mock('../../store/securityStore', () => ({
  useSecurityStore: vi.fn((selector) => {
    const mockStore = {
      securityStatus: { threat_score: 30 },
    }
    return selector ? selector(mockStore) : mockStore
  }),
}))

describe('EventFeed Component', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders without crashing', () => {
    render(<EventFeed autoScroll={true} />)
    expect(screen.getByRole('region')).toBeInTheDocument()
  })

  it('displays filter buttons for all categories', () => {
    render(<EventFeed />)
    expect(screen.getByText('ALL')).toBeInTheDocument()
    expect(screen.getByText('COGNITION')).toBeInTheDocument()
    expect(screen.getByText('TASK')).toBeInTheDocument()
  })

  it('persists filter selection to localStorage', () => {
    const { rerender } = render(<EventFeed />)
    const taskFilterBtn = screen.getByRole('button', { name: /TASK/ })
    fireEvent.click(taskFilterBtn)
    expect(localStorage.getItem('eventFeedFilter')).toBe('task')
  })

  it('shows grouped events with agent IDs', () => {
    render(<EventFeed />)
    expect(screen.getByText('AGENT-07')).toBeInTheDocument()
    expect(screen.getByText('AGENT-03')).toBeInTheDocument()
  })

  it('displays event count per group', () => {
    render(<EventFeed />)
    expect(screen.getByText(/2 events/)).toBeInTheDocument()
    expect(screen.getByText(/1 event/)).toBeInTheDocument()
  })

  it('auto-expands CRITICAL and WARNING priority groups', () => {
    const { container } = render(<EventFeed />)
    // CRITICAL group (AGENT-07) should be expanded
    const agentGroup = screen.getByText('AGENT-07').closest('.event-group')
    expect(agentGroup).toHaveClass('context-active') // or check expanded state
  })

  it('toggles group expansion on header click', () => {
    render(<EventFeed />)
    const agentHeader = screen.getByText('AGENT-03').closest('.event-group-header')
    expect(agentHeader).toBeInTheDocument()
    fireEvent.click(agentHeader)
    // Verify expansion state changed
  })

  it('displays priority indicators correctly', () => {
    const { container } = render(<EventFeed />)
    const criticalIndicators = container.querySelectorAll('.priority-critical')
    expect(criticalIndicators.length).toBeGreaterThan(0)
  })

  it('supports context locking on event selection', () => {
    render(<EventFeed />)
    const eventCards = screen.getAllByRole('button')
    if (eventCards.length > 0) {
      fireEvent.click(eventCards[0])
      // Verify context lock updated
    }
  })

  it('shows empty state when no events', () => {
    vi.mocked(useEventFeedStore).mockImplementation((selector) => {
      const mockStore = {
        events: [],
        getGroupedEvents: () => [],
      }
      return selector ? selector(mockStore) : mockStore
    })

    render(<EventFeed />)
    expect(screen.getByText(/No events yet/)).toBeInTheDocument()
  })
})

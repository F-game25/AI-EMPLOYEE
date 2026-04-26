import { render, screen } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import TopBar from '../components/dashboard/TopBar'

function renderTopBar() {
  return render(
    <BrowserRouter>
      <TopBar />
    </BrowserRouter>
  )
}

beforeEach(() => {
  useAppStore.setState({
    activeSection: 'agents',
    wsConnected: true,
    systemStatus: { cpu: 42, ram: 58, mode: 'AUTONOMOUS', uptime: '2d 4h' },
    nnStatus: { confidence: 87 },
  })
})

describe('TopBar', () => {
  it('renders the current page label', () => {
    renderTopBar()
    // TopBar shows the active section label as a breadcrumb
    expect(screen.getByText(/agents/i)).toBeInTheDocument()
  })

  it('shows ONLINE when wsConnected is true', () => {
    renderTopBar()
    expect(screen.getByText(/online/i)).toBeInTheDocument()
  })

  it('shows mode from systemStatus', () => {
    renderTopBar()
    expect(screen.getByText(/AUTONOMOUS/i)).toBeInTheDocument()
  })
})

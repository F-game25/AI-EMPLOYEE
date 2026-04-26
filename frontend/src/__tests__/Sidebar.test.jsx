import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import Sidebar from '../components/layout/Sidebar'

function renderSidebar() {
  return render(
    <BrowserRouter>
      <Sidebar />
    </BrowserRouter>
  )
}

beforeEach(() => {
  // Reset store to defaults
  useAppStore.setState({ sidebarCollapsed: false, activeSection: 'dashboard' })
})

describe('Sidebar', () => {
  it('renders navigation group labels when expanded', () => {
    renderSidebar()
    expect(screen.getByText('CORE')).toBeInTheDocument()
    expect(screen.getByText('INTELLIGENCE')).toBeInTheDocument()
    expect(screen.getByText('OPERATIONS')).toBeInTheDocument()
  })

  it('clicking a nav item calls setActiveSection', () => {
    renderSidebar()
    const agentsBtn = screen.getByText('Agents')
    fireEvent.click(agentsBtn)
    expect(useAppStore.getState().activeSection).toBe('agents')
  })

  it('collapse toggle hides group labels', () => {
    renderSidebar()
    const toggle = screen.getByTitle(/collapse/i)
    fireEvent.click(toggle)
    expect(useAppStore.getState().sidebarCollapsed).toBe(true)
    expect(screen.queryByText('CORE')).not.toBeInTheDocument()
  })
})

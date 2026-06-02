import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the api client so the page mounts without a backend.
vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(async () => ({ ok: true, orders: [
      { id: 'o1', bedrijfsnaam: 'Test BV', plaats: 'Delft', branche: 'kapper', status: 'gevonden', prijs: 299 },
    ] })),
    post: vi.fn(async () => ({ ok: true })),
    delete: vi.fn(async () => ({ ok: true })),
  },
}))

import SalesPage from '../components/pages/sales/SalesPage'

describe('SalesPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders the header, the 4-step stepper, and loaded orders', async () => {
    render(<SalesPage />)
    expect(screen.getByText('Website Sales')).toBeInTheDocument()
    for (const label of ['Leads', 'Demo', 'Pitch', 'Resultaat']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    await waitFor(() => expect(screen.getByText('Test BV')).toBeInTheDocument())
  })
})

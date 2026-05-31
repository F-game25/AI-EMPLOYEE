import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import FileUploadZone from '../components/workspace/FileUploadZone'

const OriginalXHR = window.XMLHttpRequest

class MockXHR {
  static instances = []

  constructor() {
    this.upload = { addEventListener: vi.fn((event, cb) => { this.uploadProgress = cb }) }
    this.status = 200
    this.responseText = JSON.stringify({ ok: true })
    this.timeout = 0
    MockXHR.instances.push(this)
  }

  open(method, url) {
    this.method = method
    this.url = url
  }

  send(formData) {
    this.formData = formData
  }

  abort() {
    this.onabort?.()
  }
}

describe('FileUploadZone', () => {
  afterEach(() => {
    MockXHR.instances = []
    window.XMLHttpRequest = OriginalXHR
    vi.restoreAllMocks()
  })

  it('posts uploads using the backend files field', async () => {
    window.XMLHttpRequest = MockXHR
    const onUploadComplete = vi.fn()

    render(<FileUploadZone apiUrl="" onUploadComplete={onUploadComplete} />)
    const input = document.querySelector('input[type="file"]')
    const file = new File(['hello'], 'note.txt', { type: 'text/plain' })

    fireEvent.change(input, { target: { files: [file] } })

    const xhr = MockXHR.instances[0]
    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('/api/workspace/upload')
    expect(xhr.formData.get('files')).toBe(file)

    xhr.onload()
    await waitFor(() => expect(screen.getByText('100%')).toBeInTheDocument())

  })

  it('shows backend upload errors without getting stuck', async () => {
    window.XMLHttpRequest = MockXHR

    render(<FileUploadZone apiUrl="" />)
    const input = document.querySelector('input[type="file"]')
    const file = new File(['bad'], 'bad.txt', { type: 'text/plain' })

    fireEvent.change(input, { target: { files: [file] } })
    const xhr = MockXHR.instances[0]
    xhr.status = 400
    xhr.responseText = JSON.stringify({ error: 'Invalid file', details: 'No files provided' })
    xhr.onload()

    expect(await screen.findByText('No files provided')).toBeInTheDocument()
  })
})

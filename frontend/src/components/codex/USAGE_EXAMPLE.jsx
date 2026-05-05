/**
 * USAGE EXAMPLE — CodexAnalyzer Integration
 *
 * This file demonstrates how to integrate the Codex UI components
 * into WorkspacePage or any other container.
 *
 * Example 1: Basic integration with file selection
 * Example 2: Modal dialog version
 * Example 3: Sidebar panel version
 */

import { useState, useCallback } from 'react'
import { CodexAnalyzer } from './index'

/**
 * Example 1: Basic Integration with WorkspacePage
 *
 * When user selects a text file, automatically show CodexAnalyzer.
 */
export function WorkspaceWithCodexExample() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState(null)

  const openFile = useCallback(async (file) => {
    // Load file content
    const response = await fetch(`/workspace/${encodeURIComponent(file.path)}`)
    const content = await response.text()

    // Show analyzer
    setSelectedFile(file)
    setFileContent(content)
  }, [])

  return (
    <div style={{ display: 'flex', height: '100%', gap: '16px' }}>
      {/* File list panel (left) */}
      <div style={{ flex: '0 0 250px', overflow: 'auto' }}>
        {/* Files: onClick -> openFile(file) */}
      </div>

      {/* Code analysis panel (right) */}
      {selectedFile && fileContent && (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <CodexAnalyzer
            fileId={selectedFile.id}
            fileName={selectedFile.name}
            fileContent={fileContent}
            onClose={() => setSelectedFile(null)}
          />
        </div>
      )}
    </div>
  )
}

/**
 * Example 2: Modal Dialog Version
 *
 * Show CodexAnalyzer in a modal overlay.
 * Useful when you want to keep the main view visible behind.
 */
export function CodexModalExample() {
  const [isOpen, setIsOpen] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState(null)

  const openCodexModal = useCallback(async (file) => {
    const response = await fetch(`/workspace/${encodeURIComponent(file.path)}`)
    const content = await response.text()
    setSelectedFile(file)
    setFileContent(content)
    setIsOpen(true)
  }, [])

  const closeModal = useCallback(() => {
    setIsOpen(false)
    setTimeout(() => {
      setSelectedFile(null)
      setFileContent(null)
    }, 300)
  }, [])

  return (
    <>
      {/* File list */}
      <div>
        <button onClick={() => openCodexModal({ id: '1', name: 'app.py', path: 'app.py' })}>
          Analyze app.py
        </button>
      </div>

      {/* Modal */}
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'flex-end',
            zIndex: 1000,
          }}
          onClick={closeModal}
        >
          <div
            style={{
              width: '100%',
              maxHeight: '90vh',
              background: 'var(--bg-card)',
              borderRadius: '12px 12px 0 0',
              overflow: 'hidden',
            }}
            onClick={e => e.stopPropagation()}
          >
            {selectedFile && fileContent && (
              <CodexAnalyzer
                fileId={selectedFile.id}
                fileName={selectedFile.name}
                fileContent={fileContent}
                onClose={closeModal}
              />
            )}
          </div>
        </div>
      )}
    </>
  )
}

/**
 * Example 3: Sidebar Panel Version
 *
 * CodexAnalyzer in a collapsible right sidebar.
 */
export function CodexSidebarExample() {
  const [showCodex, setShowCodex] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState(null)

  const analyzeFile = useCallback(async (file) => {
    const response = await fetch(`/workspace/${encodeURIComponent(file.path)}`)
    const content = await response.text()
    setSelectedFile(file)
    setFileContent(content)
    setShowCodex(true)
  }, [])

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Main content (left) */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {/* File list, etc. */}
      </div>

      {/* Codex sidebar (right) */}
      <div
        style={{
          flex: showCodex ? '0 0 50%' : '0 0 0',
          overflow: 'hidden',
          borderLeft: '1px solid var(--border-gold-dim)',
          transition: 'flex-basis 300ms var(--ease-out)',
        }}
      >
        {showCodex && selectedFile && fileContent && (
          <CodexAnalyzer
            fileId={selectedFile.id}
            fileName={selectedFile.name}
            fileContent={fileContent}
            onClose={() => setShowCodex(false)}
          />
        )}
      </div>
    </div>
  )
}

/**
 * Example 4: Batch Analysis
 *
 * Analyze multiple files and show results in a list.
 */
export function BatchCodexExample() {
  const [analyses, setAnalyses] = useState([])
  const [loading, setLoading] = useState(false)

  const analyzeMultiple = useCallback(async (files) => {
    setLoading(true)
    const results = []

    for (const file of files) {
      try {
        const content = await fetch(`/workspace/${file.path}`).then(r => r.text())
        const response = await fetch('/api/codex/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_name: file.name,
            content,
            language: 'python', // Detect based on extension
          }),
        })
        const result = await response.json()
        results.push({
          file: file.name,
          status: 'done',
          data: result.data,
        })
      } catch (err) {
        results.push({
          file: file.name,
          status: 'error',
          error: err.message,
        })
      }
    }

    setAnalyses(results)
    setLoading(false)
  }, [])

  return (
    <div>
      <button
        onClick={() => analyzeMultiple([
          { name: 'app.py', path: 'app.py' },
          { name: 'utils.py', path: 'utils.py' },
        ])}
        disabled={loading}
      >
        {loading ? 'Analyzing...' : 'Analyze Multiple Files'}
      </button>

      <div>
        {analyses.map((analysis, idx) => (
          <div key={idx} style={{ border: '1px solid #ccc', padding: '12px', marginTop: '12px' }}>
            <h3>{analysis.file}</h3>
            {analysis.status === 'done' && (
              <p>
                {(analysis.data?.bugs || []).length} bugs,
                {(analysis.data?.style_issues || []).length} style issues
              </p>
            )}
            {analysis.status === 'error' && <p style={{ color: 'red' }}>Error: {analysis.error}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Example 5: With Custom Styling
 *
 * Wrap CodexAnalyzer with custom styling.
 */
export function StyledCodexExample() {
  const [file, setFile] = useState(null)
  const [content, setContent] = useState(null)

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderRadius: '8px',
        overflow: 'hidden',
        boxShadow: '0 0 24px rgba(229, 199, 107, 0.2)',
      }}
    >
      {/* Custom header */}
      <div
        style={{
          padding: '12px 16px',
          background: 'var(--bg-elevated)',
          borderBottom: '1px solid var(--border-gold)',
        }}
      >
        <h2 style={{ margin: 0, color: 'var(--gold)' }}>Code Analysis</h2>
      </div>

      {/* Codex component */}
      {file && content && (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <CodexAnalyzer
            fileId={file.id}
            fileName={file.name}
            fileContent={content}
            onClose={() => setFile(null)}
          />
        </div>
      )}
    </div>
  )
}

/**
 * Example 6: Integration with API Hooks
 *
 * Using custom hooks for API calls.
 */
export function useCodexAnalysis(fileContent, fileName) {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const analyze = useCallback(async () => {
    if (!fileContent || !fileName) return

    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/codex/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: fileName,
          content: fileContent,
          language: detectLanguage(fileName),
        }),
      })

      if (!response.ok) throw new Error('Analysis failed')

      const result = await response.json()
      setAnalysis(result.data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [fileContent, fileName])

  return { analysis, loading, error, analyze }
}

function detectLanguage(fileName) {
  const ext = fileName.split('.').pop().toLowerCase()
  const map = { py: 'python', js: 'javascript', ts: 'typescript', jsx: 'jsx' }
  return map[ext] || 'text'
}

export function HookExample() {
  const [content, setContent] = useState('')
  const { analysis, loading, error, analyze } = useCodexAnalysis(content, 'example.py')

  return (
    <div>
      <textarea value={content} onChange={e => setContent(e.target.value)} />
      <button onClick={analyze} disabled={loading}>
        {loading ? 'Analyzing...' : 'Analyze'}
      </button>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {analysis && <p>{analysis.bugs?.length} bugs found</p>}
    </div>
  )
}

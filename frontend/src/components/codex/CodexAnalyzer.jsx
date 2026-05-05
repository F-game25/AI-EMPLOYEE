import { useState, useEffect, useCallback } from 'react'
import HexButton from '../nexus-ui/HexButton'
import { SectionLabel } from '../nexus-ui/SectionLabel'
import AnalysisSummary from './AnalysisSummary'
import IssuesList from './IssuesList'
import IssueDetail from './IssueDetail'
import CodePreview from './CodePreview'
import './CodexAnalyzer.css'
import { API_URL } from '../../config/api'

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

export default function CodexAnalyzer({ fileId, fileName, fileContent, onClose }) {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [severityFilter, setSeverityFilter] = useState(null)
  const [typeFilter, setTypeFilter] = useState(null)
  const [highlightedLine, setHighlightedLine] = useState(null)

  // Determine file language from extension
  const getLanguage = useCallback((name) => {
    const ext = (name.split('.').pop() || '').toLowerCase()
    const langMap = {
      py: 'python', js: 'javascript', ts: 'typescript', jsx: 'jsx', tsx: 'tsx',
      sh: 'bash', md: 'markdown', html: 'html', css: 'css', json: 'json', txt: 'text',
    }
    return langMap[ext] || 'text'
  }, [])

  // Fetch analysis from backend
  const analyzeFile = useCallback(async () => {
    if (!fileContent || !fileName) return

    setLoading(true)
    setError(null)
    setSelectedIssue(null)

    try {
      const response = await fetch(`${API_URL}/api/codex/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: fileName,
          content: fileContent,
          language: getLanguage(fileName),
        }),
      })

      if (!response.ok) throw new Error(`Analysis failed: ${response.statusText}`)

      const result = await response.json()
      setAnalysis(result.data || result)
    } catch (err) {
      setError(err.message || 'Analysis failed')
      setAnalysis(null)
    } finally {
      setLoading(false)
    }
  }, [fileContent, fileName, getLanguage])

  // Auto-analyze when file changes
  useEffect(() => {
    if (fileContent && fileName) {
      analyzeFile()
    }
  }, [fileContent, fileName, analyzeFile])

  // Combine all issues with type
  const getAllIssues = useCallback(() => {
    if (!analysis) return []

    const issues = []
    ;(analysis.bugs || []).forEach(bug => issues.push({ ...bug, type: 'bug' }))
    ;(analysis.style_issues || []).forEach(style => issues.push({ ...style, type: 'style' }))
    ;(analysis.perf_concerns || []).forEach(perf => issues.push({ ...perf, type: 'perf' }))
    ;(analysis.refactoring || []).forEach(ref => issues.push({ ...ref, type: 'refactoring' }))

    return issues.sort((a, b) => {
      const aSeverity = SEVERITY_ORDER[a.severity] ?? 999
      const bSeverity = SEVERITY_ORDER[b.severity] ?? 999
      return aSeverity - bSeverity
    })
  }, [analysis])

  // Filter issues
  const getFilteredIssues = useCallback(() => {
    let issues = getAllIssues()

    if (severityFilter) issues = issues.filter(i => i.severity === severityFilter)
    if (typeFilter) issues = issues.filter(i => i.type === typeFilter)
    if (highlightedLine) issues = issues.filter(i => i.line === highlightedLine)

    return issues
  }, [getAllIssues, severityFilter, typeFilter, highlightedLine])

  const filteredIssues = getFilteredIssues()
  const allIssues = getAllIssues()

  return (
    <div className="codex-analyzer">
      {/* Header */}
      <div className="codex-header">
        <div className="codex-header__title">
          <SectionLabel tone="gold" size="lg" rule>
            Code Analysis
          </SectionLabel>
          {fileName && <span className="codex-filename">{fileName}</span>}
        </div>
        {onClose && (
          <HexButton variant="ghost" size="sm" onClick={onClose}>
            Close
          </HexButton>
        )}
      </div>

      {/* Summary */}
      {analysis && <AnalysisSummary analysis={analysis} issues={allIssues} />}

      {/* Main content */}
      <div className="codex-content">
        {loading && (
          <div className="codex-loading">
            <div className="codex-spinner" />
            <p>Analyzing code...</p>
          </div>
        )}

        {error && (
          <div className="codex-error">
            <p>⚠ {error}</p>
            <HexButton variant="outline" size="sm" onClick={analyzeFile}>
              Retry
            </HexButton>
          </div>
        )}

        {!loading && !error && analysis && (
          <>
            {/* Filters */}
            <div className="codex-filters">
              <div className="codex-filter-group">
                <label>Severity:</label>
                <select
                  value={severityFilter || ''}
                  onChange={e => setSeverityFilter(e.target.value || null)}
                  className="codex-select"
                >
                  <option value="">All</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>

              <div className="codex-filter-group">
                <label>Type:</label>
                <select
                  value={typeFilter || ''}
                  onChange={e => setTypeFilter(e.target.value || null)}
                  className="codex-select"
                >
                  <option value="">All</option>
                  <option value="bug">Bugs</option>
                  <option value="style">Style</option>
                  <option value="perf">Performance</option>
                  <option value="refactoring">Refactoring</option>
                </select>
              </div>

              {highlightedLine && (
                <div className="codex-active-filter">
                  Line {highlightedLine}
                  <button
                    className="codex-clear-filter"
                    onClick={() => setHighlightedLine(null)}
                    aria-label="Clear line filter"
                  >
                    ✕
                  </button>
                </div>
              )}
            </div>

            {/* Code + Issues Layout */}
            <div className="codex-split">
              <div className="codex-left">
                <CodePreview
                  content={fileContent}
                  language={getLanguage(fileName)}
                  issues={allIssues}
                  onLineClick={setHighlightedLine}
                  selectedLine={highlightedLine}
                />
              </div>

              <div className="codex-right">
                {filteredIssues.length === 0 ? (
                  <div className="codex-empty">
                    <p>✓ No issues found</p>
                    {(severityFilter || typeFilter || highlightedLine) && (
                      <p className="codex-empty-hint">
                        Try adjusting your filters
                      </p>
                    )}
                  </div>
                ) : (
                  <IssuesList
                    issues={filteredIssues}
                    selected={selectedIssue}
                    onSelect={setSelectedIssue}
                  />
                )}
              </div>
            </div>

            {/* Issue Detail Panel */}
            {selectedIssue && (
              <IssueDetail
                issue={selectedIssue}
                onClose={() => setSelectedIssue(null)}
              />
            )}
          </>
        )}

        {!loading && !error && !analysis && (
          <div className="codex-empty">
            <p>No file loaded. Select a file to analyze.</p>
          </div>
        )}
      </div>
    </div>
  )
}

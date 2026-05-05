import { useMemo } from 'react'
import './CodePreview.css'

export default function CodePreview({
  content,
  language = 'text',
  issues = [],
  onLineClick,
  selectedLine = null,
}) {
  const lines = useMemo(() => content.split('\n'), [content])

  // Map line numbers to issues for quick lookup
  const issuesByLine = useMemo(() => {
    const map = {}
    issues.forEach(issue => {
      if (!map[issue.line]) map[issue.line] = []
      map[issue.line].push(issue)
    })
    return map
  }, [issues])

  // Determine line highlight tone
  const getLineTone = (lineNum) => {
    const lineIssues = issuesByLine[lineNum] || []
    if (lineIssues.length === 0) return null

    // Most severe first
    if (lineIssues.some(i => i.severity === 'critical')) return 'critical'
    if (lineIssues.some(i => i.severity === 'high')) return 'high'
    if (lineIssues.some(i => i.severity === 'medium')) return 'medium'
    return 'low'
  }

  return (
    <div className="code-preview">
      <div className="code-preview__header">
        <span className="code-preview__lang">{language}</span>
        <span className="code-preview__lines">{lines.length} lines</span>
      </div>

      <div className="code-preview__scroll">
        <table className="code-preview__table">
          <tbody>
            {lines.map((line, idx) => {
              const lineNum = idx + 1
              const tone = getLineTone(lineNum)
              const isSelected = selectedLine === lineNum
              const hasIssues = issuesByLine[lineNum]?.length > 0

              return (
                <tr
                  key={lineNum}
                  className={`code-line ${
                    isSelected ? 'code-line--selected' : ''
                  } ${tone ? `code-line--${tone}` : ''}`}
                >
                  {/* Line number - clickable */}
                  <td className="code-line__num">
                    <button
                      className="code-line__num-btn"
                      onClick={() => onLineClick?.(isSelected ? null : lineNum)}
                      title={
                        hasIssues
                          ? `${issuesByLine[lineNum].length} issue(s)`
                          : 'Click to filter'
                      }
                      type="button"
                    >
                      {lineNum}
                    </button>
                  </td>

                  {/* Code */}
                  <td className="code-line__content">
                    <code>{line || '\n'}</code>
                  </td>

                  {/* Issue indicators */}
                  {hasIssues && (
                    <td className="code-line__badges">
                      {issuesByLine[lineNum].map((issue, i) => (
                        <span
                          key={i}
                          className={`code-badge code-badge--${issue.severity}`}
                          title={issue.title || issue.type}
                        >
                          {issue.type === 'bug'
                            ? '🐛'
                            : issue.type === 'style'
                              ? '🎨'
                              : issue.type === 'perf'
                                ? '⚙'
                                : '♻'}
                        </span>
                      ))}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

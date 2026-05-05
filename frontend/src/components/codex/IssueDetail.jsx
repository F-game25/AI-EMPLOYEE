import { useState } from 'react'
import HexButton from '../nexus-ui/HexButton'
import StatusPill from '../nexus-ui/StatusPill'
import './IssueDetail.css'

const SEVERITY_COLOR = {
  critical: 'alert',
  high: 'warn',
  medium: 'gold',
  low: 'cool',
}

const ISSUE_TYPE_ICON = {
  bug: '🐛',
  style: '🎨',
  perf: '⚙',
  refactoring: '♻',
}

export default function IssueDetail({ issue, onClose }) {
  const [copied, setCopied] = useState(false)

  const copyFix = () => {
    if (issue.fix_suggestion) {
      navigator.clipboard.writeText(issue.fix_suggestion)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <div className="issue-detail">
      <div className="issue-detail__overlay" onClick={onClose} />

      <div className="issue-detail__panel">
        {/* Header */}
        <div className="issue-detail__head">
          <div className="issue-detail__head-left">
            <span className="issue-detail__type-icon">
              {ISSUE_TYPE_ICON[issue.type]}
            </span>
            <div className="issue-detail__head-text">
              <h2 className="issue-detail__title">{issue.title || 'Issue'}</h2>
              <p className="issue-detail__location">Line {issue.line}</p>
            </div>
          </div>

          <StatusPill
            label={issue.severity}
            tone={SEVERITY_COLOR[issue.severity]}
            dot={false}
          />
        </div>

        {/* Close button */}
        <button
          className="issue-detail__close"
          onClick={onClose}
          aria-label="Close"
          type="button"
        >
          ✕
        </button>

        {/* Content */}
        <div className="issue-detail__content">
          {/* Description */}
          {issue.description && (
            <section className="issue-detail__section">
              <h3 className="issue-detail__section-title">Description</h3>
              <p className="issue-detail__text">{issue.description}</p>
            </section>
          )}

          {/* Code snippet */}
          {issue.code_snippet && (
            <section className="issue-detail__section">
              <h3 className="issue-detail__section-title">Code</h3>
              <pre className="issue-detail__code">
                <code>{issue.code_snippet}</code>
              </pre>
            </section>
          )}

          {/* Fix suggestion */}
          {issue.fix_suggestion && (
            <section className="issue-detail__section">
              <h3 className="issue-detail__section-title">Fix Suggestion</h3>
              <div className="issue-detail__fix-box">
                <pre className="issue-detail__fix-code">
                  <code>{issue.fix_suggestion}</code>
                </pre>
                <button
                  className={`issue-detail__copy-btn ${copied ? 'copied' : ''}`}
                  onClick={copyFix}
                  type="button"
                  title="Copy fix to clipboard"
                >
                  {copied ? '✓ Copied' : 'Copy'}
                </button>
              </div>
            </section>
          )}

          {/* Additional info */}
          {issue.impact && (
            <section className="issue-detail__section">
              <h3 className="issue-detail__section-title">Impact</h3>
              <p className="issue-detail__text">{issue.impact}</p>
            </section>
          )}

          {issue.recommendation && (
            <section className="issue-detail__section">
              <h3 className="issue-detail__section-title">Recommendation</h3>
              <p className="issue-detail__text">{issue.recommendation}</p>
            </section>
          )}
        </div>

        {/* Footer actions */}
        <div className="issue-detail__footer">
          <HexButton variant="ghost" size="sm" onClick={onClose}>
            Close
          </HexButton>
          {issue.fix_suggestion && (
            <HexButton variant="outline" size="sm" onClick={copyFix}>
              {copied ? '✓ Copied' : 'Copy Fix'}
            </HexButton>
          )}
        </div>
      </div>
    </div>
  )
}

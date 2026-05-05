import StatusPill from '../nexus-ui/StatusPill'
import './IssuesList.css'

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

const ISSUE_TYPE_LABEL = {
  bug: 'Bug',
  style: 'Style',
  perf: 'Performance',
  refactoring: 'Refactoring',
}

export default function IssuesList({ issues, selected, onSelect }) {
  return (
    <div className="issues-list">
      <div className="issues-list__header">
        <h3 className="issues-list__title">Issues ({issues.length})</h3>
      </div>

      <div className="issues-list__scroll">
        {issues.map((issue, idx) => (
          <button
            key={`${issue.type}-${issue.line}-${idx}`}
            className={`issue-item ${selected?.id === issue.id ? 'issue-item--selected' : ''}`}
            onClick={() => onSelect(issue)}
            type="button"
          >
            <div className="issue-item__head">
              <span className="issue-item__type-badge">
                {ISSUE_TYPE_ICON[issue.type]} {ISSUE_TYPE_LABEL[issue.type]}
              </span>

              <StatusPill
                label={issue.severity}
                tone={SEVERITY_COLOR[issue.severity]}
                size="sm"
                dot={false}
              />
            </div>

            <div className="issue-item__line">
              Line {issue.line}
            </div>

            <div className="issue-item__title">
              {issue.title || issue.description || 'Untitled issue'}
            </div>

            {issue.description && (
              <div className="issue-item__snippet">
                {issue.description.substring(0, 80)}
                {issue.description.length > 80 ? '...' : ''}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}

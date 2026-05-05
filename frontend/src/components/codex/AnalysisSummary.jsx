import KPITile from '../nexus-ui/KPITile'
import './AnalysisSummary.css'

export default function AnalysisSummary({ analysis, issues }) {
  const bugCount = analysis.bugs?.length || 0
  const styleCount = analysis.style_issues?.length || 0
  const perfCount = analysis.perf_concerns?.length || 0
  const refactoringCount = analysis.refactoring?.length || 0

  const totalIssues = bugCount + styleCount + perfCount + refactoringCount
  const criticalCount = issues.filter(i => i.severity === 'critical').length
  const highCount = issues.filter(i => i.severity === 'high').length

  const analysisTime = analysis.analysis_time_ms || 0
  const timeLabel = analysisTime < 1000 ? `${analysisTime}ms` : `${(analysisTime / 1000).toFixed(1)}s`

  return (
    <div className="analysis-summary">
      <KPITile
        label="Total Issues"
        value={totalIssues}
        sub={`${criticalCount} critical, ${highCount} high`}
        icon="⚡"
        iconTone={totalIssues > 0 ? 'alert' : 'success'}
        accent={totalIssues > 10}
        size="md"
      />

      <KPITile
        label="Bugs"
        value={bugCount}
        icon="🐛"
        iconTone={bugCount > 0 ? 'alert' : 'success'}
        size="md"
      />

      <KPITile
        label="Style Issues"
        value={styleCount}
        icon="🎨"
        iconTone={styleCount > 0 ? 'warn' : 'success'}
        size="md"
      />

      <KPITile
        label="Performance"
        value={perfCount}
        icon="⚙"
        iconTone={perfCount > 0 ? 'warn' : 'success'}
        size="md"
      />

      <KPITile
        label="Refactoring"
        value={refactoringCount}
        icon="♻"
        iconTone="cool"
        size="md"
      />

      <KPITile
        label="Analysis Time"
        value={timeLabel}
        icon="⏱"
        iconTone="gold"
        size="md"
      />
    </div>
  )
}

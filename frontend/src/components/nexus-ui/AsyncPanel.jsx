import Panel from './Panel'
import LoadingSkeleton from './LoadingSkeleton'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'

/**
 * AsyncPanel — wraps Panel with data-lifecycle states.
 *
 * Props:
 *   loading     boolean
 *   error       string|null
 *   empty       boolean           — show EmptyState when true (and not loading/error)
 *   data        any               — truthy presence suppresses EmptyState check
 *   onRetry     function
 *   emptyIcon   string
 *   emptyTitle  string            default 'No data'
 *   emptySub    string
 *   skelVariant 'bar'|'card'|'row'|'grid'
 *   skelRows    number
 *   title, label, actions, className, style, children — forwarded to Panel
 */
export default function AsyncPanel({
  loading = false, error = null, empty = false, data,
  onRetry, emptyIcon, emptyTitle = 'No data', emptySub, emptyAction, onEmptyAction,
  skelVariant = 'bar', skelRows = 3,
  children, ...panelProps
}) {
  const showEmpty = !loading && !error && (empty || data === null || data === undefined || (Array.isArray(data) && data.length === 0))

  return (
    <Panel {...panelProps}>
      {loading && <LoadingSkeleton variant={skelVariant} rows={skelRows} />}
      {!loading && error && <ErrorState message={error} onRetry={onRetry} />}
      {!loading && !error && showEmpty && (
        <EmptyState icon={emptyIcon} title={emptyTitle} sub={emptySub} action={emptyAction} onAction={onEmptyAction} />
      )}
      {!loading && !error && !showEmpty && children}
    </Panel>
  )
}

/**
 * Consistent page header with title and optional actions.
 */
export default function PageHeader({ title, subtitle, children }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 'var(--space-5)',
      flexWrap: 'wrap',
      gap: 'var(--space-3)',
    }}>
      <div>
        <h1 style={{
          fontSize: '20px',
          fontWeight: 500,
          color: 'var(--text-primary)',
          letterSpacing: '-0.02em',
          lineHeight: 1.3,
        }}>
          {title}
        </h1>
        {subtitle && (
          <p style={{
            fontSize: '13px',
            color: 'var(--text-secondary)',
            marginTop: '2px',
          }}>
            {subtitle}
          </p>
        )}
      </div>
      {children && (
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          {children}
        </div>
      )}
    </div>
  )
}

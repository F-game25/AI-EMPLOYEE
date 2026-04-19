export default function TertiaryPanel({ className = '', children, ...props }) {
  return (
    <div className={`ds-card ${className}`.trim()} {...props}>
      {children}
    </div>
  )
}

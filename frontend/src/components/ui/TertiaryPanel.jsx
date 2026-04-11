export default function TertiaryPanel({ className = '', children, ...props }) {
  return (
    <div className={`tier-3-surface ${className}`.trim()} {...props}>
      {children}
    </div>
  )
}

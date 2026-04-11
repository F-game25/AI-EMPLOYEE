export default function SecondaryButton({ className = '', children, ...props }) {
  return (
    <button
      className={`tier-2-btn font-mono text-xs px-3 py-2 ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  )
}

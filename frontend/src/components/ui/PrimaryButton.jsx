export default function PrimaryButton({ className = '', children, ...props }) {
  return (
    <button
      className={`tier-1-btn font-mono text-xs px-4 py-2 ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  )
}

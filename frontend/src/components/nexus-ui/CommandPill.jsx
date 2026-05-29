import './CommandPill.css'

/**
 * <CommandPill>
 *   The chamfered command/search trigger that lives in the TopBar.
 *   Looks like an input but actually opens a command palette.
 *
 *   Props:
 *     placeholder string  — default "Search or run a command…"
 *     hotkey      string  — kbd hint shown on the right (default "⌘K")
 *     icon        node    — leading glyph (default "⌖")
 *     width       string  — CSS width (default "min(560px, 36vw)")
 *     onClick     fn      — fires on click / Enter / hotkey
 *     onChange    fn      — when used as a real input (controlled)
 *     value       string  — controlled input value
 *     readOnly    bool    — render as a button-style trigger (default true)
 *     className, style
 */
export default function CommandPill({
  placeholder = 'Search or run a command…',
  hotkey = '⌘K',
  icon = '⌖',
  width = 'min(560px, 36vw)',
  onClick,
  onChange,
  value,
  readOnly = true,
  className = '',
  style,
}) {
  const cls = ['nx-cmd', readOnly && 'nx-cmd--trigger', className].filter(Boolean).join(' ')

  return (
    <div
      className={cls}
      style={{ width, ...style }}
      onClick={readOnly ? onClick : undefined}
      role={readOnly ? 'button' : undefined}
      tabIndex={readOnly ? 0 : undefined}
      onKeyDown={readOnly && onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
    >
      <span className="nx-cmd__icon" aria-hidden="true">{icon}</span>
      {readOnly ? (
        <span className="nx-cmd__placeholder">{placeholder}</span>
      ) : (
        <input
          className="nx-cmd__input"
          placeholder={placeholder}
          value={value ?? ''}
          onChange={onChange}
        />
      )}
      {hotkey && (
        <kbd className="nx-cmd__kbd">{hotkey}</kbd>
      )}
    </div>
  )
}

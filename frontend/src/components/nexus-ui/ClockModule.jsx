import { useEffect, useState } from 'react'
import './ClockModule.css'
import { useVisibility } from '../../hooks/useVisibility'

/**
 * <ClockModule>
 *   Top-center mono timestamp + date strip for the OS topbar.
 *   Pauses ticking when the tab is hidden — saves perf on laptops.
 *
 *   Props:
 *     showSeconds bool    — default true
 *     showDate    bool    — default true
 *     timezone    string  — IANA tz; default user locale
 *     label       string  — optional small label above clock (e.g. "UTC")
 *     compact     bool    — single-row variant
 *     className, style
 */
export default function ClockModule({
  showSeconds = true,
  showDate = true,
  timezone,
  label,
  compact = false,
  className = '',
  style,
}) {
  const visible = useVisibility()
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    if (!visible) return
    const interval = showSeconds ? 1000 : 30000
    const id = setInterval(() => setNow(new Date()), interval)
    return () => clearInterval(id)
  }, [visible, showSeconds])

  const tOpts = {
    hour: '2-digit',
    minute: '2-digit',
    ...(showSeconds ? { second: '2-digit' } : {}),
    hour12: false,
    ...(timezone ? { timeZone: timezone } : {}),
  }
  const dOpts = {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(timezone ? { timeZone: timezone } : {}),
  }

  const time = now.toLocaleTimeString(undefined, tOpts)
  const date = now.toLocaleDateString(undefined, dOpts).toUpperCase()

  const cls = [
    'nx-clock',
    compact && 'nx-clock--compact',
    className,
  ].filter(Boolean).join(' ')

  return (
    <div className={cls} style={style} aria-label={`${date} ${time}`}>
      {label && <span className="nx-clock__label">{label}</span>}
      <span className="nx-clock__time">{time}</span>
      {showDate && <span className="nx-clock__date">{date}</span>}
    </div>
  )
}

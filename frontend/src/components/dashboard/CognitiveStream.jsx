import { useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useEventFeedStore } from '../../store/eventFeedStore'
import './CognitiveStream.css'

// TODO: wire `cognition:stream {ts, text}` WS event into cognitiveStore.streamLog
// (Python orchestrator would emit step-complete hooks). Until then we synthesize
// from the event feed (info-level entries) as a sensible fallback.

function fmtTime(ts) {
  if (!ts) return '--:--:--'
  const d = new Date(typeof ts === 'string' ? ts : Number(ts))
  if (Number.isNaN(d.getTime())) return '--:--:--'
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function CognitiveStream() {
  const explicitLog = useCognitiveStore(s => s.streamLog)
  const events = useEventFeedStore(s => s.events) || []

  const rows = useMemo(() => {
    if (Array.isArray(explicitLog) && explicitLog.length) {
      return explicitLog.slice(0, 5)
    }
    return events
      .filter(e => {
        const lvl = (e.level || e.severity || 'info').toLowerCase()
        return lvl === 'info' || lvl === 'success'
      })
      .slice(0, 5)
      .map(e => ({ ts: e.ts || e.timestamp || Date.now(), text: e.title || e.text || e.body || '' }))
  }, [explicitLog, events])

  return (
    <section className="cs-band" aria-label="Cognitive Stream">
      <header className="cs-band__head">
        <span className="cs-band__title">COGNITIVE STREAM</span>
        <span className="cs-band__live">
          <span className="cs-band__live-dot" />
          LIVE
        </span>
      </header>

      <ul className="cs-band__list">
        <AnimatePresence initial={false}>
          {rows.length === 0 ? (
            <li key="empty" className="cs-band__empty">Awaiting cognition events…</li>
          ) : (
            rows.map((r, idx) => (
              <motion.li
                key={`${r.ts}-${idx}`}
                className="cs-row"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
              >
                <span className="cs-row__ts">{fmtTime(r.ts)}</span>
                <span className="cs-row__bullet" aria-hidden="true">›</span>
                <span className="cs-row__text">{r.text}</span>
              </motion.li>
            ))
          )}
        </AnimatePresence>
      </ul>
    </section>
  )
}

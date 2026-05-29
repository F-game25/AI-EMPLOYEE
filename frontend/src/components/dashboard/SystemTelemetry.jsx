import { useEffect, useRef, useState } from 'react'
import { useSystemStore } from '../../store/systemStore'
import './SystemTelemetry.css'

const RING_SIZE = 24

function pushSample(ref, value) {
  if (!ref.current) ref.current = []
  ref.current.push(Number.isFinite(value) ? value : 0)
  if (ref.current.length > RING_SIZE) ref.current.shift()
  return ref.current.slice()
}

function Sparkline({ values, color }) {
  if (!values || values.length < 2) {
    return <svg className="st-spark" viewBox="0 0 200 60" preserveAspectRatio="none" />
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * 200
    const y = 56 - ((v - min) / range) * 50
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg className="st-spark" viewBox="0 0 200 60" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <polyline
        points={`${points} 200,60 0,60`}
        fill={color}
        opacity="0.08"
        stroke="none"
      />
    </svg>
  )
}

function Cell({ label, value, unit, delta, color, history }) {
  const sign = delta == null ? '' : delta >= 0 ? '+' : ''
  return (
    <div className="st-cell">
      <div className="st-cell__left">
        <div className="st-cell__label">{label}</div>
        <div className="st-cell__value" style={{ color }}>
          {value}<span className="st-cell__unit">{unit}</span>
        </div>
        {delta != null && (
          <div className={`st-cell__delta ${delta >= 0 ? 'st-cell__delta--up' : 'st-cell__delta--down'}`}>
            {sign}{delta.toFixed(1)}%
          </div>
        )}
      </div>
      <div className="st-cell__chart">
        <Sparkline values={history} color={color} />
      </div>
    </div>
  )
}

export default function SystemTelemetry() {
  const sh = useSystemStore(s => s.systemHealth) || {}

  const netRef     = useRef([])
  const latRef     = useRef([])
  const tpsRef     = useRef([])
  const errRef     = useRef([])
  const [, force] = useState(0)

  useEffect(() => {
    pushSample(netRef, sh.net_mbps ?? sh.network ?? 0)
    pushSample(latRef, sh.latency_ms ?? sh.latency ?? 0)
    pushSample(tpsRef, sh.throughput_tps ?? sh.throughput ?? 0)
    pushSample(errRef, (sh.error_rate ?? 0) * 100)
    force(x => x + 1)
  }, [sh])

  const netVal = (sh.net_mbps ?? 0).toFixed(0)
  const latVal = (sh.latency_ms ?? 0).toFixed(1)
  const tpsRaw = sh.throughput_tps ?? 0
  const tpsVal = tpsRaw >= 1e6 ? `${(tpsRaw / 1e6).toFixed(2)}M` : tpsRaw >= 1e3 ? `${(tpsRaw / 1e3).toFixed(1)}K` : Math.round(tpsRaw)
  const errVal = ((sh.error_rate ?? 0) * 100).toFixed(3)

  return (
    <section className="st-panel" aria-label="System Telemetry">
      <header className="st-panel__head">
        <span className="st-panel__title">SYSTEM TELEMETRY</span>
        <span className="st-panel__live">REAL-TIME</span>
      </header>
      <div className="st-panel__row">
        <Cell label="NETWORK"    value={netVal} unit=" MB/s" delta={sh.net_delta} color="#00CFFF" history={netRef.current} />
        <Cell label="LATENCY"    value={latVal} unit=" ms"   delta={sh.lat_delta} color="#FFB800" history={latRef.current} />
        <Cell label="THROUGHPUT" value={tpsVal} unit=" t/s"  delta={sh.tps_delta} color="#00FFB4" history={tpsRef.current} />
        <Cell label="ERROR RATE" value={errVal} unit="%"     delta={sh.err_delta} color="#FF6B6B" history={errRef.current} />
      </div>
    </section>
  )
}

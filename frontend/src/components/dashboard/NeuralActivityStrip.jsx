import { useState, useEffect } from 'react'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useEventFeedStore } from '../../store/eventFeedStore'
import { WaveformStrip } from '../nexus-ui'
import { useTelemetryBuffer } from '../../hooks/useTelemetryBuffer'
import { useVisibleInterval } from '../../hooks/useVisibleInterval'
import { usePerformanceMode } from '../../hooks/usePerformanceMode'
import './NeuralActivityStrip.css'

const LED_CHANNELS = [
  { id: 'cognitive', label: 'COG', color: '#22d3ee' },
  { id: 'memory',    label: 'MEM', color: '#a855f7' },
  { id: 'agents',    label: 'AGT', color: '#fbbf24' },
  { id: 'models',    label: 'MOD', color: '#22c55e' },
]

function classifyEvent(t) {
  if (!t) return null
  if (t.startsWith('nb:') || t.startsWith('cognitive:') || t.startsWith('brain:')) return 'cognitive'
  if (t.includes('memory')) return 'memory'
  if (t.startsWith('agent:')) return 'agents'
  if (t.includes('model') || t.startsWith('llm:')) return 'models'
  return null
}

export default function NeuralActivityStrip() {
  const reasoningSteps = useCognitiveStore(s => s.reasoningSteps || [])
  const memoryWritesArr = useCognitiveStore(s => s.memoryWrites || [])
  const modelCallsArr   = useCognitiveStore(s => s.modelCalls || [])
  const recentEvents = useEventFeedStore(s => s.events || [])

  const [pulses, setPulses] = useState({ cognitive: 0, memory: 0, agents: 0, models: 0 })

  useEffect(() => {
    if (recentEvents.length === 0) return
    const latest = recentEvents[0]
    const channel = classifyEvent(latest?.type || latest?.event || '')
    if (channel) setPulses(p => ({ ...p, [channel]: Date.now() }))
  }, [recentEvents])

  // Re-render so LED active-state expiry refreshes — paused when tab hidden,
  // and slower on low-tier devices.
  const { pollMultiplier } = usePerformanceMode()
  const [, setTick] = useState(0)
  useVisibleInterval(() => setTick(n => n + 1), 1000, pollMultiplier)

  const reasoningRate = reasoningSteps.length
  const memoryCount   = memoryWritesArr.length
  const modelCount    = modelCallsArr.length

  const reasoningBuf = useTelemetryBuffer(reasoningRate, 60)
  const memoryBuf    = useTelemetryBuffer(memoryCount,   60)
  const modelBuf     = useTelemetryBuffer(modelCount,    60)
  const errorBuf     = useTelemetryBuffer(0,              60)

  const tickerItems = reasoningSteps.slice(-6).reverse()

  return (
    <div className="nas-strip" role="region" aria-label="Neural activity strip">
      <div className="nas-leds">
        <div className="nas-leds__label">STATUS</div>
        {LED_CHANNELS.map(led => {
          const recent = Date.now() - (pulses[led.id] || 0) < 600
          return (
            <div
              key={led.id}
              className={`nas-led ${recent ? 'nas-led--active' : ''}`}
              style={{ '--led-color': led.color }}
              title={`${led.label} channel`}
            >
              <span className="nas-led__dot" aria-hidden="true" />
              <span className="nas-led__name">{led.label}</span>
            </div>
          )
        })}
      </div>

      <div className="nas-ticker">
        <div className="nas-ticker__label">REASONING</div>
        <div className="nas-ticker__rail">
          {tickerItems.length === 0 ? (
            <span className="nas-ticker__idle">awaiting cognitive activity…</span>
          ) : (
            <div className="nas-ticker__scroll">
              {tickerItems.map((step, i) => (
                <span key={i} className="nas-ticker__entry">
                  <span className="nas-ticker__tag">{step.role || step.kind || 'thought'}</span>
                  <span className="nas-ticker__text">
                    {(step.content || step.summary || step.text || '').slice(0, 100)}
                  </span>
                </span>
              ))}
              {/* Duplicate for seamless marquee */}
              {tickerItems.map((step, i) => (
                <span key={`dup-${i}`} className="nas-ticker__entry" aria-hidden="true">
                  <span className="nas-ticker__tag">{step.role || step.kind || 'thought'}</span>
                  <span className="nas-ticker__text">
                    {(step.content || step.summary || step.text || '').slice(0, 100)}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="nas-waves">
        <WaveformStrip label="REASONING/S" value={reasoningRate} data={reasoningBuf} color="#22d3ee" height={48} />
        <WaveformStrip label="MEMORY/S"    value={memoryCount}   data={memoryBuf}    color="#a855f7" height={48} />
        <WaveformStrip label="MODEL/S"     value={modelCount}    data={modelBuf}     color="#fbbf24" height={48} />
        <WaveformStrip label="ERRORS"      value={0}             data={errorBuf}     color="#ef4444" height={48} />
      </div>
    </div>
  )
}

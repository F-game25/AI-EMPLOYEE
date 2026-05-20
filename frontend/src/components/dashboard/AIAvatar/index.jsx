import { useEffect, useRef, useState } from 'react'
import { useBrainStore } from '../../../store/brainStore'
import { useAppStore } from '../../../store/appStore'
import { queueSpeech, setAvatarAlert, useAvatarStateHook } from './useSpeechQueue'
import { buildMessage, getGreeting } from './avatarMessages'
import AvatarGlyph from './AvatarGlyph'
import './AIAvatar.css'

const SLOW_LATENCY_MS = 2000
const BATCH_THRESHOLD = 3

export default function AIAvatar() {
  const avatarState = useAvatarStateHook()
  const [bubble, setBubble] = useState('')
  const [bubbleVisible, setBubbleVisible] = useState(false)
  const bubbleTimer = useRef(null)
  const completedAgentsRef = useRef(0)
  const hasGreeted = useRef(false)

  function showBubble(text) {
    setBubble(text)
    setBubbleVisible(true)
    clearTimeout(bubbleTimer.current)
    bubbleTimer.current = setTimeout(() => setBubbleVisible(false), 6000)
  }

  // Greeting on first mount
  useEffect(() => {
    if (hasGreeted.current) return
    hasGreeted.current = true
    const greeting = getGreeting()
    setTimeout(() => {
      queueSpeech(greeting, 6)
      showBubble(greeting)
    }, 2500)
  }, [])

  // Subscribe to reasoning steps
  useEffect(() => {
    return useBrainStore.subscribe(s => s.reasoningSteps, (steps, prev) => {
      if (!steps.length) return
      const latest = steps[steps.length - 1]
      if (latest === prev?.[prev.length - 1]) return

      if (latest.status === 'active') {
        const msg = buildMessage('nb:reasoning_step:active', latest)
        if (msg) { queueSpeech(msg, 3); showBubble(msg) }
      }
      if (latest.status === 'done' && latest.latency_ms > SLOW_LATENCY_MS) {
        const msg = buildMessage('nb:reasoning_step:slow', latest)
        if (msg) { queueSpeech(msg, 4); showBubble(msg) }
      }
    })
  }, [])

  // Subscribe to memory writes — check for user patterns
  useEffect(() => {
    return useBrainStore.subscribe(s => s.memoryWrites, (writes, prev) => {
      if (!writes.length) return
      const latest = writes[writes.length - 1]
      if (latest === prev?.[prev.length - 1]) return
      if (latest.type === 'user_pattern' && latest.pattern) {
        const msg = buildMessage('memory:user_pattern', latest)
        if (msg) { queueSpeech(msg, 5); showBubble(msg) }
      }
    })
  }, [])

  // Subscribe to agent updates — detect completions and errors
  useEffect(() => {
    return useAppStore.subscribe(s => s.agents, (agents, prev) => {
      if (!prev) return
      let completedCount = 0
      agents.forEach(a => {
        const prevAgent = prev.find(p => p.id === a.id || p.name === a.name)
        if (!prevAgent) return
        const wasActive = prevAgent.status === 'running' || prevAgent.status === 'active'
        const isNowDone = a.status === 'done' || a.status === 'completed' || a.status === 'idle'
        const isError = a.status === 'error' || a.status === 'failed'

        if (wasActive && isError) {
          const msg = buildMessage('agent:error', a)
          if (msg) { queueSpeech(msg, 8); setAvatarAlert(); showBubble(msg) }
        }
        if (wasActive && isNowDone) completedCount++
      })

      completedAgentsRef.current += completedCount
      if (completedAgentsRef.current >= BATCH_THRESHOLD) {
        completedAgentsRef.current = 0
        const msg = buildMessage('agent:batch_complete', {})
        if (msg) { queueSpeech(msg, 5); showBubble(msg) }
      }
    })
  }, [])

  // Subscribe to system status for degraded mode
  useEffect(() => {
    return useAppStore.subscribe(s => s.systemStatus, (status, prev) => {
      if (!status || !prev) return
      const degraded = (status.error_rate || 0) > 0.3 && (prev.error_rate || 0) <= 0.3
      if (degraded) {
        const msg = buildMessage('system:degraded', {})
        if (msg) { queueSpeech(msg, 8); setAvatarAlert(); showBubble(msg) }
      }
    })
  }, [])

  return (
    <div style={{
      position: 'fixed',
      top: '64px',
      right: '16px',
      zIndex: 50,
      width: '160px',
      height: '160px',
    }}>
      {/* Speech bubble — appears to the left */}
      <div className={`avatar-bubble ${bubbleVisible ? 'avatar-bubble--visible' : ''}`}>
        {bubble}
      </div>
      <AvatarGlyph state={avatarState} />
    </div>
  )
}

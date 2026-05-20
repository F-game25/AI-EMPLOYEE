// Singleton speech queue — not a React hook internally
import { useState, useEffect } from 'react'

const queue = []
let speaking = false
let lastSpokenAt = 0
const RATE_LIMIT_MS = 30000

const stateTarget = new EventTarget()
let _currentState = 'idle' // idle | speaking | alert

function emitState(s) {
  _currentState = s
  stateTarget.dispatchEvent(new CustomEvent('change', { detail: s }))
}

function drainQueue() {
  if (!queue.length) {
    speaking = false
    emitState('idle')
    return
  }
  speaking = true
  emitState('speaking')
  const { text } = queue.shift()
  const u = new SpeechSynthesisUtterance(text)
  u.pitch = 0.88
  u.rate = 0.93
  u.volume = 0.85
  u.onend = drainQueue
  u.onerror = drainQueue
  try {
    window.speechSynthesis.speak(u)
  } catch (_) {
    drainQueue()
  }
}

export function queueSpeech(text, priority = 5) {
  if (!text) return
  const now = Date.now()

  // High-priority (>=8) bypasses rate limit
  if (priority < 8 && now - lastSpokenAt < RATE_LIMIT_MS) return

  // Deduplicate
  if (queue.some(q => q.text === text)) return

  lastSpokenAt = now
  queue.push({ text, priority, ts: now })
  queue.sort((a, b) => b.priority - a.priority)

  // Trim overflow — keep top 3
  if (queue.length > 4) {
    queue.splice(3)
  }

  if (!speaking) drainQueue()
}

export function setAvatarAlert() {
  emitState('alert')
  setTimeout(() => { if (!speaking) emitState('idle') }, 3000)
}

export function useAvatarStateHook() {
  const [state, setState] = useState(_currentState)
  useEffect(() => {
    function onchange(e) { setState(e.detail) }
    stateTarget.addEventListener('change', onchange)
    return () => stateTarget.removeEventListener('change', onchange)
  }, [])
  return state
}

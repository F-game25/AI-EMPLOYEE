// Singleton mouse tracker — one rAF loop shared across all consumers.
// Subscribers receive (clientX, clientY) on every animation frame.
// Zero extra re-renders: callers update DOM refs directly.

let _mx = 0, _my = 0
let _started = false
const _subs = new Set()

function _tick() {
  _subs.forEach(fn => fn(_mx, _my))
  requestAnimationFrame(_tick)
}

function _ensureStarted() {
  if (_started || typeof window === 'undefined') return
  _started = true
  window.addEventListener('mousemove', e => { _mx = e.clientX; _my = e.clientY }, { passive: true })
  requestAnimationFrame(_tick)
}

export function subscribeGlobalMouse(fn) {
  _ensureStarted()
  _subs.add(fn)
  return () => _subs.delete(fn)
}

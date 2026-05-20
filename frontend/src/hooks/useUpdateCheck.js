import { useEffect, useRef, useCallback } from 'react'
import { useSystemStore } from '../store/systemStore'

export function useUpdateCheck() {
  const updateStatus = useSystemStore(s => s.updateStatus)
  const setUpdateStatus = useSystemStore(s => s.setUpdateStatus)
  const appendUpdateLog = useSystemStore(s => s.appendUpdateLog)
  const clearUpdateLog = useSystemStore(s => s.clearUpdateLog)
  const baseline = useRef(null)
  const esRef = useRef(null)

  // Passive: poll build-hash every 60s to detect server-side updates
  useEffect(() => {
    fetch('/api/system/build-hash')
      .then(r => r.json())
      .then(d => { baseline.current = d.last_commit || d.last_installed_commit })
      .catch(() => {})

    const i = setInterval(async () => {
      try {
        const d = await fetch('/api/system/build-hash').then(r => r.json())
        const current = d.last_commit || d.last_installed_commit
        if (baseline.current && current && current !== baseline.current) {
          setUpdateStatus({ available: true })
        }
      } catch (_) {}
    }, 60000)
    return () => clearInterval(i)
  }, [setUpdateStatus])

  const checkForUpdates = useCallback(async () => {
    setUpdateStatus({ checking: true, error: null })
    try {
      const [statusRes, hashRes] = await Promise.all([
        fetch('/api/system/update-status', { headers: { Authorization: `Bearer ${sessionStorage.getItem('ai_jwt')}` } }).then(r => r.json()),
        fetch('/api/system/build-hash', { headers: { Authorization: `Bearer ${sessionStorage.getItem('ai_jwt')}` } }).then(r => r.json()),
      ])
      setUpdateStatus({
        checking: false,
        lastChecked: Date.now(),
        available: statusRes.has_update || false,
        currentCommit: hashRes.last_commit || null,
        remoteCommit: statusRes.updater?.remote_commit || null,
      })
    } catch (e) {
      setUpdateStatus({ checking: false, error: e.message || 'Check failed' })
    }
  }, [setUpdateStatus])

  const applyUpdate = useCallback(() => {
    if (updateStatus.applying) return
    clearUpdateLog()
    setUpdateStatus({ applying: true, error: null, progress: 0, stage: 'starting', updateComplete: false })

    const jwt = sessionStorage.getItem('ai_jwt')
    const es = new EventSource('/api/system/run-update?_auth=' + encodeURIComponent(jwt || ''))
    esRef.current = es

    // SSE doesn't support custom headers — use fetch POST with SSE-like reading instead
    es.close()

    fetch('/api/system/run-update', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${jwt}`,
        'Content-Type': 'application/json',
      },
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
        setUpdateStatus({ applying: false, error: err.error || 'Request failed' })
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      const STAGE_PROGRESS = { starting: 5, fetching: 15, comparing: 25, applying: 50, building: 75, restarting: 90, done: 100, running: 40 }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          try {
            const msg = JSON.parse(line.slice(5).trim())
            if (msg.type === 'log') {
              appendUpdateLog({ text: msg.line, level: msg.level, stage: msg.stage, ts: msg.ts })
              setUpdateStatus({ stage: msg.stage, progress: STAGE_PROGRESS[msg.stage] || 40 })
            } else if (msg.type === 'complete') {
              setUpdateStatus({
                applying: false,
                updateComplete: msg.success,
                progress: msg.success ? 100 : 0,
                stage: msg.success ? 'done' : 'error',
                error: msg.success ? null : msg.message,
              })
            } else if (msg.type === 'error') {
              setUpdateStatus({ applying: false, error: msg.message, stage: 'error' })
            }
          } catch (_) {}
        }
      }
    }).catch(e => {
      setUpdateStatus({ applying: false, error: e.message || 'Connection failed' })
    })
  }, [updateStatus.applying, setUpdateStatus, appendUpdateLog, clearUpdateLog])

  return {
    updateReady: updateStatus.available || updateStatus.updateComplete,
    updateComplete: updateStatus.updateComplete,
    checking: updateStatus.checking,
    applying: updateStatus.applying,
    progress: updateStatus.progress,
    stage: updateStatus.stage,
    log: updateStatus.log,
    error: updateStatus.error,
    lastChecked: updateStatus.lastChecked,
    currentCommit: updateStatus.currentCommit,
    remoteCommit: updateStatus.remoteCommit,
    checkForUpdates,
    applyUpdate,
  }
}

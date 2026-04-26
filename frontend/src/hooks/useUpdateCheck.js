import { useEffect, useRef, useState } from 'react'

export function useUpdateCheck() {
  const [updateReady, setUpdateReady] = useState(false)
  const baseline = useRef(null)

  useEffect(() => {
    // Capture build hash at startup
    fetch('/api/system/build-hash')
      .then(r => r.json())
      .then(d => {
        baseline.current = d.last_commit || d.last_installed_commit
      })
      .catch(() => {})

    // Poll every 60s for new build
    const i = setInterval(async () => {
      try {
        const d = await fetch('/api/system/build-hash').then(r => r.json())
        const current = d.last_commit || d.last_installed_commit
        if (baseline.current && current && current !== baseline.current) {
          setUpdateReady(true)
        }
      } catch {}
    }, 60000)

    return () => clearInterval(i)
  }, [])

  return { updateReady }
}

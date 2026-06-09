import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
import { useAppStore } from '../../store/appStore'
import { useSystemStore } from '../../store/systemStore'
import './SystemSetupCenter.css'

const STATUS_LABEL = {
  live: 'Live',
  dry_run: 'Dry-run',
  mock: 'Mock',
  fallback: 'Fallback',
  not_configured: 'Needs setup',
  unavailable: 'Unavailable',
  error: 'Error',
}

const CATEGORY_ORDER = ['runtime', 'llm', 'execution', 'memory', 'integration', 'money', 'security']

const WIZARD_STEPS = [
  { id: 'identity', label: 'Identity', detail: 'Name the system and confirm the technical owner.' },
  { id: 'runtime', label: 'Runtime', detail: 'Check Node, Python, WebSocket, ports, build output, and startup warnings.' },
  { id: 'llm', label: 'LLM', detail: 'Confirm local or provider-backed model access before live task execution.' },
  { id: 'memory', label: 'Memory', detail: 'Confirm memory, vector, artifact, and proof storage are writable.' },
  { id: 'integrations', label: 'Integrations', detail: 'Review missing provider keys and approval-gated connectors.' },
  { id: 'safety', label: 'Money Safety', detail: 'Confirm external effects require approval before execution.' },
  { id: 'smoke', label: 'Smoke Test', detail: 'Run one safe canonical task and display proof/output.' },
]

const USER_READINESS = [
  {
    id: 'technical_admin',
    label: 'Technical Admin',
    needs: ['runtime', 'llm', 'execution', 'memory', 'security'],
    outcome: 'Can install, configure, verify, and troubleshoot the system.',
  },
  {
    id: 'owner',
    label: 'Owner / Founder',
    needs: ['money', 'integration', 'execution'],
    outcome: 'Can see what makes money, what needs approval, and what produced proof.',
  },
  {
    id: 'operator',
    label: 'Daily Operator',
    needs: ['execution', 'memory', 'integration'],
    outcome: 'Can run tasks, inspect blockers, and find usable outputs.',
  },
  {
    id: 'analyst',
    label: 'Analyst',
    needs: ['memory', 'llm', 'execution'],
    outcome: 'Can verify sources, traces, model choices, and degraded results.',
  },
]

function normalizeStatus(status) {
  return STATUS_LABEL[status] ? status : 'error'
}

function statusLabel(status) {
  return STATUS_LABEL[normalizeStatus(status)]
}

function statusSeverity(status) {
  const s = normalizeStatus(status)
  if (s === 'live') return 0
  if (s === 'dry_run' || s === 'fallback') return 1
  if (s === 'mock' || s === 'not_configured') return 2
  return 3
}

function fmtTime(value) {
  if (!value) return 'Not checked'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Not checked'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function capabilityId(capability) {
  return capability?.id || capability?.name || capability?.label || 'capability'
}

function groupCapabilities(capabilities) {
  const groups = new Map()
  for (const capability of capabilities) {
    const category = capability.category || 'runtime'
    if (!groups.has(category)) groups.set(category, [])
    groups.get(category).push(capability)
  }
  return [...groups.entries()].sort(([a], [b]) => {
    const ai = CATEGORY_ORDER.indexOf(a)
    const bi = CATEGORY_ORDER.indexOf(b)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b)
  })
}

function deriveWizardStatus(step, capabilities) {
  if (step.id === 'identity') return 'live'
  if (step.id === 'safety') return capabilities.some(cap => capabilityId(cap) === 'money_mode') ? 'live' : 'fallback'
  if (step.id === 'smoke') return capabilities.some(cap => normalizeStatus(cap.status) === 'live') ? 'fallback' : 'unavailable'

  const category = step.id === 'integrations' ? 'integration' : step.id
  const related = capabilities.filter(cap => cap.category === category)
  if (!related.length) return 'unavailable'
  const worst = Math.max(...related.map(cap => statusSeverity(cap.status)))
  if (worst === 0) return 'live'
  if (worst === 1) return 'fallback'
  if (worst === 2) return 'not_configured'
  return 'unavailable'
}

function deriveUserReadiness(profile, capabilities) {
  const related = capabilities.filter(capability => profile.needs.includes(capability.category))
  if (!related.length) return { status: 'unavailable', blockers: ['No capability data for this profile yet.'] }
  const blockers = related
    .filter(capability => normalizeStatus(capability.status) !== 'live')
    .map(capability => `${capability.label || capabilityId(capability)}: ${statusLabel(capability.status)}`)
  if (!blockers.length) return { status: 'live', blockers: [] }
  const hardBlock = related.some(capability => ['unavailable', 'error', 'not_configured'].includes(normalizeStatus(capability.status)))
  return { status: hardBlock ? 'not_configured' : 'fallback', blockers: blockers.slice(0, 4) }
}

function StatusBadge({ status }) {
  const normalized = normalizeStatus(status)
  return <span className={`setup-status setup-status--${normalized}`}>{statusLabel(normalized)}</span>
}

function formatOllamaPullStatus(event) {
  if (!event) return ''
  if (event.error) return `Model download failed: ${event.error}`
  const model = event.name || event.recommendation?.model || 'recommended model'
  const status = event.status || 'downloading'
  if (event.total && event.completed) {
    const total = (event.total / 1e9).toFixed(2)
    const done = (event.completed / 1e9).toFixed(2)
    return `${model}: ${status} (${done}/${total} GB)`
  }
  if (event.recommendation && status === 'recommendation') {
    return `Recommended for this PC: ${event.recommendation.model}. Starting download.`
  }
  return `${model}: ${status}`
}

function voiceStatusToSetup(status) {
  if (status === 'ready') return 'live'
  if (status === 'starting' || status === 'downloading' || status === 'training' || status === 'benchmarking') return 'fallback'
  if (status === 'runtime_missing' || status === 'model_missing' || status === 'license_required' || status === 'bundle_missing' || status === 'bundle_corrupt') return 'not_configured'
  if (status === 'hardware_blocked') return 'unavailable'
  if (status === 'error') return 'error'
  return 'unavailable'
}

function formatBytes(bytes) {
  const value = Number(bytes) || 0
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)} GB`
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} MB`
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)} KB`
  return `${value} B`
}

function formatVoiceDownloadStatus(event) {
  if (!event) return ''
  const component = event.component || 'voice runtime'
  if (event.error) return `${component}: ${event.error}`
  const state = event.state || event.type || 'downloading'
  if (Number.isFinite(event.percent)) {
    const received = event.bytes_received ? ` ${formatBytes(event.bytes_received)}` : ''
    const total = event.total_bytes ? `/${formatBytes(event.total_bytes)}` : ''
    return `${component}: ${state} ${Math.round(event.percent)}%${received}${total}`
  }
  return `${component}: ${event.message || state}`
}

function CapabilityRow({ capability, onAction }) {
  const missing = Array.isArray(capability.missing_env) ? capability.missing_env : []
  const action = capability.setup_action || 'none'
  return (
    <div className={`setup-cap setup-cap--${normalizeStatus(capability.status)}`}>
      <div className="setup-cap__main">
        <span className="setup-cap__dot" />
        <div>
          <div className="setup-cap__name">{capability.label || capabilityId(capability)}</div>
          <div className="setup-cap__details">{capability.details || capability.docs_hint || 'No details reported.'}</div>
          {missing.length > 0 && (
            <div className="setup-cap__env">Missing: {missing.join(', ')}</div>
          )}
        </div>
      </div>
      <div className="setup-cap__side">
        <StatusBadge status={capability.status} />
        <button type="button" className="setup-btn setup-btn--small" onClick={() => onAction(action, capability)}>
          {action === 'none' ? 'View' : action.replace(/_/g, ' ')}
        </button>
      </div>
    </div>
  )
}

export default function SystemSetupCenter() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const capabilityStatus = useSystemStore(s => s.capabilityStatus)
  const fetchCapabilityStatus = useSystemStore(s => s.fetchCapabilityStatus)
  const [activeStep, setActiveStep] = useState('runtime')
  const [identity, setIdentity] = useState({ systemName: 'Aeternus Nexus', adminName: 'Technical Admin', voicePreset: 'professional', colorPalette: null })
  const [palettes, setPalettes] = useState([])
  const [actionResult, setActionResult] = useState(null)
  const [ollamaPullStatus, setOllamaPullStatus] = useState(null)
  const [voiceRuntime, setVoiceRuntime] = useState(null)
  const [voiceDownloadStatus, setVoiceDownloadStatus] = useState(null)
  const [voiceBenchmark, setVoiceBenchmark] = useState(null)
  const [voiceDoctor, setVoiceDoctor] = useState(null)
  const [voiceSelfTest, setVoiceSelfTest] = useState(null)
  const [voiceLogs, setVoiceLogs] = useState(null)
  const [voiceSamples, setVoiceSamples] = useState(null)
  const [smokeResult, setSmokeResult] = useState(null)
  const [busyAction, setBusyAction] = useState(null)

  const refreshVoiceRuntime = useCallback(async () => {
    const runtime = await api.voice.runtime()
    setVoiceRuntime(runtime)
    api.voice.runtimeDoctor()
      .then(setVoiceDoctor)
      .catch(() => {})
    api.voice.runtimeLogs(12)
      .then(setVoiceLogs)
      .catch(() => {})
    api.voice.modelSamples()
      .then(setVoiceSamples)
      .catch(() => {})
    return runtime
  }, [])

  useEffect(() => {
    fetchCapabilityStatus()
    refreshVoiceRuntime().catch(error => {
      setVoiceRuntime({ ok: false, error: error?.message || 'Voice runtime status unavailable' })
    })
    // Salvaged from the old Onboarding flow: backend-generated accent palettes.
    api.get('/api/onboarding/palettes')
      .then(d => {
        const list = d?.palettes || []
        setPalettes(list)
        if (list[0]) setIdentity(prev => prev.colorPalette ? prev : { ...prev, colorPalette: list[0] })
      })
      .catch(() => {})
  }, [fetchCapabilityStatus, refreshVoiceRuntime])

  const saveIdentity = async () => {
    setBusyAction('identity')
    try {
      await api.post('/api/identity/finalize', {
        user_chosen: identity.adminName || undefined,
        instance_name: identity.systemName || undefined,
        voice_preset: identity.voicePreset,
        color_palette: identity.colorPalette,
      })
      setActionResult({ type: 'success', message: 'Identity saved.' })
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || 'Failed to save identity.' })
    } finally {
      setBusyAction(null)
    }
  }

  const capabilities = useMemo(() => {
    return Array.isArray(capabilityStatus.capabilities) ? capabilityStatus.capabilities : []
  }, [capabilityStatus.capabilities])
  const grouped = useMemo(() => groupCapabilities(capabilities), [capabilities])
  const counts = capabilityStatus.counts || {}
  const total = capabilities.length
  const live = counts.live || capabilities.filter(cap => normalizeStatus(cap.status) === 'live').length
  const needsSetup = capabilities.filter(cap => normalizeStatus(cap.status) !== 'live').length
  const recommended = capabilityStatus.next_recommended_action
  const envList = useMemo(() => {
    return [...new Set(capabilities.flatMap(cap => Array.isArray(cap.missing_env) ? cap.missing_env : []))].sort()
  }, [capabilities])

  const runAction = async (action, capability) => {
    const capLabel = capability?.label || capabilityId(capability)
    if (action === 'configure_env') {
      setActiveSection('settings')
      return
    }
    if (action === 'view_logs') {
      setActiveSection('infrastructure')
      return
    }
    if (action === 'start_managed_runtime' || (action === 'start_service' && capabilityId(capability) === 'ollama_local_model')) {
      setBusyAction(`${action}:${capabilityId(capability)}`)
      try {
        const result = await api.ollama.start()
        await fetchCapabilityStatus()
        const runtime = result?.runtime || {}
        setActionResult({
          type: result?.ok ? 'success' : 'warning',
          message: result?.ok
            ? `Managed Ollama started at ${runtime.host || 'local host'}.`
            : (result?.error || `${capLabel} could not be started.`),
        })
      } catch (error) {
        fetchCapabilityStatus()
        setActionResult({ type: 'error', message: error?.message || `${capLabel} start failed.` })
      } finally {
        setBusyAction(null)
      }
      return
    }
    if (action === 'run_build') {
      setActionResult({ type: 'info', message: 'Frontend build is a terminal action: npm --prefix frontend run build.' })
      return
    }
    if (action === 'bundle_runtime') {
      setActionResult({ type: 'warning', message: 'Packaged Ollama runtime is missing. Bundle runtime/vendor/ollama/ollama or set OLLAMA_BIN before local LLM can run.' })
      return
    }
    if (action === 'pull_recommended_model') {
      setBusyAction(`${action}:${capabilityId(capability)}`)
      setOllamaPullStatus({ status: 'starting', name: capability?.proof?.recommended_model?.model })
      try {
        const finalEvent = await api.ollama.pullRecommended({ onEvent: setOllamaPullStatus })
        await fetchCapabilityStatus()
        const model = finalEvent?.name || finalEvent?.recommendation?.model || capability?.proof?.recommended_model?.model || 'recommended model'
        setActionResult({
          type: finalEvent?.status === 'error' ? 'error' : 'success',
          message: finalEvent?.status === 'error'
            ? (finalEvent.error || `Failed to download ${model}.`)
            : `${model} is installed and selected as the main local model.`,
        })
      } catch (error) {
        setOllamaPullStatus({ status: 'error', error: error?.message || 'Download failed' })
        setActionResult({ type: 'error', message: error?.message || 'Recommended model download failed.' })
      } finally {
        setBusyAction(null)
      }
      return
    }
    if (action === 'pull_model') {
      const proof = capability?.proof || {}
      setActionResult({
        type: 'warning',
        message: `Ollama is running, but ${proof.configured_model || 'the configured model'} is not installed in ${proof.model_home || 'the app model directory'}. Recommended model: ${proof.recommended_model?.model || 'not reported'}.`,
      })
      return
    }
    if (action === 'configure_storage') {
      const proof = capability?.proof || {}
      setActionResult({
        type: 'warning',
        message: `Ollama model storage is low or unavailable at ${proof.model_home || proof.disk?.path || 'the configured model directory'}. Set OLLAMA_MODELS to a larger writable drive before pulling models.`,
      })
      return
    }
    if (action === 'start_service') {
      setActionResult({ type: 'warning', message: `${capLabel} needs its service started outside the browser.` })
      return
    }
    setBusyAction(`${action}:${capabilityId(capability)}`)
    try {
      if (action === 'run_doctor') {
        const readiness = await api.get('/api/readiness')
        setActionResult({
          type: readiness?.degraded ? 'warning' : 'success',
          message: readiness?.degraded
            ? `Doctor check found: ${(readiness.degradedReasons || []).join(', ') || 'degraded state'}`
            : 'Doctor check completed without readiness degradation.',
        })
      } else {
        await fetchCapabilityStatus()
        setActionResult({ type: 'success', message: `${capLabel} check refreshed.` })
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || `${capLabel} action failed.` })
    } finally {
      setBusyAction(null)
    }
  }

  const runVoiceDownload = async (component, options = {}) => {
    setBusyAction(`voice:${component}`)
    setVoiceDownloadStatus({ component, state: 'starting', percent: 0 })
    try {
      const finalEvent = await api.voice.downloadRuntime(
        { component, ...options },
        { onEvent: setVoiceDownloadStatus },
      )
      const runtime = await refreshVoiceRuntime()
      const failedResult = finalEvent?.result?.ok === false
      setActionResult({
        type: finalEvent?.state === 'error' || finalEvent?.type === 'download.error'
          ? 'error'
          : failedResult ? 'warning' : 'success',
        message: finalEvent?.error || finalEvent?.result?.message || `${component} download finished. Current voice recommendation: ${runtime?.recommendation?.label || 'none'}.`,
      })
    } catch (error) {
      setVoiceDownloadStatus({ component, state: 'error', error: error?.message || 'Download failed' })
      setActionResult({ type: 'error', message: error?.message || `${component} download failed.` })
    } finally {
      setBusyAction(null)
    }
  }

  const cancelVoiceDownload = async () => {
    const component = voiceDownloadStatus?.component || null
    setBusyAction('voice:cancel')
    try {
      const result = await api.voice.cancelRuntimeDownload(component ? { component } : {})
      setVoiceDownloadStatus(prev => ({ ...(prev || {}), state: result.cancelled ? 'cancelled' : 'idle', message: result.cancelled ? 'Download cancelled.' : 'No active download to cancel.' }))
      setActionResult({ type: result.cancelled ? 'warning' : 'info', message: result.cancelled ? `Cancelled ${result.component || component || 'voice download'}.` : 'No active voice download was running.' })
      await refreshVoiceRuntime().catch(() => {})
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || 'Voice download cancel failed.' })
    } finally {
      setBusyAction(null)
    }
  }

  const runVoiceDoctor = async () => {
    setBusyAction('voice:doctor')
    try {
      const result = await api.voice.runtimeDoctor()
      setVoiceDoctor(result)
      setVoiceRuntime(result.status || await refreshVoiceRuntime())
      setActionResult({
        type: result.blocking?.length ? 'warning' : 'success',
        message: result.blocking?.length
          ? `Voice doctor found ${result.blocking.length} blocker(s).`
          : 'Voice doctor found no blocking issue.',
      })
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || 'Voice doctor failed.' })
    } finally {
      setBusyAction(null)
    }
  }

  const runVoiceSelfTest = async () => {
    setBusyAction('voice:self-test')
    setVoiceSelfTest(null)
    try {
      const result = await api.voice.runtimeSelfTest({
        voice: 'default',
        text_en: 'System ready. I can speak locally with a natural default voice.',
        text_nl: 'Systeem klaar. Ik kan lokaal spreken met een standaardstem.',
      })
      setVoiceSelfTest(result)
      setVoiceRuntime(result.status_after || await refreshVoiceRuntime())
      setActionResult({
        type: result.blocking?.length ? 'warning' : 'success',
        message: result.blocking?.length
          ? `Voice self-test has ${result.blocking.length} blocking failure(s).`
          : `Voice self-test passed in ${result.elapsed_ms || 0}ms.`,
      })
    } catch (error) {
      const payload = error?.payload
      if (payload?.checks) setVoiceSelfTest(payload)
      if (payload?.status_after) setVoiceRuntime(payload.status_after)
      setActionResult({ type: 'warning', message: error?.message || 'Voice self-test found blockers.' })
    } finally {
      await refreshVoiceRuntime().catch(() => {})
      setBusyAction(null)
    }
  }

  const verifyVoiceBundle = async () => {
    setBusyAction('voice:bundle')
    try {
      const result = await api.voice.verifyBundle({ install: true })
      setVoiceRuntime(result.status || await refreshVoiceRuntime())
      setActionResult({
        type: result?.ok ? 'success' : 'warning',
        message: result?.ok
          ? 'Bundled Default Human Voice verified.'
          : `Default voice bundle is not ready: ${result?.state || 'missing or incomplete'}.`,
      })
    } catch (error) {
      await refreshVoiceRuntime().catch(() => {})
      setActionResult({ type: 'error', message: error?.message || 'Default voice bundle verification failed.' })
    } finally {
      setBusyAction(null)
    }
  }

  const startVoiceRuntime = async () => {
    setBusyAction('voice:start')
    try {
      const result = await api.voice.startRuntime({ component: 'voice_core_local' })
      setVoiceRuntime(result.runtime || await refreshVoiceRuntime())
      setActionResult({
        type: result?.ok ? 'success' : 'warning',
        message: result?.ok
          ? (result.result?.message || 'Default Human Voice checked.')
          : (result?.error || 'Default Human Voice could not start.'),
      })
    } catch (error) {
      await refreshVoiceRuntime().catch(() => {})
      setActionResult({ type: 'error', message: error?.message || 'Default Human Voice start failed.' })
    } finally {
      setBusyAction(null)
    }
  }

  const startFishRuntime = async () => {
    setBusyAction('voice:fish:start')
    try {
      const result = await api.voice.startRuntime({ component: 'fish_speech', accept_personal_license: true })
      setVoiceRuntime(result.runtime || await refreshVoiceRuntime())
      setActionResult({
        type: result?.ok ? 'success' : 'warning',
        message: result?.ok ? 'Fish Speech runtime start requested.' : (result?.error || 'Fish Speech could not start.'),
      })
    } catch (error) {
      await refreshVoiceRuntime().catch(() => {})
      setActionResult({ type: 'error', message: error?.message || 'Fish Speech start failed.' })
    } finally {
      setBusyAction(null)
    }
  }

  const stopVoiceRuntime = async () => {
    setBusyAction('voice:stop')
    try {
      const result = await api.voice.stopRuntime({ component: 'fish_speech' })
      setVoiceRuntime(result.runtime || await refreshVoiceRuntime())
      setActionResult({ type: 'success', message: 'Fish Speech runtime stopped.' })
    } catch (error) {
      await refreshVoiceRuntime().catch(() => {})
      setActionResult({ type: 'error', message: error?.message || 'Fish Speech stop failed.' })
    } finally {
      setBusyAction(null)
    }
  }

  const benchmarkVoiceLite = async () => {
    setBusyAction('voice:benchmark')
    try {
      const result = await api.voice.benchmarkModel({ provider: 'voice_core_local', voice: 'default' })
      setVoiceBenchmark(result)
      await refreshVoiceRuntime().catch(() => {})
      setActionResult({
        type: result?.ok ? 'success' : 'warning',
        message: result?.ok
          ? `Default voice benchmark complete. RTF ${result.average_rtf ?? 'n/a'}, TTFA ${result.average_ttfa_ms ?? 'n/a'}ms.`
          : (result?.message || 'Default voice benchmark could not run.'),
      })
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || 'Default voice benchmark failed.' })
    } finally {
      setBusyAction(null)
    }
  }

  const copyEnvList = async () => {
    const text = envList.length ? envList.join('\n') : 'No missing env vars reported.'
    try {
      await navigator.clipboard.writeText(text)
      setActionResult({ type: 'success', message: 'Missing env variable list copied.' })
    } catch {
      setActionResult({ type: 'warning', message: text })
    }
  }

  const runSmokeTest = async () => {
    setBusyAction('smoke')
    setSmokeResult(null)
    try {
      const result = await api.post('/api/tasks/run', {
        task: 'Run a safe setup smoke test: summarize current system readiness without external actions.',
        user_id: 'user:technical-admin',
      })
      setSmokeResult(result)
      setActionResult({
        type: result?.degraded ? 'warning' : 'success',
        message: result?.degraded ? 'Smoke test completed with degraded/fallback output.' : 'Smoke test completed.',
      })
    } catch (error) {
      setActionResult({ type: 'error', message: error?.message || 'Smoke test failed.' })
    } finally {
      setBusyAction(null)
      fetchCapabilityStatus()
    }
  }

  const voiceTts = voiceRuntime?.tts || {}
  const voiceCore = voiceTts.voice_core_local || {}
  const voiceLite = voiceTts.voice_lite || {}
  const voiceFish = voiceTts.fish_speech || {}
  const voiceStt = voiceRuntime?.stt || {}
  const voiceVad = voiceRuntime?.vad || {}
  const voiceHardware = voiceRuntime?.hardware || {}
  const fishState = voiceFish.state || 'runtime_missing'
  const fishHardwareBlocked = fishState === 'hardware_blocked' || voiceFish.hardware_blocked
  const fishMissingRuntime = fishState === 'runtime_missing' || voiceFish.source_ready === false
  const fishCanStart = voiceFish.model_ready && voiceFish.license_acknowledged && !fishHardwareBlocked && !fishMissingRuntime
  const voiceBusy = typeof busyAction === 'string' && busyAction.startsWith('voice:')
  const voiceDownloadActive = voiceDownloadStatus && ['starting', 'downloading'].includes(voiceDownloadStatus.state)
  const doctorChecks = Array.isArray(voiceDoctor?.checks) ? voiceDoctor.checks : []
  const selfTestChecks = Array.isArray(voiceSelfTest?.checks) ? voiceSelfTest.checks : []
  const voiceLogLines = Array.isArray(voiceLogs?.logs) ? voiceLogs.logs : []
  const bundledSamples = Array.isArray(voiceSamples?.samples) ? voiceSamples.samples : []

  return (
    <main className="setup-center">
      <section className="setup-hero">
        <div>
          <p className="setup-kicker">SYSTEM SETUP CENTER</p>
          <h1>Technical Admin Readiness</h1>
          <p className="setup-hero__copy">
            Verify what is live, what is degraded, what needs configuration, and what the next admin action should be.
          </p>
        </div>
        <div className="setup-hero__actions">
          <button type="button" className="setup-btn" onClick={fetchCapabilityStatus} disabled={capabilityStatus.loading}>
            {capabilityStatus.loading ? 'Checking' : 'Retry checks'}
          </button>
          <button type="button" className="setup-btn setup-btn--quiet" onClick={copyEnvList}>
            Copy env list
          </button>
        </div>
      </section>

      <section className="setup-overview" aria-label="Setup overview">
        <div className="setup-metric">
          <span>Live</span>
          <b>{live}/{total || 0}</b>
        </div>
        <div className="setup-metric setup-metric--warn">
          <span>Needs action</span>
          <b>{needsSetup}</b>
        </div>
        <div className="setup-metric">
          <span>Last checked</span>
          <b>{fmtTime(capabilityStatus.checked_at || capabilityStatus.lastChecked)}</b>
        </div>
        <div className="setup-next">
          <span>Next admin action</span>
          <b>{recommended?.label || 'No blocker selected'}</b>
          <small>{recommended?.details || 'Run checks to refresh the recommendation.'}</small>
        </div>
      </section>

      {actionResult && (
        <div className={`setup-alert setup-alert--${actionResult.type || 'info'}`}>
          {actionResult.message}
        </div>
      )}
      {ollamaPullStatus && (
        <div className={`setup-alert setup-alert--${ollamaPullStatus.error ? 'error' : 'info'}`}>
          {formatOllamaPullStatus(ollamaPullStatus)}
        </div>
      )}
      {voiceDownloadStatus && (
        <div className={`setup-alert setup-alert--${voiceDownloadStatus.error ? 'error' : 'info'}`}>
          {formatVoiceDownloadStatus(voiceDownloadStatus)}
        </div>
      )}

      <section className="setup-panel setup-voice">
        <div className="setup-panel__head">
          <div>
            <p className="setup-kicker">VOICE RUNTIME</p>
            <h2>Default Human Voice, bundled and local</h2>
          </div>
          <button type="button" className="setup-btn setup-btn--small" onClick={refreshVoiceRuntime} disabled={voiceBusy}>
            Refresh voice
          </button>
        </div>
        <div className="setup-voice__hardware">
          <span>CPU: {voiceHardware.cpu || 'unknown'}</span>
          <span>RAM: {voiceHardware.ram_gib ? `${voiceHardware.ram_gib} GiB` : 'unknown'}</span>
          <span>
            GPU: {voiceHardware.gpu?.name || 'none'}
            {voiceHardware.gpu?.vram_mib ? ` / ${(voiceHardware.gpu.vram_mib / 1024).toFixed(1)} GiB VRAM` : ''}
          </span>
          <span>Driver: {voiceHardware.gpu?.driver_status || 'unknown'}</span>
        </div>
        <div className="setup-voice__rows">
          <div className="setup-voice__row">
            <div>
              <b>Default Human Voice: {voiceCore.state === 'ready' ? 'Ready' : 'Not ready'}</b>
              <p>
                No voice training required. EN: {voiceCore.tts_en_ready ? `Kokoro ${voiceCore.active_voice?.voice || 'af_heart'}` : 'missing bundled Kokoro voice'}.
                {' '}NL: {voiceCore.tts_nl_ready ? 'Piper nl_NL-mls-medium' : 'missing bundled Dutch voice'}.
              </p>
              <small>
                No GPU / no internet after packaging / active root: {voiceCore.active_root || 'not found'} / RTF: {voiceCore.rtf ?? 'not benchmarked'} / TTFA: {voiceCore.ttfa_ms ?? 'not benchmarked'}ms
              </small>
            </div>
            <div className="setup-voice__actions">
              <StatusBadge status={voiceStatusToSetup(voiceCore.state || voiceTts.state)} />
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={verifyVoiceBundle}
                disabled={voiceBusy || voiceCore.state === 'ready'}
                title="Verifies the packaged voice-core manifest, runtimes, models, and checksums."
              >
                Verify Bundle
              </button>
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={startVoiceRuntime}
                disabled={voiceBusy}
              >
                Start Voice
              </button>
              <button
                type="button"
                className="setup-btn setup-btn--small setup-btn--quiet"
                onClick={benchmarkVoiceLite}
                disabled={voiceBusy || voiceCore.state !== 'ready'}
              >
                Benchmark
              </button>
            </div>
          </div>
          <div className="setup-voice__row">
            <div>
              <b>Optional Compatibility: Voice Lite CPU</b>
              <p>
                Runtime: {voiceLite.runtime_ready ? voiceLite.runtime?.binary : 'missing Piper/ONNX runtime'}.
                {' '}EN base: {voiceLite.base_en_ready ? 'ready' : 'missing'}.
                {' '}NL base: {voiceLite.base_nl_ready ? 'ready' : 'missing'}.
              </p>
              <small>
                Optional repair/fallback path only. It is not custom voice training and is not required when Default Human Voice is ready.
              </small>
            </div>
            <div className="setup-voice__actions">
              <StatusBadge status={voiceStatusToSetup(voiceLite.state || voiceTts.state)} />
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={() => runVoiceDownload('voice_lite_runtime')}
                disabled={voiceBusy || voiceLite.runtime_ready}
              >
                Repair Runtime
              </button>
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={() => runVoiceDownload('voice_lite_base_en')}
                disabled={voiceBusy || voiceLite.base_en_ready}
              >
                Repair EN
              </button>
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={() => runVoiceDownload('voice_lite_base_nl')}
                disabled={voiceBusy || voiceLite.base_nl_ready}
              >
                Repair NL
              </button>
            </div>
          </div>
          <div className="setup-voice__row">
            <div>
              <b>Recommended STT: Whisper base.en</b>
              <p>{voiceStt.model_ready ? `Installed at ${voiceStt.model_path}` : `Missing model at ${voiceStt.model_path || 'voice model directory'}.`}</p>
              {voiceStt.runtime?.binary ? <small>Runtime: {voiceStt.runtime.binary}</small> : <small>Runtime missing: bundle whisper.cpp or set WHISPER_CPP_BIN.</small>}
            </div>
            <div className="setup-voice__actions">
              <StatusBadge status={voiceStatusToSetup(voiceStt.state)} />
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={() => runVoiceDownload('whisper_model')}
                disabled={voiceBusy || voiceStt.model_ready}
              >
                Download Whisper
              </button>
            </div>
          </div>
          <div className="setup-voice__row">
            <div>
              <b>VAD: Silero ONNX</b>
              <p>{voiceVad.model_ready ? `Installed at ${voiceVad.model_path}` : 'Missing VAD model. Simple RMS fallback is active until downloaded.'}</p>
              <small>Used for no-speech detection and silence gating.</small>
            </div>
            <div className="setup-voice__actions">
              <StatusBadge status={voiceStatusToSetup(voiceVad.state)} />
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={() => runVoiceDownload('vad_model')}
                disabled={voiceBusy || voiceVad.model_ready}
              >
                Download VAD
              </button>
            </div>
          </div>
          {voiceBenchmark && (
            <div className="setup-voice__row">
              <div>
                <b>Last Default Voice Benchmark</b>
                <p>RTF {voiceBenchmark.average_rtf ?? 'n/a'} / TTFA {voiceBenchmark.average_ttfa_ms ?? 'n/a'}ms.</p>
                <small>Benchmarks use bundled EN/NL default voices and subtle emotion presets.</small>
              </div>
            </div>
          )}
          <div className="setup-voice__row">
            <div>
              <b>Fish S2-Pro TTS</b>
              <p>
                {fishHardwareBlocked
                  ? voiceFish.hardware_reason || 'Fish Speech is not recommended on this hardware.'
                  : voiceFish.model_ready
                    ? `Model installed at ${voiceFish.model_path}`
                    : `Model missing at ${voiceFish.model_path || 'Fish model directory'}.`}
              </p>
              <small>
                Runtime: {voiceFish.source_ready ? voiceFish.source_path : 'missing Fish Speech runtime source'}
                {voiceFish.license_acknowledged ? ' / license acknowledged for personal-local use' : ' / license acknowledgement required'}
              </small>
            </div>
            <div className="setup-voice__actions">
              <StatusBadge status={voiceStatusToSetup(fishState)} />
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={() => runVoiceDownload('fish_speech', { accept_personal_license: true })}
                disabled={voiceBusy || fishHardwareBlocked || voiceFish.model_ready}
                title={fishHardwareBlocked ? 'Fish Speech download is hardware-gated on this PC.' : 'Download Fish S2-Pro model assets for personal-local use.'}
              >
                Download Fish
              </button>
              <button
                type="button"
                className="setup-btn setup-btn--small"
                onClick={startFishRuntime}
                disabled={voiceBusy || !fishCanStart}
              >
                Start Fish
              </button>
              <button
                type="button"
                className="setup-btn setup-btn--small setup-btn--quiet"
                onClick={stopVoiceRuntime}
                disabled={voiceBusy || !voiceFish.process_running}
              >
                Stop Fish
              </button>
            </div>
          </div>
        </div>
        <div className="setup-voice__recommendation">
          <b>{voiceRuntime?.recommendation?.label || 'Voice runtime not checked'}</b>
          <span>{voiceRuntime?.recommendation?.details || voiceRuntime?.error || 'Run a voice refresh to inspect local speech readiness.'}</span>
        </div>
        <div className="setup-voice-lab">
          <div className="setup-voice-lab__head">
            <div>
              <b>Voice Test Lab</b>
              <span>Run production checks for runtime readiness, local TTS, STT readiness, VAD gating, logs, and sample playback.</span>
            </div>
            <div className="setup-voice__actions">
              <button type="button" className="setup-btn setup-btn--small" onClick={runVoiceDoctor} disabled={voiceBusy}>
                Run Doctor
              </button>
              <button type="button" className="setup-btn setup-btn--small" onClick={runVoiceSelfTest} disabled={voiceBusy}>
                Run Self-Test
              </button>
              <button type="button" className="setup-btn setup-btn--small setup-btn--quiet" onClick={cancelVoiceDownload} disabled={!voiceDownloadActive || busyAction === 'voice:cancel'}>
                Cancel Download
              </button>
            </div>
          </div>
          <div className="setup-voice-lab__grid">
            <div className="setup-voice-lab__panel">
              <div className="setup-kicker">DOCTOR CHECKS</div>
              {doctorChecks.length ? doctorChecks.map(check => (
                <div key={check.id} className={`setup-voice-check setup-voice-check--${check.state}`}>
                  <span>{check.label}</span>
                  <b>{check.state}</b>
                  <small>{check.message}</small>
                </div>
              )) : (
                <p className="setup-voice-lab__empty">Run Doctor to see exact blockers.</p>
              )}
            </div>
            <div className="setup-voice-lab__panel">
              <div className="setup-kicker">SELF-TEST</div>
              {voiceSelfTest && (
                <div className="setup-voice-lab__summary">
                  <span>{voiceSelfTest.ok ? 'Pass' : 'Has blockers'}</span>
                  <span>{voiceSelfTest.elapsed_ms ?? 0}ms</span>
                  <span>{voiceSelfTest.blocking?.length || 0} blockers</span>
                </div>
              )}
              {selfTestChecks.length ? selfTestChecks.map(check => (
                <div key={check.id} className={`setup-voice-check setup-voice-check--${check.state}`}>
                  <span>{check.label}</span>
                  <b>{check.state}</b>
                  <small>{check.message}</small>
                </div>
              )) : (
                <p className="setup-voice-lab__empty">Run Self-Test to generate EN/NL voice samples when runtime and models are ready.</p>
              )}
              {voiceSelfTest?.artifacts?.length > 0 && (
                <div className="setup-voice-samples">
                  {voiceSelfTest.artifacts.map(artifact => (
                    <a key={artifact.id || artifact.url} href={artifact.url} target="_blank" rel="noreferrer">
                      {artifact.language?.toUpperCase() || 'AUDIO'} sample
                    </a>
                  ))}
                </div>
              )}
              {bundledSamples.length > 0 && (
                <div className="setup-voice-samples">
                  {bundledSamples.map(sample => sample.exists ? (
                    <a key={sample.id} href={sample.url} target="_blank" rel="noreferrer">
                      {sample.language?.toUpperCase() || 'AUDIO'} bundled sample
                    </a>
                  ) : (
                    <span key={sample.id}>{sample.language?.toUpperCase() || 'AUDIO'} sample missing</span>
                  ))}
                </div>
              )}
            </div>
            <div className="setup-voice-lab__panel setup-voice-lab__panel--logs">
              <div className="setup-kicker">RUNTIME LOGS</div>
              {voiceLogLines.length ? voiceLogLines.map((line, index) => (
                <div key={`${line.ts || index}-${index}`} className="setup-voice-log">
                  <span>{fmtTime(line.ts)}</span>
                  <b>{line.level || 'info'}</b>
                  <small>{line.message}</small>
                </div>
              )) : (
                <p className="setup-voice-lab__empty">No voice runtime logs yet.</p>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="setup-grid">
        <div className="setup-panel setup-panel--wizard">
          <div className="setup-panel__head">
            <div>
              <p className="setup-kicker">FIRST-RUN WIZARD</p>
              <h2>Admin setup path</h2>
            </div>
            <button type="button" className="setup-btn setup-btn--small" onClick={() => setActiveStep('identity')}>
              Reopen
            </button>
          </div>
          <div className="setup-wizard">
            <div className="setup-wizard__steps">
              {WIZARD_STEPS.map(step => {
                const status = deriveWizardStatus(step, capabilities)
                return (
                  <button
                    key={step.id}
                    type="button"
                    className={`setup-step ${activeStep === step.id ? 'setup-step--active' : ''}`}
                    onClick={() => setActiveStep(step.id)}
                  >
                    <span>{step.label}</span>
                    <StatusBadge status={status} />
                  </button>
                )
              })}
            </div>
            <div className="setup-wizard__body">
              {WIZARD_STEPS.filter(step => step.id === activeStep).map(step => (
                <div key={step.id}>
                  <p className="setup-kicker">{step.label}</p>
                  <h3>{step.detail}</h3>
                  {step.id === 'identity' && (
                    <div className="setup-fields">
                      <label>
                        <span>System name</span>
                        <input value={identity.systemName} onChange={event => setIdentity({ ...identity, systemName: event.target.value })} />
                      </label>
                      <label>
                        <span>Admin owner</span>
                        <input value={identity.adminName} onChange={event => setIdentity({ ...identity, adminName: event.target.value })} />
                      </label>
                      <div className="setup-field-group">
                        <span>Voice preset</span>
                        <div className="setup-chips">
                          {['professional', 'friendly', 'creative', 'concise'].map(preset => (
                            <button
                              key={preset}
                              type="button"
                              className={`setup-chip ${identity.voicePreset === preset ? 'setup-chip--active' : ''}`}
                              onClick={() => setIdentity({ ...identity, voicePreset: preset })}
                            >
                              {preset.charAt(0).toUpperCase() + preset.slice(1)}
                            </button>
                          ))}
                        </div>
                      </div>
                      {palettes.length > 0 && (
                        <div className="setup-field-group">
                          <span>Accent palette</span>
                          <div className="setup-palette-grid">
                            {palettes.map((palette, idx) => (
                              <button
                                key={idx}
                                type="button"
                                className={`setup-swatch ${identity.colorPalette?.primary === palette.primary ? 'setup-swatch--active' : ''}`}
                                style={{ background: `linear-gradient(135deg, ${palette.primary}, ${palette.accent})` }}
                                onClick={() => setIdentity({ ...identity, colorPalette: palette })}
                                title={`Palette ${idx + 1}`}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                      <button type="button" className="setup-btn" onClick={saveIdentity} disabled={busyAction === 'identity'}>
                        {busyAction === 'identity' ? 'Saving…' : 'Save identity'}
                      </button>
                    </div>
                  )}
                  {step.id === 'smoke' && (
                    <button type="button" className="setup-btn" onClick={runSmokeTest} disabled={busyAction === 'smoke'}>
                      {busyAction === 'smoke' ? 'Running smoke test' : 'Run safe smoke test'}
                    </button>
                  )}
                  {step.id !== 'identity' && step.id !== 'smoke' && (
                    <div className="setup-step__hint">
                      Review the capability matrix below. Fallback, dry-run, mock, and unavailable states are not treated as live success.
                    </div>
                  )}
                </div>
              ))}
              {smokeResult && (
                <div className="setup-smoke">
                  <div><b>Status:</b> {smokeResult.status || (smokeResult.ok ? 'completed' : 'failed')}</div>
                  <div><b>Turn:</b> {smokeResult.turn_id || smokeResult.taskId || 'not returned'}</div>
                  <div><b>Source:</b> {smokeResult.source || 'unknown'}</div>
                  <div><b>Proof items:</b> {(smokeResult.proof || []).length + (smokeResult.artifacts || []).length}</div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="setup-panel">
          <div className="setup-panel__head">
            <div>
              <p className="setup-kicker">USER READINESS</p>
              <h2>After technical setup</h2>
            </div>
          </div>
          <div className="setup-users">
            {USER_READINESS.map(profile => {
              const readiness = deriveUserReadiness(profile, capabilities)
              return (
                <div key={profile.id} className="setup-user">
                  <div className="setup-user__head">
                    <b>{profile.label}</b>
                    <StatusBadge status={readiness.status} />
                  </div>
                  <p>{profile.outcome}</p>
                  {readiness.blockers.length > 0 && (
                    <ul>
                      {readiness.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="setup-panel">
        <div className="setup-panel__head">
          <div>
            <p className="setup-kicker">CAPABILITY MATRIX</p>
            <h2>Installed, configured, live, or blocked</h2>
          </div>
          {capabilityStatus.error && <span className="setup-error">{capabilityStatus.error}</span>}
        </div>
        <div className="setup-cap-groups">
          {grouped.map(([category, items]) => (
            <div key={category} className="setup-cap-group">
              <div className="setup-cap-group__title">{category}</div>
              {items
                .sort((a, b) => statusSeverity(b.status) - statusSeverity(a.status) || String(a.label).localeCompare(String(b.label)))
                .map(capability => (
                  <CapabilityRow
                    key={capabilityId(capability)}
                    capability={capability}
                    onAction={runAction}
                    busy={busyAction}
                  />
                ))}
            </div>
          ))}
          {!grouped.length && (
            <div className="setup-empty">
              Capability data is unavailable. Check authentication, then retry setup checks.
            </div>
          )}
        </div>
      </section>
    </main>
  )
}

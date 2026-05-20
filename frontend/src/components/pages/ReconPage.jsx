import { useEffect, useMemo, useState } from 'react'
import { Panel, SectionLabel, StatusPill, EmptyState, ErrorState, toastError, toastSuccess, toastWarn } from '../nexus-ui'
import api from '../../api/client'
import './ReconPage.css'

const CATEGORY_ORDER = ['all', 'osint', 'defensive_review', 'phishing', 'special']
const CATEGORY_LABELS = {
  all: 'All',
  osint: 'OSINT',
  defensive_review: 'Defensive Review',
  phishing: 'Phishing Defense',
  special: 'Special',
}
const MODE_LABELS = {
  safe: 'LOCAL',
  passive_network: 'POLICY',
  defensive_simulation: 'SIM',
}
const SEVERITIES = ['info', 'low', 'medium', 'high']

function modeTone(mode) {
  if (mode === 'passive_network') return 'warn'
  if (mode === 'defensive_simulation') return 'gold'
  return 'success'
}

function jsonPreview(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value ?? '')
  }
}

function ReconToolCard({ tool, active, onSelect }) {
  return (
    <button className={`recon-tool ${active ? 'recon-tool--active' : ''}`} onClick={() => onSelect(tool)}>
      <div className="recon-tool__head">
        <span className="recon-tool__name">{tool.name}</span>
        <StatusPill label={MODE_LABELS[tool.mode] || tool.mode} tone={modeTone(tool.mode)} size="sm" />
      </div>
      <div className="recon-tool__meta">{tool.categoryLabel || CATEGORY_LABELS[tool.category] || tool.category}</div>
      <div className="recon-tool__desc">{tool.description}</div>
    </button>
  )
}

function CaseScope({ cases, selectedCaseId, setSelectedCaseId, onCreated }) {
  const [draft, setDraft] = useState({ name: '', target: '', owner: '', authorization: '' })
  const [busy, setBusy] = useState(false)

  async function createCase() {
    if (!draft.name.trim() || !draft.target.trim()) {
      toastWarn('Case name and target are required')
      return
    }
    setBusy(true)
    try {
      const data = await api.recon.createCase(draft)
      onCreated(data.case)
      setSelectedCaseId(data.case.id)
      setDraft({ name: '', target: '', owner: '', authorization: '' })
      toastSuccess('Recon case created')
    } catch (err) {
      toastError(err.message || 'Could not create recon case')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title="Case Scope" className="recon-panel">
      <div className="recon-safe-banner">
        <span className="recon-safe-banner__mark">SAFE</span>
        <span>Safe recon and defensive local analysis only. High-risk offensive tooling is not available on this page.</span>
      </div>
      <div className="recon-form-grid">
        <label>
          <span>Active Case</span>
          <select value={selectedCaseId} onChange={e => setSelectedCaseId(e.target.value)}>
            <option value="">No case selected</option>
            {cases.map(item => <option key={item.id} value={item.id}>{item.name} - {item.target}</option>)}
          </select>
        </label>
        <label>
          <span>Case Name</span>
          <input value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="Client brand review" />
        </label>
        <label>
          <span>Target</span>
          <input value={draft.target} onChange={e => setDraft({ ...draft, target: e.target.value })} placeholder="domain, account, header dump, URL, or local artifact" />
        </label>
        <label>
          <span>Owner</span>
          <input value={draft.owner} onChange={e => setDraft({ ...draft, owner: e.target.value })} placeholder="operator" />
        </label>
      </div>
      <label className="recon-full">
        <span>Authorization Notes</span>
        <textarea value={draft.authorization} onChange={e => setDraft({ ...draft, authorization: e.target.value })} rows={3} placeholder="Scope, owner approval, and offline/online policy notes" />
      </label>
      <div className="recon-actions">
        <button className="recon-btn recon-btn--primary" onClick={createCase} disabled={busy}>{busy ? 'Creating...' : 'Create Case'}</button>
        <StatusPill label="OFFLINE FIRST" tone="success" size="sm" />
      </div>
    </Panel>
  )
}

function FindingsPanel({ findings, selectedCaseId, selectedTool, result, onSaved }) {
  const [severity, setSeverity] = useState('info')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

  async function saveFinding() {
    if (!result) {
      toastWarn('Run a tool before saving a finding')
      return
    }
    setBusy(true)
    try {
      const payload = {
        case_id: selectedCaseId,
        title: title.trim() || `${selectedTool?.name || 'Recon'} result`,
        severity,
        source_tool: selectedTool?.id || '',
        evidence: result.result || result,
      }
      const data = await api.recon.createFinding(payload)
      onSaved(data.finding)
      setTitle('')
      setSeverity('info')
      toastSuccess('Finding saved')
    } catch (err) {
      toastError(err.message || 'Could not save finding')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title="Findings" className="recon-panel">
      <div className="recon-finding-form">
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Finding title" />
        <select value={severity} onChange={e => setSeverity(e.target.value)}>
          {SEVERITIES.map(item => <option key={item} value={item}>{item.toUpperCase()}</option>)}
        </select>
        <button className="recon-btn" onClick={saveFinding} disabled={busy || !result}>{busy ? 'Saving...' : 'Save Result'}</button>
      </div>
      <div className="recon-list">
        {!findings.length && <EmptyState title="No findings yet" sub="Run a safe tool and save useful evidence to this case." />}
        {findings.map(item => (
          <div key={item.id} className={`recon-finding recon-finding--${item.severity}`}>
            <div className="recon-finding__head">
              <span>{item.title}</span>
              <StatusPill label={item.severity?.toUpperCase?.() || 'INFO'} tone={item.severity === 'high' ? 'alert' : item.severity === 'medium' ? 'warn' : 'cool'} size="sm" />
            </div>
            <div className="recon-finding__meta">{item.source_tool || 'manual'} · {new Date(item.created_at).toLocaleString()}</div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

export default function ReconPage() {
  const [tools, setTools] = useState([])
  const [categories, setCategories] = useState({})
  const [cases, setCases] = useState([])
  const [findings, setFindings] = useState([])
  const [audit, setAudit] = useState([])
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [selectedTool, setSelectedTool] = useState(null)
  const [query, setQuery] = useState('')
  const [input, setInput] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    setError(null)
    try {
      const [toolData, caseData, auditData] = await Promise.all([
        api.recon.tools(),
        api.recon.cases(),
        api.recon.audit(),
      ])
      const nextTools = Array.isArray(toolData.tools) ? toolData.tools : []
      setTools(nextTools)
      setCategories(toolData.categories || {})
      setCases(Array.isArray(caseData.cases) ? caseData.cases : [])
      setAudit(Array.isArray(auditData.audit) ? auditData.audit : [])
      setSelectedTool(current => current || nextTools[0] || null)
    } catch (err) {
      setError(err.message || 'Recon API unavailable')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    api.recon.findings(selectedCaseId)
      .then(data => setFindings(Array.isArray(data.findings) ? data.findings : []))
      .catch(() => setFindings([]))
  }, [selectedCaseId])

  const filteredTools = useMemo(() => {
    const q = query.trim().toLowerCase()
    return tools.filter(tool => {
      if (selectedCategory !== 'all' && tool.category !== selectedCategory) return false
      if (!q) return true
      return `${tool.name} ${tool.description || ''} ${(tool.keywords || []).join(' ')}`.toLowerCase().includes(q)
    })
  }, [tools, selectedCategory, query])

  async function handleSearch() {
    if (!query.trim()) return
    setBusy(true)
    try {
      const data = await api.recon.search(query)
      if (data.matches?.length) {
        setSelectedTool(data.matches[0])
        toastSuccess(`Matched ${data.matches[0].name}`)
      } else {
        toastWarn('No safe recon tool matched that query')
      }
    } catch (err) {
      toastError(err.message || 'Recon search failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleRun() {
    if (!selectedTool) return
    setBusy(true)
    setResult(null)
    try {
      const data = await api.recon.runTool({ tool_id: selectedTool.id, input, case_id: selectedCaseId })
      setResult(data)
      if (data?.result?.blocked) toastWarn('Blocked by Recon policy')
      else toastSuccess('Recon tool completed')
      api.recon.audit().then(a => setAudit(Array.isArray(a.audit) ? a.audit : [])).catch(() => {})
    } catch (err) {
      setResult({ ok: false, error: err.message })
      toastError(err.message || 'Recon tool failed')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="recon-page"><Panel title="Recon"><EmptyState title="Loading Recon" sub="Fetching safe tool catalog and case state." /></Panel></div>
  }

  if (error) {
    return <div className="recon-page"><ErrorState title="Recon unavailable" message={error} action="Retry" onAction={load} /></div>
  }

  return (
    <div className="recon-page">
      <header className="recon-header">
        <div>
          <div className="recon-kicker">SAFE RECON</div>
          <h1>Recon Workspace</h1>
          <p>Case-based OSINT and defensive local analysis for authorized work.</p>
        </div>
        <div className="recon-header__pills">
          <StatusPill label={`${tools.length} TOOLS`} tone={tools.length ? 'success' : 'idle'} />
          <StatusPill label="NO OFFENSIVE SURFACE" tone="gold" />
        </div>
      </header>

      <CaseScope
        cases={cases}
        selectedCaseId={selectedCaseId}
        setSelectedCaseId={setSelectedCaseId}
        onCreated={item => setCases(prev => [item, ...prev])}
      />

      <div className="recon-grid">
        <Panel title="Tool Catalog" className="recon-panel recon-panel--catalog">
          <div className="recon-search">
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a safe recon or defensive review tool..." />
            <button className="recon-btn" onClick={handleSearch} disabled={busy || !query.trim()}>AI Search</button>
          </div>
          <div className="recon-cats">
            {CATEGORY_ORDER.filter(id => id === 'all' || categories[id]).map(id => (
              <button key={id} className={`recon-cat ${selectedCategory === id ? 'recon-cat--active' : ''}`} onClick={() => setSelectedCategory(id)}>
                {CATEGORY_LABELS[id] || categories[id] || id}
              </button>
            ))}
          </div>
          <div className="recon-tools">
            {!filteredTools.length && <EmptyState title="No tools available" sub="The safe Recon catalog is empty or filtered out." />}
            {filteredTools.map(tool => (
              <ReconToolCard key={tool.id} tool={tool} active={selectedTool?.id === tool.id} onSelect={tool => { setSelectedTool(tool); setResult(null) }} />
            ))}
          </div>
        </Panel>

        <Panel title={selectedTool ? selectedTool.name : 'Runner'} className="recon-panel recon-panel--runner">
          {selectedTool ? (
            <>
              <div className="recon-runner__meta">
                <StatusPill label={MODE_LABELS[selectedTool.mode] || selectedTool.mode} tone={modeTone(selectedTool.mode)} size="sm" />
                <span>{selectedTool.categoryLabel}</span>
              </div>
              <p className="recon-runner__desc">{selectedTool.description}</p>
              {selectedTool.mode === 'passive_network' && (
                <div className="recon-policy-note">This tool is policy-gated. Offline-first mode blocks network-backed lookups unless explicitly enabled.</div>
              )}
              <textarea value={input} onChange={e => setInput(e.target.value)} rows={8} placeholder="Paste a URL, header block, token, hash, domain, or other authorized input..." />
              <div className="recon-actions">
                <button className="recon-btn recon-btn--primary" onClick={handleRun} disabled={busy}>{busy ? 'Running...' : 'Run Safe Tool'}</button>
                <button className="recon-btn" onClick={() => { setInput(''); setResult(null) }}>Clear</button>
              </div>
              {result && (
                <div className={`recon-result ${result.ok === false ? 'recon-result--error' : ''}`}>
                  <SectionLabel>Result</SectionLabel>
                  <pre>{jsonPreview(result.result || result)}</pre>
                </div>
              )}
            </>
          ) : (
            <EmptyState title="Select a tool" sub="Choose a safe recon tool from the catalog." />
          )}
        </Panel>
      </div>

      <div className="recon-grid recon-grid--bottom">
        <FindingsPanel
          findings={findings}
          selectedCaseId={selectedCaseId}
          selectedTool={selectedTool}
          result={result}
          onSaved={item => setFindings(prev => [item, ...prev])}
        />
        <Panel title="Audit Trail" className="recon-panel">
          <div className="recon-audit">
            {!audit.length && <EmptyState title="No audit events" sub="Tool searches, runs, and findings appear here." />}
            {audit.map(item => (
              <div key={item.id} className="recon-audit__row">
                <span>{new Date(item.ts).toLocaleTimeString()}</span>
                <strong>{item.action}</strong>
                <code>{jsonPreview(item.payload).slice(0, 160)}</code>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}

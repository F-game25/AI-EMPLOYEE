import { useState, useEffect, useMemo, useCallback } from 'react'
import './AIOutputPage.css'

// One screen for ALL AI work output — skill deliverables, research reports, media,
// code — made USABLE: preview, copy, download, open. Backed by /api/proof/center
// (artifact files) + /api/research/deep (research reports).

const authHeaders = () => {
  const t = sessionStorage.getItem('ai_jwt') || ''
  return { 'content-type': 'application/json', ...(t ? { authorization: `Bearer ${t}` } : {}) }
}

const extOf = (name = '') => (name.split('.').pop() || '').toLowerCase()
const fmtBytes = (b) => (!b ? '' : b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`)
const fmtDate = (d) => { try { return new Date(d).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) } catch { return '' } }

const CATEGORY = (name = '', source = '') => {
  const e = extOf(name)
  if (['mp4', 'mov', 'webm'].includes(e)) return 'media'
  if (['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(e)) return 'media'
  if (['py', 'js', 'ts', 'tsx', 'jsx', 'json', 'sh', 'rs', 'go'].includes(e)) return 'code'
  if (source === 'research') return 'research'
  return 'content' // .md and the rest = written deliverables
}

const ICON = { content: '📄', research: '🔬', media: '🎬', code: '🧩' }

// Minimal, dependency-free markdown rendered as REACT ELEMENTS (React escapes all
// text → XSS-safe even though artifacts are AI-generated; no dangerouslySetInnerHTML).
function inline(text) {
  // Split on **bold** and `code`, keeping the delimiters, into React nodes.
  const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) return <strong key={i}>{p.slice(2, -2)}</strong>
    if (/^`[^`]+`$/.test(p)) return <code key={i}>{p.slice(1, -1)}</code>
    return p
  })
}
function MarkdownView({ text }) {
  const lines = String(text || '').split('\n')
  return (
    <div className="aiout__md">
      {lines.map((ln, i) => {
        if (ln.startsWith('### ')) return <h3 key={i}>{inline(ln.slice(4))}</h3>
        if (ln.startsWith('## ')) return <h2 key={i}>{inline(ln.slice(3))}</h2>
        if (ln.startsWith('# ')) return <h1 key={i}>{inline(ln.slice(2))}</h1>
        if (/^[-*] /.test(ln)) return <div key={i} className="aiout__li">• {inline(ln.slice(2))}</div>
        if (!ln.trim()) return <div key={i} className="aiout__br" />
        return <p key={i}>{inline(ln)}</p>
      })}
    </div>
  )
}

export default function AIOutputPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('all')
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(null)
  const [preview, setPreview] = useState({ status: 'idle', text: '', url: '' })
  const [copied, setCopied] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    Promise.allSettled([
      fetch('/api/proof/center', { headers: authHeaders() }).then(r => r.json()),
      fetch('/api/research/deep', { headers: authHeaders() }).then(r => r.json()),
    ]).then(([proof, research]) => {
      const out = []
      const pc = proof.status === 'fulfilled' ? proof.value : {}
      for (const a of (pc.artifactFiles || pc.artifacts || [])) {
        out.push({ id: a.id || `artifact:${a.name}`, name: a.name, url: a.url,
                   size: a.size, created_at: a.created_at, source: a.source || 'artifact',
                   kind: 'artifact', category: CATEGORY(a.name, a.source) })
      }
      const rep = research.status === 'fulfilled' ? research.value : {}
      for (const r of (rep.reports || [])) {
        out.push({ id: `research:${r.id}`, name: r.topic || r.id, report_id: r.id,
                   created_at: r.created_at ? new Date(r.created_at * 1000).toISOString() : r.updated_at,
                   status: r.status, source: 'research', kind: 'research', category: 'research' })
      }
      out.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
      setItems(out)
      setLoading(false)
    })
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => items.filter(i =>
    (tab === 'all' || i.category === tab) &&
    (!q || (i.name || '').toLowerCase().includes(q.toLowerCase()))
  ), [items, tab, q])

  const openItem = useCallback((it) => {
    setSelected(it); setCopied(false); setPreview({ status: 'loading', text: '', url: '' })
    if (it.kind === 'research') {
      fetch(`/api/research/deep/${it.report_id}`, { headers: authHeaders() })
        .then(r => r.json())
        .then(d => setPreview({ status: 'ready', text: d.report?.report_md || d.report?.executive_summary || '(no content)', url: '' }))
        .catch(() => setPreview({ status: 'error', text: '', url: '' }))
      return
    }
    const cat = it.category
    if (cat === 'media') { setPreview({ status: 'ready', text: '', url: it.url }); return }
    // text/code/content → fetch the file body
    fetch(it.url, { headers: authHeaders() })
      .then(r => r.text())
      .then(t => setPreview({ status: 'ready', text: t, url: it.url }))
      .catch(() => setPreview({ status: 'error', text: '', url: '' }))
  }, [])

  const copy = () => { navigator.clipboard?.writeText(preview.text || '').then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }) }
  const download = () => {
    const blob = new Blob([preview.text || ''], { type: 'text/plain' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = selected?.name?.includes('.') ? selected.name : `${selected?.name || 'output'}.txt`
    a.click(); URL.revokeObjectURL(a.href)
  }

  const counts = useMemo(() => {
    const c = { all: items.length, content: 0, research: 0, media: 0, code: 0 }
    for (const i of items) c[i.category] = (c[i.category] || 0) + 1
    return c
  }, [items])

  return (
    <div className="aiout">
      <div className="aiout__head">
        <div>
          <h1 className="aiout__title">AI Output</h1>
          <p className="aiout__sub">Every result the AI has produced — open, copy, download, use.</p>
        </div>
        <button className="aiout__refresh" onClick={load}>↻ Refresh</button>
      </div>

      <div className="aiout__bar">
        <div className="aiout__tabs">
          {['all', 'content', 'research', 'media', 'code'].map(t => (
            <button key={t} className={`aiout__tab ${tab === t ? 'is-active' : ''}`} onClick={() => setTab(t)}>
              {t === 'all' ? 'All' : `${ICON[t] || ''} ${t[0].toUpperCase()}${t.slice(1)}`} <span className="aiout__count">{counts[t] || 0}</span>
            </button>
          ))}
        </div>
        <input className="aiout__search" placeholder="Search outputs…" value={q} onChange={e => setQ(e.target.value)} />
      </div>

      <div className="aiout__body">
        <div className="aiout__list">
          {loading && <div className="aiout__empty">Loading outputs…</div>}
          {!loading && filtered.length === 0 && <div className="aiout__empty">No outputs yet — ask the teammate to produce something.</div>}
          {filtered.map(it => (
            <button key={it.id} className={`aiout__item ${selected?.id === it.id ? 'is-selected' : ''}`} onClick={() => openItem(it)}>
              <span className="aiout__item-icon">{ICON[it.category] || '📄'}</span>
              <span className="aiout__item-main">
                <span className="aiout__item-name">{it.name}</span>
                <span className="aiout__item-meta">{it.source}{it.status ? ` · ${it.status}` : ''}{it.size ? ` · ${fmtBytes(it.size)}` : ''} · {fmtDate(it.created_at)}</span>
              </span>
            </button>
          ))}
        </div>

        <div className="aiout__preview">
          {!selected && <div className="aiout__empty">Select an output to view it.</div>}
          {selected && (
            <>
              <div className="aiout__preview-head">
                <span className="aiout__preview-name">{ICON[selected.category]} {selected.name}</span>
                <div className="aiout__actions">
                  {preview.text && <button onClick={copy}>{copied ? '✓ Copied' : 'Copy'}</button>}
                  {preview.text && <button onClick={download}>Download</button>}
                  {selected.url && <a href={selected.url} target="_blank" rel="noreferrer noopener"><button>Open ↗</button></a>}
                </div>
              </div>
              <div className="aiout__preview-body">
                {preview.status === 'loading' && <div className="aiout__empty">Loading…</div>}
                {preview.status === 'error' && <div className="aiout__empty">Could not load this output.</div>}
                {preview.status === 'ready' && selected.category === 'media' && extOf(selected.name) === 'mp4' && (
                  <video src={`${selected.url}?token=${encodeURIComponent(sessionStorage.getItem('ai_jwt') || '')}`} controls className="aiout__media" />
                )}
                {preview.status === 'ready' && selected.category === 'media' && extOf(selected.name) !== 'mp4' && (
                  <img src={`${selected.url}?token=${encodeURIComponent(sessionStorage.getItem('ai_jwt') || '')}`} alt={selected.name} className="aiout__media" />
                )}
                {preview.status === 'ready' && selected.category !== 'media' && (
                  (extOf(selected.name) === 'md' || selected.kind === 'research')
                    ? <MarkdownView text={preview.text} />
                    : <pre className="aiout__pre">{preview.text}</pre>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

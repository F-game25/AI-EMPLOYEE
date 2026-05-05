import { useState, useEffect, useCallback } from 'react'
import { Panel, HexButton } from '../nexus-ui'
import { API_URL } from '../../config/api'
import './WorkspacePage.css'

const BASE = API_URL

const EXT_LANG = { py: 'python', js: 'javascript', ts: 'typescript', jsx: 'jsx', tsx: 'tsx', sh: 'bash', md: 'markdown', html: 'html', css: 'css', json: 'json', txt: 'text' }

function ext(name) { return (name.split('.').pop() || '').toLowerCase() }
function isHtml(name) { return ext(name) === 'html' }
function isText(name) { const e = ext(name); return ['py','js','ts','jsx','tsx','sh','md','css','json','txt','csv','yaml','yml'].includes(e) }
function fmtSize(b) { return b < 1024 ? `${b}B` : b < 1048576 ? `${(b/1024).toFixed(1)}KB` : `${(b/1048576).toFixed(1)}MB` }

const ICON_MAP = { html: '🌐', py: '🐍', js: '📜', ts: '📘', jsx: '⚛', tsx: '⚛', md: '📝', sh: '🖥', json: '{}', css: '🎨' }

function FileIcon({ name }) {
  const e = ext(name)
  return <span>{ICON_MAP[e] || '📄'}</span>
}

function CodePreview({ content }) {
  const [copied, setCopied] = useState(false)
  const copy = () => { navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500) }
  return (
    <div className="ws-code-preview">
      <button onClick={copy} className="ws-copy-btn">
        {copied ? '✓ Copied' : 'Copy'}
      </button>
      <pre className="ws-code-block"><code>{content}</code></pre>
    </div>
  )
}

function HtmlPreview({ url, name }) {
  return (
    <div className="ws-html-preview">
      <div className="ws-html-actions">
        <a href={url} target="_blank" rel="noreferrer" className="ws-html-link">Open in new tab ↗</a>
      </div>
      <iframe src={url} sandbox="allow-scripts allow-same-origin" title={name} className="ws-html-frame" />
    </div>
  )
}

export default function WorkspacePage() {
  const [files, setFiles]         = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)
  const [preview, setPreview]     = useState(null)
  const [previewLoading, setPL]   = useState(false)
  const [filter, setFilter]       = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${BASE}/api/workspace/files`)
      const d = await r.json()
      setFiles(d.files || [])
    } catch { setFiles([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const openFile = useCallback(async (file) => {
    setSelected(file)
    setPreview(null)
    if (isHtml(file.name)) {
      setPreview({ type: 'html', url: `${BASE}/workspace/${file.path}` })
    } else if (isText(file.name) && file.size < 200000) {
      setPL(true)
      try {
        const r = await fetch(`${BASE}/workspace/${encodeURIComponent(file.path)}`)
        const text = await r.text()
        setPreview({ type: 'code', content: text, lang: EXT_LANG[ext(file.name)] || 'text' })
      } catch { setPreview({ type: 'error', msg: 'Could not load file.' }) }
      finally { setPL(false) }
    } else {
      setPreview({ type: 'download', url: `${BASE}/workspace/${file.path}` })
    }
  }, [])

  const filtered = files.filter(f => !filter || f.name.toLowerCase().includes(filter.toLowerCase()) || f.path.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="ws-page">
      {/* File List Sidebar */}
      <div className="ws-sidebar">
        <div className="ws-sidebar-header">
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter files…"
            className="ws-filter-input"
          />
          <button onClick={load} title="Refresh" className="ws-refresh-btn">↻</button>
        </div>
        <div className="ws-file-list">
          {loading ? (
            <div className="ws-empty">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="ws-empty">No files found.</div>
          ) : filtered.map((f, i) => (
            <div
              key={i}
              onClick={() => openFile(f)}
              className={`ws-file-item ${selected?.path === f.path ? 'ws-file-item--selected' : ''}`}
            >
              <FileIcon name={f.name} />
              <div className="ws-file-info">
                <div className="ws-file-name">{f.name}</div>
                <div className="ws-file-size">{fmtSize(f.size)}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="ws-file-count">{filtered.length} file{filtered.length !== 1 ? 's' : ''}</div>
      </div>

      {/* Preview Panel */}
      <div className="ws-preview-area">
        {!selected ? (
          <div className="ws-empty-state">Select a file to preview</div>
        ) : (
          <Panel title={selected.path} tone="gold">
            <div className="ws-preview-meta">
              <span>{fmtSize(selected.size)}</span>
              <span>·</span>
              <span>{new Date(selected.mtime).toLocaleString()}</span>
              <a href={`${BASE}/workspace/${selected.path}`} download={selected.name} className="ws-download-link">⬇ Download</a>
            </div>
            {previewLoading && <div className="ws-loading">Loading preview…</div>}
            {preview?.type === 'html' && <HtmlPreview url={preview.url} name={selected.name} />}
            {preview?.type === 'code' && <CodePreview content={preview.content} />}
            {preview?.type === 'download' && (
              <div className="ws-download-msg">
                Binary file — <a href={preview.url} download={selected.name} className="ws-download-link">download</a> to view.
              </div>
            )}
            {preview?.type === 'error' && <div className="ws-error">{preview.msg}</div>}
          </Panel>
        )}
      </div>
    </div>
  )
}

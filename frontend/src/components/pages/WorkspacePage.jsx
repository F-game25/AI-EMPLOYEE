import { useState, useEffect, useCallback } from 'react'
import { Panel, HexButton, SectionLabel } from '../nexus-ui'
import FileUploadZone from '../workspace/FileUploadZone'
import { API_URL } from '../../config/api'
import './WorkspacePage.css'

const BASE = API_URL
const EXT_LANG = { py: 'python', js: 'javascript', ts: 'typescript', jsx: 'jsx', tsx: 'tsx', sh: 'bash', md: 'markdown', html: 'html', css: 'css', json: 'json', txt: 'text' }
const ICON_MAP = { html: '🌐', py: '🐍', js: '📜', ts: '📘', jsx: '⚛', tsx: '⚛', md: '📝', sh: '🖥', json: '{}', css: '🎨' }

const ext = name => (name.split('.').pop() || '').toLowerCase()
const isHtml = name => ext(name) === 'html'
const isText = name => ['py','js','ts','jsx','tsx','sh','md','css','json','txt','csv','yaml','yml'].includes(ext(name))
const fmtSize = b => b < 1024 ? `${b}B` : b < 1048576 ? `${(b/1024).toFixed(1)}KB` : `${(b/1048576).toFixed(1)}MB`
const fmtDate = ms => new Date(ms).toLocaleString()

function FileIcon({ name }) {
  return <span>{ICON_MAP[ext(name)] || '📄'}</span>
}

function CodePreview({ content }) {
  const [copied, setCopied] = useState(false)
  const copy = () => { navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500) }
  return (
    <div className="wsp-code-preview">
      <button onClick={copy} className="wsp-copy-btn">{copied ? '✓ Copied' : 'Copy'}</button>
      <pre className="wsp-code-block"><code>{content}</code></pre>
    </div>
  )
}

function HtmlPreview({ url, name }) {
  return (
    <div className="wsp-html-preview">
      <div className="wsp-html-actions">
        <a href={url} target="_blank" rel="noreferrer" className="wsp-html-link">Open in new tab ↗</a>
      </div>
      <iframe src={url} sandbox="allow-scripts allow-same-origin" title={name} className="wsp-html-frame" />
    </div>
  )
}

export default function WorkspacePage() {
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPL] = useState(false)
  const [filter, setFilter] = useState('')
  const [deleting, setDeleting] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${BASE}/api/workspace/files`)
      const d = await r.json()
      setFiles(d.files || [])
    } catch {
      setFiles([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const openFile = useCallback(async file => {
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
      } catch {
        setPreview({ type: 'error', msg: 'Could not load file.' })
      } finally {
        setPL(false)
      }
    } else {
      setPreview({ type: 'download', url: `${BASE}/workspace/${file.path}` })
    }
  }, [])

  const deleteFile = useCallback(async (fileId, e) => {
    e.stopPropagation()
    if (!window.confirm('Delete this file? This action cannot be undone.')) return
    setDeleting(fileId)
    try {
      const r = await fetch(`${BASE}/api/workspace/files/${fileId}`, { method: 'DELETE' })
      if (r.ok) {
        setFiles(prev => prev.filter(f => f.id !== fileId))
        if (selected?.id === fileId) setSelected(null)
      }
    } catch (e) {
      console.error('Delete failed:', e)
    } finally {
      setDeleting(null)
    }
  }, [selected])

  const filtered = files.filter(f => !filter || f.name.toLowerCase().includes(filter.toLowerCase()) || f.path.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="wsp-page">
      <div className="wsp-sidebar">
        <FileUploadZone onUploadComplete={load} apiUrl={BASE} />

        <div className="wsp-list-section">
          <SectionLabel tone="gold" rule>Files ({filtered.length})</SectionLabel>
          <div className="wsp-sidebar-header">
            <input value={filter} onChange={e => setFilter(e.target.value)}
              placeholder="Filter files…" className="wsp-filter-input" />
            <button onClick={load} title="Refresh" className="wsp-refresh-btn">↻</button>
          </div>
          <div className="wsp-file-list">
            {loading ? (
              <div className="wsp-empty">Loading…</div>
            ) : filtered.length === 0 ? (
              <div className="wsp-empty">No files found.</div>
            ) : (
              filtered.map(f => (
                <div key={f.id || f.path} onClick={() => openFile(f)}
                  className={`wsp-file-item ${selected?.path === f.path ? 'wsp-file-item--selected' : ''}`}>
                  <FileIcon name={f.name} />
                  <div className="wsp-file-info">
                    <div className="wsp-file-name">{f.name}</div>
                    <div className="wsp-file-size">{fmtSize(f.size)}</div>
                  </div>
                  <button className="wsp-file-delete-btn" onClick={e => deleteFile(f.id || f.path, e)}
                    disabled={deleting === (f.id || f.path)} title="Delete">×</button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="wsp-preview-area">
        {!selected ? (
          <div className="wsp-empty-state">Select a file to preview</div>
        ) : (
          <Panel title={selected.path} tone="gold">
            <div className="wsp-preview-meta">
              <span>{fmtSize(selected.size)}</span>
              <span>·</span>
              <span>{fmtDate(selected.mtime)}</span>
              <a href={`${BASE}/workspace/${selected.path}`} download={selected.name} className="wsp-download-link">⬇ Download</a>
            </div>
            {previewLoading && <div className="wsp-loading">Loading preview…</div>}
            {preview?.type === 'html' && <HtmlPreview url={preview.url} name={selected.name} />}
            {preview?.type === 'code' && <CodePreview content={preview.content} />}
            {preview?.type === 'download' && (
              <div className="wsp-download-msg">Binary file — <a href={preview.url} download={selected.name} className="wsp-download-link">download</a> to view.</div>
            )}
            {preview?.type === 'error' && <div className="wsp-error">{preview.msg}</div>}
          </Panel>
        )}
      </div>
    </div>
  )
}

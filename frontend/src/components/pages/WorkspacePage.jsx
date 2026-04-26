import { useState, useEffect, useCallback } from 'react'
import { Panel } from '../ui/primitives'
import { API_URL } from '../../config/api'

const BASE = API_URL

const EXT_LANG = { py: 'python', js: 'javascript', ts: 'typescript', jsx: 'jsx', tsx: 'tsx', sh: 'bash', md: 'markdown', html: 'html', css: 'css', json: 'json', txt: 'text' }

function ext(name) { return (name.split('.').pop() || '').toLowerCase() }
function isHtml(name) { return ext(name) === 'html' }
function isText(name) { const e = ext(name); return ['py','js','ts','jsx','tsx','sh','md','css','json','txt','csv','yaml','yml'].includes(e) }
function fmtSize(b) { return b < 1024 ? `${b}B` : b < 1048576 ? `${(b/1024).toFixed(1)}KB` : `${(b/1048576).toFixed(1)}MB` }

function FileIcon({ name }) {
  const e = ext(name)
  const map = { html: '🌐', py: '🐍', js: '📜', ts: '📘', jsx: '⚛', tsx: '⚛', md: '📝', sh: '🖥', json: '{}', css: '🎨' }
  return <span>{map[e] || '📄'}</span>
}

function CodePreview({ content, lang }) {
  const [copied, setCopied] = useState(false)
  const copy = () => { navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500) }
  return (
    <div style={{ position: 'relative', marginTop: 8 }}>
      <button onClick={copy} style={{ position: 'absolute', top: 6, right: 6, padding: '3px 8px', borderRadius: 5, border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.6)', fontSize: 10, cursor: 'pointer' }}>
        {copied ? '✓ Copied' : 'Copy'}
      </button>
      <pre style={{ margin: 0, padding: '10px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.08)', overflowX: 'auto', fontSize: 11, lineHeight: 1.5, color: 'var(--text-primary, #F0E9D2)', maxHeight: 320, fontFamily: 'monospace' }}>
        <code>{content}</code>
      </pre>
    </div>
  )
}

function HtmlPreview({ url, name }) {
  const blobRef = { current: null }
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
        <a href={url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: 'var(--teal, #20D6C7)', textDecoration: 'none', padding: '3px 10px', border: '1px solid rgba(32,214,199,0.3)', borderRadius: 5 }}>Open in new tab ↗</a>
      </div>
      <iframe src={url} sandbox="allow-scripts allow-same-origin" style={{ width: '100%', height: 280, borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)', background: '#fff' }} title={name} />
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
    <div style={{ display: 'flex', gap: 12, height: '100%', overflow: 'hidden' }}>
      {/* File list */}
      <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input
            value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter files…"
            style={{ flex: 1, padding: '6px 10px', borderRadius: 7, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary, #F0E9D2)', fontSize: 12, outline: 'none' }}
          />
          <button onClick={load} title="Refresh" style={{ padding: '6px 10px', borderRadius: 7, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: 13 }}>↻</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
          {loading ? (
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', padding: 8 }}>Loading…</div>
          ) : filtered.length === 0 ? (
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', fontStyle: 'italic', padding: 8 }}>No files found.</div>
          ) : filtered.map((f, i) => (
            <div
              key={i} onClick={() => openFile(f)}
              style={{ padding: '7px 10px', borderRadius: 7, border: `1px solid ${selected?.path === f.path ? 'rgba(32,214,199,0.3)' : 'rgba(255,255,255,0.06)'}`, background: selected?.path === f.path ? 'rgba(32,214,199,0.07)' : 'rgba(255,255,255,0.02)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <FileIcon name={f.name} />
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{ fontSize: 12, color: 'var(--text-primary, #F0E9D2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</div>
                <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', fontFamily: 'monospace' }}>{fmtSize(f.size)}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.25)', fontFamily: 'monospace', padding: '4px 0' }}>{filtered.length} file{filtered.length !== 1 ? 's' : ''}</div>
      </div>

      {/* Preview panel */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {!selected ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'rgba(255,255,255,0.2)', fontSize: 13 }}>Select a file to preview</div>
        ) : (
          <Panel title={selected.path}>
            <div style={{ display: 'flex', gap: 10, marginBottom: 10, fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>
              <span>{fmtSize(selected.size)}</span>
              <span>·</span>
              <span>{new Date(selected.mtime).toLocaleString()}</span>
              <a href={`${BASE}/workspace/${selected.path}`} download={selected.name} style={{ color: 'var(--teal, #20D6C7)', marginLeft: 'auto' }}>⬇ Download</a>
            </div>
            {previewLoading && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)' }}>Loading preview…</div>}
            {preview?.type === 'html' && <HtmlPreview url={preview.url} name={selected.name} />}
            {preview?.type === 'code' && <CodePreview content={preview.content} lang={preview.lang} />}
            {preview?.type === 'download' && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>Binary file — <a href={preview.url} download={selected.name} style={{ color: 'var(--teal, #20D6C7)' }}>download</a> to view.</div>}
            {preview?.type === 'error' && <div style={{ fontSize: 12, color: '#EF4444' }}>{preview.msg}</div>}
          </Panel>
        )}
      </div>
    </div>
  )
}

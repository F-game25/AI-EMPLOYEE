import { useState, useEffect } from 'react'
import { EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JGET, JPOST_JSON } from './helpers'

export function FileTree({ project, selectedFile, onSelect }) {
  const [tree, setTree] = useState(null)
  const projectId = project?.id

  useEffect(() => {
    if (!projectId) return
    JGET(`/api/forge/files/tree?project_id=${projectId}`).then(r => r.json()).then(d => setTree(d.tree || [])).catch(() => setTree([]))
  }, [projectId])

  if (!project) return <EmptyState icon="📁" title="No project" sub="Select or create a project" />
  if (!tree) return <div className="af-file-loading">Loading…</div>

  const renderNode = (node, depth = 0) => (
    <div key={node.path} className={`af-tree__indent af-tree__indent--${Math.min(depth, 6)}`}>
      {node.type === 'dir'
        ? <div className="af-tree__dir">📁 {node.name}</div>
        : <button className={`af-tree__file ${selectedFile?.path === node.path ? 'af-tree__file--active' : ''}`} onClick={() => onSelect(node)}>
            <span className="af-tree__file-icon">{node.name.endsWith('.py') ? '🐍' : node.name.endsWith('.js') || node.name.endsWith('.jsx') ? '⚡' : '📄'}</span>
            {node.name}
          </button>
      }
      {node.children?.map(c => renderNode(c, depth + 1))}
    </div>
  )

  return (
    <div className="af-file-tree">
      {tree.length === 0
        ? <EmptyState icon="📄" title="Empty project" sub="Start chatting to create files" />
        : tree.map(n => renderNode(n))}
    </div>
  )
}

export function FileEditor({ project, selectedFile, onSave }) {
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const projectId = project?.id

  useEffect(() => {
    if (!projectId || !selectedFile) return
    setLoading(true)
    JGET(`/api/forge/files/read?project_id=${projectId}&file_path=${encodeURIComponent(selectedFile)}`)
      .then(r => r.json())
      .then(d => { setContent(d.content || ''); setOriginal(d.content || '') })
      .finally(() => setLoading(false))
  }, [projectId, selectedFile])

  const save = async () => {
    setSaving(true)
    try {
      await JPOST_JSON('/api/forge/files/write', { project_id: project.id, file_path: selectedFile, content })
      setOriginal(content)
      if (onSave) onSave(selectedFile)
      toastSuccess('File saved')
    } catch (e) { toastError(e.message) }
    finally { setSaving(false) }
  }

  if (!selectedFile) return <div className="forge-editor-empty">Select a file to edit</div>
  if (loading) return <div className="forge-editor-empty">Loading…</div>
  return (
    <div className="forge-editor">
      <div className="forge-editor-bar">
        <span className="forge-editor-filename">{selectedFile}</span>
        {content !== original && (
          <button className="forge-editor-save" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : '↑ Save'}
          </button>
        )}
      </div>
      <textarea
        className="forge-editor-area"
        value={content}
        onChange={e => setContent(e.target.value)}
        spellCheck={false}
      />
    </div>
  )
}

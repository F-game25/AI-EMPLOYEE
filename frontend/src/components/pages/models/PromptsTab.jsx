import { useState, useCallback, useRef, useEffect } from 'react'
import api from '../../../api/client'

function PromptsTab() {
  const [agents, setAgents]               = useState([])
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [promptText, setPromptText]       = useState('')
  const [originalText, setOriginalText]   = useState('')
  const [versions, setVersions]           = useState([])
  const [saving, setSaving]               = useState(false)
  const [saved, setSaved]                 = useState(false)
  const textareaRef                       = useRef(null)

  useEffect(() => {
    api.get('/api/agents/list')
      .then(d => setAgents((d?.agents || d || []).map(a => ({ id: a.id || a.name, name: a.name || a.id, prompt: a.prompt || a.description || '' }))))
      .catch(() => setAgents([]))
  }, [])

  const selectAgent = useCallback(async (agent) => {
    setSelectedAgent(agent)
    setSaved(false)
    try {
      const d = await api.get(`/api/agents/${agent.id}/prompt`)
      const text = d?.prompt ?? agent.prompt
      setPromptText(text)
      setOriginalText(text)
      setVersions(Array.isArray(d?.versions) ? d.versions : [])
    } catch {
      setPromptText(agent.prompt)
      setOriginalText(agent.prompt)
      setVersions([])
    }
  }, [])

  const savePrompt = async () => {
    if (!selectedAgent) return
    setSaving(true)
    try {
      await api.put(`/api/agents/${selectedAgent.id}/prompt`, { prompt: promptText }).catch(() => {})
      setOriginalText(promptText)
      setVersions(prev => [
        { ts: new Date().toISOString().slice(0, 16).replace('T', ' '), preview: promptText.slice(0, 80) + '…' },
        ...prev.slice(0, 4),
      ])
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } finally {
      setSaving(false)
    }
  }

  const discard = () => {
    setPromptText(originalText)
    setSaved(false)
  }

  const restore = (version) => {
    setPromptText(version.preview.replace('…', ''))
    textareaRef.current?.focus()
  }

  return (
    <div>
      <div className="mp-section-label">AGENT SYSTEM PROMPTS</div>
      <div className="mp-prompts-layout">
        {/* Left: agent list */}
        <div className="mp-agent-list">
          {agents.length === 0 && <div className="mp-prompt-no-selection">No agents loaded.</div>}
          {agents.map(agent => (
            <div
              key={agent.id}
              className={`mp-agent-item ${selectedAgent?.id === agent.id ? 'mp-agent-item--active' : ''}`}
              onClick={() => selectAgent(agent)}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && selectAgent(agent)}
            >
              <div className="mp-agent-item-name">{agent.name}</div>
              {agent.prompt && <div className="mp-agent-item-preview">{agent.prompt.slice(0, 80)}</div>}
            </div>
          ))}
        </div>

        {/* Right: editor + history */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {!selectedAgent ? (
            <div className="mp-prompt-no-selection">
              Select an agent to edit its system prompt
            </div>
          ) : (
            <>
              <div className="mp-prompt-editor">
                <div className="mp-prompt-editor-header">
                  <span className="mp-prompt-agent-title">{selectedAgent.name}</span>
                  <div className="mp-prompt-actions">
                    <span className="mp-prompt-char-count">{promptText.length} chars</span>
                    <button className="mp-discard-btn" onClick={discard}>DISCARD</button>
                    <button
                      className={`mp-test-btn ${saved ? 'mp-row-save-btn--saved' : ''}`}
                      style={saved ? { color: '#22c55e', borderColor: 'rgba(34,197,94,0.3)' } : {}}
                      onClick={savePrompt}
                      disabled={saving || saved}
                    >
                      {saved ? '✓ SAVED' : saving ? 'SAVING…' : 'SAVE PROMPT'}
                    </button>
                  </div>
                </div>
                <textarea
                  ref={textareaRef}
                  className="mp-prompt-textarea"
                  value={promptText}
                  onChange={e => { setPromptText(e.target.value); setSaved(false) }}
                  spellCheck={false}
                  aria-label={`System prompt for ${selectedAgent.name}`}
                />
              </div>

              {versions.length > 0 && (
                <div className="mp-version-history">
                  <div className="mp-version-history-title">VERSION HISTORY (LAST 5)</div>
                  {versions.map((v, i) => (
                    <div key={i} className="mp-version-row">
                      <span className="mp-version-ts">{v.ts}</span>
                      <span className="mp-version-preview">{v.preview}</span>
                      <button className="mp-restore-btn" onClick={() => restore(v)}>RESTORE</button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default PromptsTab

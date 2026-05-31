'use strict'
// Ollama admin — list / pull / delete local models via Ollama HTTP API.
const OLLAMA_HOST = process.env.OLLAMA_HOST || 'http://localhost:11434'

async function isOllamaRunning() {
  try {
    const r = await fetch(`${OLLAMA_HOST}/api/tags`, { method: 'HEAD', signal: AbortSignal.timeout(2000) })
    return r.ok
  } catch { return false }
}

async function listModels() {
  try {
    const r = await fetch(`${OLLAMA_HOST}/api/tags`, { signal: AbortSignal.timeout(4000) })
    if (!r.ok) return []
    const d = await r.json()
    return (d.models || []).map(m => ({ name: m.name, size: m.size, modified_at: m.modified_at, digest: m.digest }))
  } catch { return [] }
}

async function pullModel(name) {
  try {
    const r = await fetch(`${OLLAMA_HOST}/api/pull`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name }),
      signal: AbortSignal.timeout(300000),
    })
    if (!r.ok) return { ok: false, status: r.status, message: `pull failed (${r.status})` }
    return { ok: true, status: 'success', message: 'pulled' }
  } catch (e) { return { ok: false, status: 0, message: e.message } }
}

async function deleteModel(name) {
  try {
    const r = await fetch(`${OLLAMA_HOST}/api/delete`, {
      method: 'DELETE',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name }),
      signal: AbortSignal.timeout(10000),
    })
    return { ok: r.ok }
  } catch (e) { return { ok: false, error: e.message } }
}

async function* pullModelStream(name) {
  const r = await fetch(`${OLLAMA_HOST}/api/pull`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name, stream: true }),
  })
  if (!r.ok) throw new Error(`ollama pull failed (${r.status})`)
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      if (line.trim()) {
        try { yield JSON.parse(line) } catch { /* skip malformed */ }
      }
    }
  }
}

// Legacy aliases kept for backward compatibility
const listLocalModels = listModels
const showModel = async (name) => {
  try {
    const r = await fetch(`${OLLAMA_HOST}/api/show`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!r.ok) throw new Error(`ollama show failed (${r.status})`)
    return r.json()
  } catch (e) { return { error: e.message } }
}

module.exports = { listModels, listLocalModels, showModel, deleteModel, pullModel, pullModelStream, isOllamaRunning }

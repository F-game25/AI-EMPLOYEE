'use strict'
/**
 * Ollama admin — list / show / pull / delete local models.
 * Talks directly to the Ollama HTTP API (default http://localhost:11434).
 */
const OLLAMA_HOST = process.env.OLLAMA_HOST || 'http://localhost:11434'

async function listLocalModels() {
  const r = await fetch(`${OLLAMA_HOST}/api/tags`)
  if (!r.ok) throw new Error(`ollama list failed (${r.status})`)
  const d = await r.json()
  return d.models || []
}

async function showModel(name) {
  const r = await fetch(`${OLLAMA_HOST}/api/show`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!r.ok) throw new Error(`ollama show failed (${r.status})`)
  return r.json()
}

async function deleteModel(name) {
  const r = await fetch(`${OLLAMA_HOST}/api/delete`, {
    method: 'DELETE',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return { ok: r.ok, status: r.status }
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

module.exports = { listLocalModels, showModel, deleteModel, pullModelStream }

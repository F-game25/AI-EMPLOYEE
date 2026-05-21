/* Shared model helpers extracted from ModelsPage. */

export const FALLBACK_MODEL_OPTIONS = [
  { value: 'claude-sonnet-4-6', label: 'claude-sonnet-4-6', provider: 'anthropic' },
  { value: 'claude-opus-4-7',   label: 'claude-opus-4-7',   provider: 'anthropic' },
  { value: 'claude-haiku-4-5',  label: 'claude-haiku-4-5',  provider: 'anthropic' },
  { value: 'gpt-4o',            label: 'gpt-4o',            provider: 'openai'    },
  { value: 'llama3.2',          label: 'llama3.2',          provider: 'ollama'    },
]

export function buildModelOptions(registryData) {
  if (!registryData?.providers) return FALLBACK_MODEL_OPTIONS
  return Object.entries(registryData.providers).flatMap(([provider, pd]) =>
    (pd.models || []).map(m => ({
      value: typeof m === 'string' ? m : m.id,
      label: typeof m === 'string' ? m : (m.label || m.id),
      provider,
    }))
  )
}

export function modelProvider(model, registryData) {
  const opts = buildModelOptions(registryData)
  return opts.find(m => m.value === model)?.provider || 'anthropic'
}


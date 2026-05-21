/* Shared model helpers + stub data extracted from ModelsPage. */

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

export const STUB_ROUTING = [
  { id: 1, agent: 'content-generator',   preferred: 'claude-sonnet-4-6', fallback: 'claude-haiku-4-5', budget: 5.00,  active: true  },
  { id: 2, agent: 'email-writer',        preferred: 'claude-haiku-4-5',  fallback: 'llama3.2',         budget: 2.00,  active: true  },
  { id: 3, agent: 'data-analyst',        preferred: 'claude-opus-4-7',   fallback: 'gpt-4o',           budget: 15.00, active: true  },
  { id: 4, agent: 'lead-hunter-elite',   preferred: 'claude-sonnet-4-6', fallback: 'claude-haiku-4-5', budget: 8.00,  active: false },
  { id: 5, agent: 'research-agent',      preferred: 'gpt-4o',            fallback: 'llama3.2',         budget: 3.00,  active: true  },
]


export const STUB_AGENTS = [
  { id: 'content-generator',  name: 'Content Generator',  prompt: 'You are a content generation specialist. Your job is to create high-quality, engaging content for various platforms and audiences. Focus on clarity, tone, and audience alignment.' },
  { id: 'email-writer',       name: 'Email Writer',       prompt: 'You are an expert email writer. Craft clear, compelling emails with strong subject lines, concise bodies, and effective calls-to-action. Adapt tone to context: formal, friendly, or sales-oriented.' },
  { id: 'data-analyst',       name: 'Data Analyst',       prompt: 'You are a data analysis agent. Interpret structured datasets, identify trends, surface anomalies, and deliver actionable insights in structured formats (tables, bullet summaries, JSON).' },
  { id: 'lead-hunter-elite',  name: 'Lead Hunter Elite',  prompt: 'You are a lead generation specialist. Identify high-value prospects using ICP criteria. Prioritize recency, fit score, and engagement signals. Output leads as structured JSON.' },
  { id: 'research-agent',     name: 'Research Agent',     prompt: 'You are a deep research agent. Synthesize information from multiple sources, evaluate source credibility, identify knowledge gaps, and produce structured research briefs with citations.' },
  { id: 'team-management',    name: 'Team Management',    prompt: 'You are a team operations agent. Manage task assignments, track deliverables, identify blockers, and produce status reports. Communicate with clarity and prioritize by impact.' },
]

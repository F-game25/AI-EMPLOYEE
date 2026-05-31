// Message template library for AI avatar speech

export const MESSAGES = {
  'nb:reasoning_step:active':    d => `Running ${d?.node || d?.step || 'analysis'} node`,
  'nb:reasoning_step:slow':      d => `${d?.node || 'Step'} took ${d?.latency_ms}ms — heavy computation`,
  'nb:reasoning_step:done':      d => `${d?.node || 'Step'} complete`,
  'nb:model_call:ok':            d => `${d?.arch || 'Model'} responded cleanly`,
  'nb:model_call:error':         d => `${d?.arch || 'Model'} returned an error. Reviewing`,
  'agent:running':               d => `Agent ${d?.name || 'unknown'} is executing`,
  'agent:error':                 d => `Agent ${d?.name || 'unknown'} encountered an error`,
  'agent:batch_complete':        _  => 'Task batch completed. Clean run',
  'system:degraded':             _  => 'System under stress — error rate elevated',
  'system:ready':                _  => 'All systems online. Ready to operate',
  'memory:user_pattern':         d => `I noticed: ${d?.pattern || 'a pattern in your workflow'}`,
  'forge:approved':              d => `Forge approved: ${d?.goal || 'patch applied'}`,
  'forge:high_risk':             d => `High risk change flagged: ${d?.goal || 'review recommended'}`,
}

export function getGreeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning. Systems are online.'
  if (h < 18) return 'Good afternoon. Ready to assist.'
  return 'Good evening. All systems operational.'
}

export function buildMessage(eventKey, data) {
  const template = MESSAGES[eventKey]
  return template ? template(data) : null
}

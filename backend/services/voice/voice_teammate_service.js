'use strict';

const INTERNAL_DEFAULT_PROFILE = Object.freeze({
  mode: 'internal',
  gender: 'female',
  tone: 'warm',
  warmth: 0.55,
  emotion: 'warm_confident',
  emotionIntensity: 0.35,
  speakingRate: 1.0,
  energy: 0.55,
  addressUserAs: 'Chief Lars',
  approvalMode: 'approval_gates',
});

const EXTERNAL_DEFAULT_PROFILE = Object.freeze({
  mode: 'external',
  gender: 'female',
  tone: 'warm',
  warmth: 0.7,
  emotion: 'warm_confident',
  emotionIntensity: 0.32,
  speakingRate: 1.0,
  energy: 0.5,
  addressUserAs: 'customer',
  approvalMode: 'approval_gates',
});

const SUPPORTED_TONES = new Set(['calm', 'warm', 'focused', 'authoritative', 'concerned', 'urgent', 'professional', 'firm']);
const SUPPORTED_EMOTIONS = new Set(['neutral', 'calm', 'warm_confident', 'focused', 'curious', 'concerned', 'firm', 'urgent', 'subtle_excited']);

function clampNumber(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function normalizeMode(value) {
  return String(value || '').toLowerCase() === 'external' ? 'external' : 'internal';
}

function normalizeGender(value, fallback = 'female') {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'male' || normalized === 'masculine') return 'male';
  if (normalized === 'female' || normalized === 'feminine') return 'female';
  return fallback;
}

function normalizeTone(value, fallback = 'warm') {
  const normalized = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (SUPPORTED_TONES.has(normalized)) return normalized;
  if (normalized === 'warm_confident') return 'warm';
  if (normalized === 'sharp') return 'authoritative';
  if (normalized === 'futuristic') return 'focused';
  return fallback;
}

function normalizeEmotion(value, fallback = 'warm_confident') {
  const normalized = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  return SUPPORTED_EMOTIONS.has(normalized) ? normalized : fallback;
}

function identityAddress(identity = {}) {
  const name = String(identity.userName || identity.user_name || 'Lars').trim() || 'Lars';
  const rank = String(identity.rank || 'Chief').trim() || 'Chief';
  return [rank, name].filter(Boolean).join(' ');
}

function legacyProfileFromConfig(cfg = {}, mode = 'internal') {
  if (mode === 'external') {
    const customer = cfg.customer || {};
    return {
      mode: 'external',
      tone: customer.tone || customer.profile || 'warm',
      warmth: customer.warmth,
      speakingRate: customer.speed,
      addressUserAs: 'customer',
      gender: customer.gender,
      emotion: customer.emotion,
      emotionIntensity: customer.emotionIntensity,
      energy: customer.energy,
    };
  }
  const voiceCore = cfg.voiceCore || {};
  return {
    mode: 'internal',
    gender: voiceCore.gender || voiceCore.voice,
    tone: cfg.tone || voiceCore.tone,
    warmth: voiceCore.warmth,
    emotion: voiceCore.emotion,
    emotionIntensity: voiceCore.emotionIntensity,
    speakingRate: voiceCore.speakingRate,
    energy: voiceCore.energy,
    addressUserAs: identityAddress(cfg.identity),
  };
}

function normalizeVoiceProfile(input = {}, cfg = {}, forcedMode = null) {
  const mode = normalizeMode(forcedMode || input.mode || input.voice_mode || input.channel);
  const defaults = mode === 'external' ? EXTERNAL_DEFAULT_PROFILE : INTERNAL_DEFAULT_PROFILE;
  const configured = cfg.voiceProfiles?.[mode] || cfg.voice_profiles?.[mode] || {};
  const legacy = legacyProfileFromConfig(cfg, mode);
  const merged = { ...defaults, ...legacy, ...configured, ...input, mode };

  return {
    mode,
    gender: normalizeGender(merged.gender || merged.voice, defaults.gender),
    tone: normalizeTone(merged.tone, defaults.tone),
    warmth: clampNumber(merged.warmth, 0, 1, defaults.warmth),
    emotion: normalizeEmotion(merged.emotion, defaults.emotion),
    emotionIntensity: clampNumber(merged.emotionIntensity ?? merged.emotion_intensity, 0, 0.7, defaults.emotionIntensity),
    speakingRate: clampNumber(merged.speakingRate ?? merged.speaking_rate ?? merged.speed, 0.85, 1.15, defaults.speakingRate),
    energy: clampNumber(merged.energy, 0.2, 0.8, defaults.energy),
    addressUserAs: String(merged.addressUserAs || merged.address_user_as || defaults.addressUserAs).trim() || defaults.addressUserAs,
    approvalMode: merged.approvalMode || merged.approval_mode || defaults.approvalMode,
  };
}

function normalizeVoiceProfiles(input = {}, cfg = {}) {
  return {
    internal: normalizeVoiceProfile(input.internal || {}, cfg, 'internal'),
    external: normalizeVoiceProfile(input.external || {}, cfg, 'external'),
  };
}

function profileToVoiceCore(profile = {}, existing = {}) {
  const normalized = normalizeVoiceProfile(profile, {}, profile.mode);
  return {
    ...existing,
    voice: normalized.gender,
    gender: normalized.gender,
    tone: normalized.tone,
    warmth: normalized.warmth,
    emotion: normalized.emotion,
    emotionIntensity: normalized.emotionIntensity,
    speakingRate: normalized.speakingRate,
    energy: normalized.energy,
  };
}

function profileToSynthesisOptions(profile = {}, extra = {}) {
  const normalized = normalizeVoiceProfile({ ...profile, ...extra }, {}, profile.mode);
  return {
    voice: normalized.gender,
    gender: normalized.gender,
    tone: normalized.tone,
    warmth: normalized.warmth,
    emotion: normalized.emotion,
    emotion_intensity: normalized.emotionIntensity,
    speaking_rate: normalized.speakingRate,
    energy: normalized.energy,
    persona: {
      ...(extra.persona || {}),
      mode: normalized.mode,
      gender: normalized.gender,
      tone: normalized.tone,
      warmth: normalized.warmth,
      emotion: normalized.emotion,
      emotion_intensity: normalized.emotionIntensity,
      speaking_rate: normalized.speakingRate,
      energy: normalized.energy,
      addressUserAs: normalized.addressUserAs,
      approvalMode: normalized.approvalMode,
    },
  };
}

function buildVoiceInstructions(profile = {}) {
  const normalized = normalizeVoiceProfile(profile, {}, profile.mode);
  if (normalized.mode === 'external') {
    return [
      'You are speaking in external customer-call mode.',
      'Use customer-safe language. Do not reveal internal memory, internal tools, secrets, task queues, money-mode data, or system state.',
      'Be warm, concise, and professional.',
      'Do not perform outbound, account, payment, publishing, or money actions without explicit approval.',
    ].join('\n');
  }
  return [
    `Address the user as ${normalized.addressUserAs} naturally. Do not repeat the name in every sentence.`,
    'Speak like a calm, high-context teammate: concise, intelligent, direct, and useful.',
    'Reply in the same language as the user unless the user asks for another language.',
    'When the user wants to make a plan, collaborate on the plan and keep next actions concrete.',
    'When the user gives a voice command, treat it as actionable intent and route it through existing system capabilities.',
    'Never bypass approval gates. Ask for approval before destructive, external-account, publishing, payment, wallet, money-spending, or security-sensitive actions.',
  ].join('\n');
}

function buildVoiceContext({ existingContext = {}, transcript = '', sessionId = null, profile = {} } = {}) {
  const normalized = normalizeVoiceProfile(profile, {}, profile.mode);
  return {
    ...existingContext,
    modality: 'voice',
    voice_session_id: sessionId,
    raw_transcript: transcript,
    voice_mode: normalized.mode,
    voice_profile: normalized,
    voice_address: normalized.addressUserAs,
    voice_command_mode: normalized.mode === 'internal',
    voice_external_mode: normalized.mode === 'external',
    internal_data_allowed: normalized.mode !== 'external',
    requires_approval_for_sensitive_actions: normalized.approvalMode === 'approval_gates',
    voice_instructions: buildVoiceInstructions(normalized),
    use_turn_runner: existingContext.use_turn_runner !== false,
  };
}

function buildLocalFallback(message, profile = {}) {
  const normalized = normalizeVoiceProfile(profile, {}, profile.mode);
  const text = String(message || '').trim();
  if (normalized.mode === 'external') {
    return 'I can help with that, but the main AI backend is unavailable right now. Please try again in a moment.';
  }
  return `${normalized.addressUserAs}, I heard you: "${text}". Local voice and transcription are working, but the main chat route is unavailable right now.`;
}

function cleanMarkdownForSpeech(value) {
  return String(value || '')
    .replace(/```[\s\S]*?```/g, 'I have code ready on screen.')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/Request processed via Ollama\.\s*/gi, '')
    .replace(/[📋⚡✅❌🎓⚠️]/g, '')
    .replace(/^#+\s*(TASK UNDERSTANDING|EXECUTION & RESULTS|PROOF|RESULTS?|SUMMARY|VALIDATION)\s*$/gim, '')
    .replace(/^#+\s*/gm, '')
    .replace(/\b(TASK UNDERSTANDING|EXECUTION & RESULTS|PROOF|SUMMARY|VALIDATION)\b\.?\s*/gi, '')
    .replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, '$1')
    .replace(/^\s*[-+*]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/\s*\n\s*/g, '. ')
    .replace(/\s{2,}/g, ' ')
    .replace(/\.{2,}/g, '.')
    .replace(/^[\s.,:;!?-]+/, '')
    .trim();
}

function executionStateFromPayload(payload = {}) {
  if (payload.source === 'approval_gate' || payload.status === 'waiting_approval') return 'waiting_approval';
  if (payload.taskId || payload.task_id || payload.workflow_run) return payload.status === 'failed' ? 'failed' : 'queued_or_executed';
  if (payload.chat_unavailable) return 'fallback';
  return 'conversation';
}

function approvalRequiredFromPayload(payload = {}) {
  return payload.source === 'approval_gate' || payload.status === 'waiting_approval' || Boolean(payload.approval_required) || (
    Array.isArray(payload.approvals) && payload.approvals.length > 0
  );
}

function formatSpokenReply(reply, transcript, payload = {}, profile = {}) {
  const normalized = normalizeVoiceProfile(profile, {}, profile.mode);
  const original = String(reply || '').trim();
  if (!original) return buildLocalFallback(transcript, normalized);

  let result = original;
  const resultMatch = original.match(/(?:^|\n)Result:\s*\n([\s\S]*?)(?:\n\nProof:|\n\nBlocked by:|$)/i);
  if (resultMatch?.[1]) result = resultMatch[1].trim();

  if (approvalRequiredFromPayload(payload)) {
    result = normalized.mode === 'external'
      ? 'That needs approval before I can continue.'
      : 'I paused that before execution because it needs approval. Approve it first, then I can continue.';
  } else if (payload?.source === 'node-fallback' && /unable to reach the ai backend/i.test(result)) {
    result = 'I queued the request, but the main AI backend is unavailable right now. Start Ollama or configure an API key, then I can continue with full planning.';
  }

  result = cleanMarkdownForSpeech(
    result
      .replace(/\s*Proof:\s*[\s\S]*$/i, '')
      .replace(/\s*Blocked by:\s*[\s\S]*$/i, '')
      .trim(),
  );
  if (!result) result = cleanMarkdownForSpeech(original).slice(0, 500);
  if (normalized.mode === 'external') return result;
  if (result.toLowerCase().startsWith(normalized.addressUserAs.toLowerCase())) return result;
  return `${normalized.addressUserAs}, ${result}`;
}

function buildTurnResult({ transcript = '', payload = {}, reply = '', profile = {}, latencyMs = null, fallbackReason = null } = {}) {
  const voiceProfile = normalizeVoiceProfile(profile, {}, profile.mode);
  const spokenReply = formatSpokenReply(reply, transcript, payload, voiceProfile);
  const executionState = executionStateFromPayload(payload);
  const approvalRequired = approvalRequiredFromPayload(payload);
  return {
    spoken_reply: spokenReply,
    reply: spokenReply,
    content: spokenReply,
    structured_result: {
      ...(payload && typeof payload === 'object' ? payload : {}),
      structured_reply: reply,
    },
    execution_state: executionState,
    approval_required: approvalRequired,
    voice_profile_used: voiceProfile,
    fallback_reason: fallbackReason || (payload.chat_unavailable ? 'chat_unavailable' : null),
    latency_ms: latencyMs,
  };
}

module.exports = {
  INTERNAL_DEFAULT_PROFILE,
  EXTERNAL_DEFAULT_PROFILE,
  normalizeVoiceProfile,
  normalizeVoiceProfiles,
  profileToVoiceCore,
  profileToSynthesisOptions,
  buildVoiceContext,
  buildLocalFallback,
  formatSpokenReply,
  buildTurnResult,
};

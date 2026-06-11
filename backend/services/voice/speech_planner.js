'use strict';

const SUPPORTED_EMOTIONS = [
  'neutral',
  'calm',
  'warm_confident',
  'focused',
  'curious',
  'concerned',
  'firm',
  'urgent',
  'subtle_excited',
];

const EMOTION_PRESETS = {
  neutral: { intensity: 0.2, speaking_rate: 1.0, energy: 0.45, pause_style: 'natural' },
  calm: { intensity: 0.25, speaking_rate: 0.94, energy: 0.38, pause_style: 'measured' },
  warm_confident: { intensity: 0.35, speaking_rate: 0.98, energy: 0.55, pause_style: 'natural' },
  focused: { intensity: 0.3, speaking_rate: 1.0, energy: 0.5, pause_style: 'precise' },
  curious: { intensity: 0.32, speaking_rate: 1.02, energy: 0.52, pause_style: 'natural' },
  concerned: { intensity: 0.35, speaking_rate: 0.93, energy: 0.42, pause_style: 'measured' },
  firm: { intensity: 0.38, speaking_rate: 0.96, energy: 0.58, pause_style: 'precise' },
  urgent: { intensity: 0.5, speaking_rate: 1.07, energy: 0.68, pause_style: 'short' },
  subtle_excited: { intensity: 0.42, speaking_rate: 1.04, energy: 0.64, pause_style: 'natural' },
};

const ABBREV_RE = /\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|i\.e|e\.g)\.\s*$/i;

function clamp(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function normalizeEmotion(value, fallback = 'warm_confident') {
  const normalized = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  return SUPPORTED_EMOTIONS.includes(normalized) ? normalized : fallback;
}

function inferEmotion(text, explicit, tone) {
  if (explicit) return normalizeEmotion(explicit);
  const value = String(text || '').toLowerCase();
  const toneValue = String(tone || '').toLowerCase();
  if (/(error|failed|blocked|warning|risk|danger|issue|problem)/.test(value)) return 'concerned';
  if (/(urgent|immediately|critical|deadline|asap)/.test(value)) return 'urgent';
  if (/(no\.|cannot|do not|stop|must)/.test(value)) return 'firm';
  if (value.includes('?')) return 'curious';
  if (/(great|excellent|good news)/.test(value)) return 'subtle_excited';
  if (toneValue.includes('calm')) return 'calm';
  if (toneValue.includes('authoritative')) return 'firm';
  if (toneValue.includes('warm')) return 'warm_confident';
  return 'warm_confident';
}

function cleanMarkdown(raw) {
  let text = String(raw || '').trim();
  if (!text) return '';
  text = text.replace(/```[\s\S]*?```/g, ' I prepared a code block for you. ');
  text = text.replace(/`([^`]{1,80})`/g, '$1');
  text = text.replace(/\[([^\]]+)]\(([^)]+)\)/g, '$1');
  text = text.replace(/(^|\n)\s{0,3}#{1,6}\s+/g, '$1');
  text = text.replace(/(^|\n)\s*[-*+]\s+/g, '$1');
  text = text.replace(/(^|\n)\s*\d+\.\s+/g, '$1');
  text = text.replace(/[*_~]{1,3}/g, '');
  text = text.replace(/\s*[-–—]\s*/g, ', ');
  text = text.replace(/\bHTTP\s+(\d{3})\b/gi, 'HTTP $1');
  text = text.replace(/\s+/g, ' ').trim();
  return text;
}

function splitSentences(raw) {
  const text = String(raw || '').trim();
  if (!text) return [];
  const safeText = text.length > 8000 ? text.slice(0, 8000) : text;
  const chunks = [];
  let current = '';
  for (let i = 0; i < safeText.length; i += 1) {
    current += safeText[i];
    const ch = safeText[i];
    const next = i + 1 < safeText.length ? safeText[i + 1] : '';
    if ((ch === '.' || ch === '?' || ch === '!') && (next === ' ' || next === '\n' || next === '')) {
      if (ch === '.' && ABBREV_RE.test(current)) continue;
      chunks.push(current.trim());
      current = '';
      if (next === ' ') i += 1;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  const merged = [];
  for (let i = 0; i < chunks.length; i += 1) {
    if (chunks[i].length < 10 && i + 1 < chunks.length) {
      merged.push(`${chunks[i]} ${chunks[i + 1]}`);
      i += 1;
    } else {
      merged.push(chunks[i]);
    }
  }
  return merged;
}

function applyNaturalPauses(text, pauseStyle) {
  if (!text) return '';
  if (pauseStyle === 'short') return text.replace(/,\s+/g, '. ');
  if (pauseStyle === 'measured') return text.replace(/;\s*/g, '. ').replace(/:\s*/g, '. ');
  return text.replace(/;\s*/g, ', ').replace(/:\s*/g, ', ');
}

function planSpeech(text, options = {}) {
  const persona = options.persona || {};
  const emotion = inferEmotion(text, options.emotion ?? persona.emotion, options.tone ?? persona.tone);
  const preset = EMOTION_PRESETS[emotion] || EMOTION_PRESETS.warm_confident;
  const emotionIntensity = clamp(
    options.emotion_intensity ?? options.emotionIntensity ?? persona.emotion_intensity ?? persona.emotionIntensity,
    0,
    0.7,
    preset.intensity,
  );
  const speakingRate = clamp(
    options.speaking_rate ?? options.speakingRate ?? persona.speaking_rate ?? persona.speed,
    0.85,
    1.15,
    preset.speaking_rate,
  );
  const warmth = clamp(options.warmth ?? persona.warmth, 0, 1, 0.5);
  const energy = clamp(options.energy ?? persona.energy, 0.2, 0.8, preset.energy + ((warmth - 0.5) * 0.08));
  const pauseStyle = String(options.pause_style || options.pauseStyle || persona.pause_style || (warmth > 0.65 ? 'natural' : preset.pause_style) || 'natural');
  const cleaned = applyNaturalPauses(cleanMarkdown(text), pauseStyle);
  const chunks = splitSentences(cleaned);
  return {
    text: cleaned,
    chunks,
    emotion,
    emotion_intensity: emotionIntensity,
    speaking_rate: speakingRate,
    warmth,
    energy,
    pause_style: pauseStyle,
    supported_emotions: SUPPORTED_EMOTIONS.slice(),
  };
}

module.exports = {
  SUPPORTED_EMOTIONS,
  EMOTION_PRESETS,
  cleanMarkdown,
  normalizeEmotion,
  planSpeech,
  splitSentences,
};

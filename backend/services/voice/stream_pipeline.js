'use strict';

/**
 * stream_pipeline.js — Low-latency streaming voice pipeline
 *
 * Architecture principle:
 *   Text → split sentences → speak first chunk immediately (perceived ~100ms)
 *               → chain remaining chunks with micro-pauses (sounds natural)
 *               → interrupt at sentence boundary when user speaks
 *               → pre-roll filler while longer response generates
 *
 * The STT / VAD stubs in this file are designed so that plugging in
 * Whisper.cpp or any other real-time transcription backend requires
 * replacing only the stub body — no callers need to change.
 *
 * Pipeline stage diagram (all overlapping):
 *
 *   [Input text ready]
 *       ↓
 *   [Split → chunks]           ← O(n) text split, ~0ms
 *       ↓
 *   [Speak chunk 0]            ← starts ~50–100ms after text arrives
 *       ↓ (while chunk 0 plays)
 *   [Prepare chunk 1, 2…]      ← queued, zero extra latency
 *       ↓
 *   [Micro-pause 50–150ms]     ← sounds human, not robotic
 *       ↓
 *   [Speak chunk 1]
 *       …
 *   [VAD fires → interrupt]    ← stops between chunks immediately
 */

const EventEmitter = require('events');
const ttsEngine = require('./tts_engine');

// ── Helpers ───────────────────────────────────────────────────────────────────

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ── Sentence splitter ─────────────────────────────────────────────────────────
// Splits text at sentence boundaries without breaking common abbreviations.
const ABBREV_RE = /\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|i\.e|e\.g)\.\s*$/i;
const MIN_CHUNK_LENGTH = 8; // chars — avoid tiny fragments

function splitSentences(raw) {
  const text = String(raw || '').trim();
  if (!text) return [];

  // Cap input to prevent exhaustion on very large strings
  const MAX_TEXT_LENGTH = 8000;
  const safeText = text.length > MAX_TEXT_LENGTH ? text.slice(0, MAX_TEXT_LENGTH) : text;
  const len = safeText.length;
  const chunks = [];
  let current = '';

  for (let i = 0; i < len; i++) {
    current += safeText[i];
    const ch = safeText[i];
    const next = i + 1 < len ? safeText[i + 1] : '';

    if ((ch === '.' || ch === '?' || ch === '!') &&
        (next === ' ' || next === '\n' || next === '')) {
      // Don't split on common abbreviations like "Dr. Smith"
      if (ch === '.' && ABBREV_RE.test(current)) continue;
      chunks.push(current.trim());
      current = '';
      if (next === ' ') i++; // consume the space
    }
  }
  if (current.trim()) chunks.push(current.trim());

  // Merge very short fragments into the following chunk
  const merged = [];
  let i = 0;
  while (i < chunks.length) {
    if (chunks[i].length < MIN_CHUNK_LENGTH && i + 1 < chunks.length) {
      merged.push(chunks[i] + ' ' + chunks[i + 1]);
      i += 2;
    } else {
      merged.push(chunks[i]);
      i++;
    }
  }
  return merged;
}

// ── Pre-roll phrase banks ─────────────────────────────────────────────────────
// System channel — terse, futuristic
const PRE_ROLL_SYSTEM = {
  thinking:     ['Processing.', 'Analyzing.', 'One moment.', 'Calculating.'],
  acknowledging: ['Confirmed.', 'Understood.', 'Received.'],
  error:        ['Error detected.', 'Fault noted.'],
  filler:       ['Standby.', 'Loading.', 'Initializing.'],
};

// Customer channel — warm, human-like
const PRE_ROLL_CUSTOMER = {
  thinking:     ['One moment, please.', 'Let me check that for you.', 'Just a moment.', 'Sure, let me look into that.'],
  acknowledging: ['Absolutely!', 'Of course.', 'Certainly!', 'I\'d be happy to help.'],
  error:        ['I\'m sorry to hear that.', 'Let me look into that right away.'],
  filler:       ['Alright…', 'Sure thing.', 'Let me see…'],
  closing:      ['Is there anything else I can help you with?', 'Have a wonderful day!', 'Thank you for calling.'],
};

function pickPreRoll(type, channel) {
  const bank = channel === 'customer' ? PRE_ROLL_CUSTOMER : PRE_ROLL_SYSTEM;
  const phrases = bank[type] || bank.thinking;
  return phrases[Math.floor(Math.random() * phrases.length)];
}

// ── Default pipeline settings ─────────────────────────────────────────────────
const DEFAULT_OPTIONS = {
  microPauseMs:     80,     // pause between sentence chunks (sounds natural)
  thinkingDelayMs:  0,      // artificial "thinking" delay before first chunk
  preRollEnabled:   true,   // speak filler before longer responses
  preRollThreshold: 2,      // only pre-roll if response has >= N chunks
  channel:          'system',
};

// ── StreamPipeline class ──────────────────────────────────────────────────────

class StreamPipeline extends EventEmitter {
  constructor(options = {}) {
    super();
    this._options   = { ...DEFAULT_OPTIONS, ...options };
    this._speaking  = false;
    this._interrupted = false;
    // Phrase warmup: register all known pre-roll phrases so they go through
    // text normalization once rather than per-call.
    this._phraseCache = new Set();
    this._warmPhraseCache();
  }

  // ── Cache warming ───────────────────────────────────────────────────────────

  _warmPhraseCache() {
    const all = [
      ...Object.values(PRE_ROLL_SYSTEM).flat(),
      ...Object.values(PRE_ROLL_CUSTOMER).flat(),
    ];
    for (const p of all) this._phraseCache.add(p.toLowerCase());
  }

  /**
   * Warm additional caller-supplied phrases into the cache.
   * @param {string[]} phrases
   */
  warmCache(phrases = []) {
    for (const p of phrases) {
      if (typeof p === 'string') this._phraseCache.add(p.toLowerCase());
    }
  }

  // ── State ───────────────────────────────────────────────────────────────────

  isSpeaking() {
    return this._speaking;
  }

  isInterrupted() {
    return this._interrupted;
  }

  // ── Interrupt ───────────────────────────────────────────────────────────────

  /**
   * Immediately stop speech and clear the audio buffer.
   * Safe to call at any time — idempotent.
   */
  async interrupt() {
    this._interrupted = true;
    this._speaking    = false;
    await ttsEngine.stop();
    this.emit('pipeline:interrupted');
  }

  _reset() {
    this._interrupted = false;
    this._speaking    = false;
  }

  // ── Pre-roll ────────────────────────────────────────────────────────────────

  /**
   * Speak an immediate filler phrase to fill perceived silence while a longer
   * response is being prepared.  Only speaks if not already interrupted.
   * @param {string} [type]    - Key from PRE_ROLL_* banks ('thinking', 'acknowledging', etc.)
   * @param {string} [channel] - 'system' | 'customer'
   */
  async preRoll(type = 'thinking', channel) {
    const ch = channel || this._options.channel;
    if (this._interrupted) return '';
    const phrase = pickPreRoll(type, ch);
    this.emit('pipeline:preroll', { phrase, channel: ch });
    await ttsEngine.speak(phrase, ch);
    return phrase;
  }

  // ── Core: streaming speak ───────────────────────────────────────────────────

  /**
   * Speak text using sentence-level chunk streaming.
   *
   * The first sentence plays within ~50–100ms of the call.  Remaining chunks
   * are chained with micro-pauses, and the whole thing can be interrupted by
   * calling interrupt() between chunks.
   *
   * @param {string} text
   * @param {object} [opts]
   * @param {string}   [opts.channel]           - 'system' | 'customer'
   * @param {number}   [opts.microPauseMs]       - ms gap between chunks
   * @param {number}   [opts.thinkingDelayMs]    - optional pre-speech delay
   * @param {boolean}  [opts.preRollEnabled]     - emit filler before long responses
   * @param {number}   [opts.preRollThreshold]   - min chunks to trigger pre-roll
   * @param {Function} [opts.onChunk]            - callback(text, index, total)
   * @returns {Promise<{chunks: number, interrupted: boolean}>}
   */
  async speakStreaming(text, opts = {}) {
    const options = { ...this._options, ...opts };
    const channel = options.channel;

    this._reset();
    this._speaking = true;
    this.emit('pipeline:started', { text, channel });

    // Pre-split all chunks upfront so we know the count before speaking
    const chunks = splitSentences(text);
    if (chunks.length === 0) {
      this._speaking = false;
      this.emit('pipeline:complete', { chunks: 0, interrupted: false });
      return { chunks: 0, interrupted: false };
    }

    // Optional pre-roll for multi-chunk responses (fills perceived silence)
    if (options.preRollEnabled && chunks.length >= options.preRollThreshold) {
      await this.preRoll('thinking', channel);
      if (this._interrupted) {
        this._speaking = false;
        return { chunks: 0, interrupted: true };
      }
    }

    // Optional "thinking" delay (human-like, added AFTER pre-roll)
    if (options.thinkingDelayMs > 0 && !this._interrupted) {
      await sleep(options.thinkingDelayMs);
    }

    let spokenCount = 0;

    for (let i = 0; i < chunks.length; i++) {
      if (this._interrupted) break;

      const chunk = chunks[i];
      this.emit('pipeline:chunk', { chunk, index: i, total: chunks.length, channel });
      if (typeof options.onChunk === 'function') options.onChunk(chunk, i, chunks.length);

      // Speak this sentence — returns when audio finishes
      await ttsEngine.speak(chunk, channel);
      spokenCount++;

      if (this._interrupted) break;

      // Micro-pause between sentences — sounds natural, not robotic
      if (i < chunks.length - 1 && options.microPauseMs > 0) {
        await sleep(options.microPauseMs);
      }
    }

    this._speaking = false;
    const interrupted = this._interrupted;
    this.emit('pipeline:complete', { chunks: spokenCount, interrupted });
    return { chunks: spokenCount, interrupted };
  }

  /**
   * Simulate a streamed LLM token feed.
   * Callers push tokens one by one; the pipeline accumulates and speaks
   * complete sentences as soon as a sentence boundary is detected.
   * This allows TTS to start before the full response is available.
   *
   * Usage:
   *   const session = pipeline.openTokenSession(opts);
   *   for await (const token of llmStream) session.pushToken(token);
   *   await session.flush();
   *
   * @param {object} [opts] - same options as speakStreaming
   * @returns {{ pushToken(t:string):void, flush():Promise<void>, interrupt():Promise<void> }}
   */
  openTokenSession(opts = {}) {
    const options = { ...this._options, ...opts };
    const channel = options.channel;
    this._reset();
    this._speaking = true;

    let buffer = '';
    let firstChunk = true;

    const flushBuffer = async () => {
      if (!buffer.trim() || this._interrupted) return;
      const toSpeak = buffer.trim();
      buffer = '';
      this.emit('pipeline:chunk', { chunk: toSpeak, channel });
      await ttsEngine.speak(toSpeak, channel);
      if (options.microPauseMs > 0 && !this._interrupted) {
        await sleep(options.microPauseMs);
      }
    };

    const pushToken = (token) => {
      if (this._interrupted) return;
      buffer += token;

      // Detect sentence boundary and flush immediately
      const trimmed = buffer.trimEnd();
      const lastChar = trimmed[trimmed.length - 1];
      if (lastChar === '.' || lastChar === '?' || lastChar === '!') {
        // Check it's not an abbreviation
        if (!ABBREV_RE.test(trimmed)) {
          // Fire and forget the flush — parallelism with incoming tokens
          void flushBuffer();
        }
      }

      // On first token, emit started event
      if (firstChunk) {
        firstChunk = false;
        this.emit('pipeline:started', { channel });
      }
    };

    const flush = async () => {
      await flushBuffer(); // flush any remaining buffer
      this._speaking = false;
      const interrupted = this._interrupted;
      this.emit('pipeline:complete', { interrupted });
    };

    const interruptSession = async () => {
      buffer = '';
      await this.interrupt();
    };

    return { pushToken, flush, interrupt: interruptSession };
  }

  // ── VAD stub ────────────────────────────────────────────────────────────────

  /**
   * Voice Activity Detection — stub for future real-time STT integration.
   *
   * When a real VAD library is available (e.g. silero-vad, WebRTC VAD),
   * replace this body.  The contract stays the same:
   *   returns Promise<{ detected: boolean, confidence: number }>
   *
   * @param {object} [_options]
   * @param {number} [_options.silenceThresholdMs] - ms of silence before returning
   * @returns {Promise<{ detected: boolean, confidence: number }>}
   */
  async detectSpeech(_options = {}) {
    // Stub: always reports no speech until real VAD is wired in.
    return { detected: false, confidence: 0 };
  }

  // ── STT stub ────────────────────────────────────────────────────────────────

  /**
   * Streaming speech-to-text — stub for future Whisper / whisper.cpp integration.
   *
   * When real STT is available, replace this async generator body.
   * Each yielded object has the contract:
   *   { partial: string, final: boolean, confidence: number }
   *
   * @param {*} _audioSource  - mic stream / WebRTC track / audio buffer
   * @param {object} [_options]
   * @param {number} [_options.silenceMs]     - silence timeout before final
   * @param {number} [_options.confidenceCutoff] - early-trigger threshold
   */
  // eslint-disable-next-line require-yield
  async *streamTranscribe(_audioSource, _options = {}) {
    // Stub: yields a single empty final result until STT is integrated.
    yield { partial: '', final: true, confidence: 0 };
  }

  // ── Configure ───────────────────────────────────────────────────────────────

  configure(patch = {}) {
    Object.assign(this._options, patch);
  }

  getOptions() {
    return { ...this._options };
  }
}

// ── Singleton ─────────────────────────────────────────────────────────────────
// A shared pipeline instance is exported so call_engine and voice_manager
// can both attach listeners without creating duplicate emitters.

const sharedPipeline = new StreamPipeline();

module.exports = {
  StreamPipeline,
  pipeline: sharedPipeline,
  splitSentences,
  PRE_ROLL_SYSTEM,
  PRE_ROLL_CUSTOMER,
  pickPreRoll,
};

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { Router, raw } = require('express');
const voiceManager = require('../core/voice_manager');
const callEngine = require('../services/voice/call_engine');
const { VOICE_PROFILES } = require('../services/voice/tts_engine');
const personaplex = require('../services/voice/nvidia_personaplex');
const fishSpeech = require('../services/voice/fish_speech');
const voiceSessions = require('../services/voice/session_manager');
const voiceRuntime = require('../services/voice/voice_runtime_manager');
const { splitSentences } = require('../services/voice/stream_pipeline');

const router = Router();
const audioBodyParser = raw({
  type: ['audio/wav', 'audio/x-wav', 'audio/wave', 'application/octet-stream'],
  limit: '25mb',
});

function classifyFishRuntime(status) {
  if (status?.available) return 'ready';
  if (!status?.configured) return 'runtime_missing';
  const err = String(status?.last_error || '').toLowerCase();
  if (!err) return 'starting';
  if (err.includes('model') || err.includes('checkpoint') || err.includes('weight') || err.includes('reference')) {
    return 'model_missing';
  }
  if (err.includes('econnrefused') || err.includes('enotfound') || err.includes('timeout') || err.includes('not reachable')) {
    return 'runtime_missing';
  }
  return 'error';
}

async function getVoiceRuntimeStatus(cfg = voiceManager.getConfig()) {
  const managed = await voiceRuntime.getStatus();
  const fish = managed.tts?.fish_speech || fishSpeech.getStatus();
  const fishState = managed.tts?.fish_speech?.state || classifyFishRuntime(fish);
  const voiceCoreState = managed.tts?.voice_core_local?.state || managed.tts?.state || 'bundle_missing';
  const voiceLiteState = managed.tts?.voice_lite?.state || managed.tts?.state || 'runtime_missing';
  const provider = cfg.provider || managed.tts?.provider || 'voice_core_local';
  const engine = voiceManager.getEngineStatus();
  return {
    ...managed,
    state: provider === 'fish_speech'
      ? fishState
      : provider === 'voice_core_local' || provider === 'voice_core'
        ? voiceCoreState
      : String(provider).startsWith('voice_lite')
        ? voiceLiteState
        : (engine.silent ? 'runtime_missing' : 'ready'),
    provider,
    tts: {
      ...(managed.tts || {}),
      fish_speech: fish,
      local_fallback: {
        available: !engine.silent,
        backend: engine.fallback_backend,
      },
    },
    stt: {
      ...(managed.stt || {}),
      fallback_provider: 'browser_speech_recognition',
    },
  };
}

function extractReply(payload) {
  if (!payload) return '';
  if (typeof payload === 'string') return payload;
  return String(payload.reply || payload.assistant_reply || payload.content || payload.message || '').trim();
}

function getVoiceIdentity() {
  const cfg = voiceManager.getConfig();
  const identity = cfg.identity || {};
  const userName = String(identity.userName || 'Lars').trim() || 'Lars';
  const rank = String(identity.rank || 'Chief').trim() || 'Chief';
  return {
    userName,
    rank,
    address: [rank, userName].filter(Boolean).join(' '),
    addressStyle: identity.addressStyle || 'command',
    startupStyle: identity.startupStyle || 'soldier',
  };
}

function buildVoiceAgentInstructions(identity = getVoiceIdentity()) {
  return [
    `Address the user as ${identity.address} naturally. Do not repeat the name in every sentence.`,
    'Speak like a calm, high-context teammate: concise, intelligent, direct, and useful.',
    'Reply in the same language as the user unless the user asks for another language.',
    'When the user wants to make a plan, collaborate on the plan and keep next actions concrete.',
    'When the user gives a voice command, treat it as actionable intent and route it through the existing system capabilities.',
    'Never bypass approval gates. Ask for approval before destructive, external-account, publishing, payment, wallet, money-spending, or security-sensitive actions.',
  ].join('\n');
}

async function callChatPipeline(req, message, sessionId) {
  const proto = req.protocol || 'http';
  const host = req.get('host') || `localhost:${process.env.PORT || 8787}`;
  const requestBody = req.body && !Buffer.isBuffer(req.body) && typeof req.body === 'object' ? req.body : {};
  const identity = getVoiceIdentity();
  const voiceInstructions = buildVoiceAgentInstructions(identity);
  const headers = {
    'Content-Type': 'application/json',
    'X-Session-Id': sessionId,
  };
  if (req.headers.authorization) headers.Authorization = req.headers.authorization;

  const body = JSON.stringify({
    message,
    context: {
      ...(requestBody.context && typeof requestBody.context === 'object' ? requestBody.context : {}),
      modality: 'voice',
      voice_session_id: sessionId,
      raw_transcript: message,
      voice_user_name: identity.userName,
      voice_user_rank: identity.rank,
      voice_address: identity.address,
      voice_command_mode: true,
      voice_instructions: voiceInstructions,
      requires_approval_for_sensitive_actions: true,
      use_turn_runner: requestBody.context?.use_turn_runner !== false,
    },
  });
  const candidates = [
    { source: 'node_chat', url: `${proto}://${host}/chat`, headers },
    { source: 'node_api_chat', url: `${proto}://${host}/api/chat`, headers },
    {
      source: 'python_chat',
      url: `http://${process.env.PYTHON_BACKEND_HOST || '127.0.0.1'}:${process.env.PYTHON_BACKEND_PORT || 18790}/api/chat`,
      headers,
    },
  ];
  const failures = [];
  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate.url, { method: 'POST', headers: candidate.headers, body });
      const raw = await response.text();
      let payload = null;
      try { payload = raw ? JSON.parse(raw) : {}; } catch (_err) { payload = { content: raw }; }
      if (!response.ok) {
        failures.push({
          source: candidate.source,
          status: response.status,
          error: payload?.error || payload?.message || payload?.detail || raw || `HTTP ${response.status}`,
        });
        continue;
      }
      const reply = extractReply(payload);
      if (reply) return { payload: { ...payload, source: payload.source || candidate.source }, reply };
      failures.push({ source: candidate.source, status: response.status, error: 'empty_reply' });
    } catch (err) {
      failures.push({ source: candidate.source, error: String(err.message || err) });
    }
  }

  return {
    payload: {
      ok: true,
      source: 'local_voice_fallback',
      chat_unavailable: true,
      failures,
    },
    reply: buildLocalVoiceFallback(message, identity),
  };
}

function buildLocalVoiceFallback(message, identity = getVoiceIdentity()) {
  const text = String(message || '').trim();
  const lower = ` ${text.toLowerCase()} `;
  const dutchHits = [' de ', ' het ', ' een ', ' niet ', ' hoe ', ' waarom ', ' systeem ', ' klaar ', ' kan ', ' werkt ']
    .filter((word) => lower.includes(word)).length;
  if (dutchHits >= 2) {
    return `${identity.address}, ik heb je gehoord: "${text}". De lokale stem, transcriptie en avatar-route werken. De hoofd-chatroute is nu niet beschikbaar, dus dit is een beperkte lokale reactie.`;
  }
  return `${identity.address}, I heard you: "${text}". Local voice, transcription, and the avatar route are working. The main chat route is not available right now, so this is a limited local response.`;
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

function formatVoiceSpokenReply(reply, transcript, payload = {}, identity = getVoiceIdentity()) {
  const original = String(reply || '').trim();
  if (!original) return buildLocalVoiceFallback(transcript, identity);
  let result = original;
  const resultMatch = original.match(/(?:^|\n)Result:\s*\n([\s\S]*?)(?:\n\nProof:|\n\nBlocked by:|$)/i);
  if (resultMatch?.[1]) result = resultMatch[1].trim();
  if (payload?.source === 'approval_gate') {
    result = 'I paused that before execution because it needs approval. Approve it first, then I can continue.';
  } else if (payload?.source === 'node-fallback' && /unable to reach the ai backend/i.test(result)) {
    result = 'I queued the request, but the main AI backend is unavailable right now. Start Ollama or configure an API key, then I can continue with full planning.';
  }
  result = result
    .replace(/\s*Proof:\s*[\s\S]*$/i, '')
    .replace(/\s*Blocked by:\s*[\s\S]*$/i, '')
    .trim();
  result = cleanMarkdownForSpeech(result);
  if (!result) result = original.replace(/\s+/g, ' ').slice(0, 500);
  if (result.toLowerCase().startsWith(identity.address.toLowerCase())) return result;
  return `${identity.address}, ${result}`;
}

async function processVoiceTextTurn(req, res, session, text) {
  const transcript = String(text || '').trim();
  if (!transcript) {
    return res.status(400).json({ ok: false, error: 'text or transcript is required.' });
  }

  const epoch = voiceSessions.nextTurn(session.id);
  const started = Date.now();
  voiceSessions.setTranscript(session.id, transcript, true);
  voiceSessions.setPhase(session.id, voiceSessions.VOICE_PHASES.TRANSCRIBING);
  voiceSessions.setPhase(session.id, voiceSessions.VOICE_PHASES.THINKING);

  try {
    const { payload, reply } = await callChatPipeline(req, transcript, session.id);
    const identity = getVoiceIdentity();
    const spokenReply = formatVoiceSpokenReply(reply, transcript, payload, identity);
    if (!voiceSessions.isTurnCurrent(session.id, epoch)) {
      return res.json({ ok: false, interrupted: true, session: voiceSessions.publicSession(session) });
    }

    const chunks = splitSentences(spokenReply);
    chunks.forEach((chunk, index) => voiceSessions.appendReplyChunk(session.id, chunk, index, chunks.length));
    const latencyMs = Date.now() - started;
    voiceSessions.setReply(session.id, spokenReply, latencyMs, {
      source: payload.source || payload.model || 'chat_pipeline',
      taskId: payload.taskId || null,
      workflow_run: payload.workflow_run || null,
      structured_reply: reply,
    });
    voiceSessions.setPhase(session.id, voiceSessions.VOICE_PHASES.IDLE, {
      reply_ready: true,
      playback_owner: 'frontend',
    });

    return res.json({
      ok: true,
      session: voiceSessions.publicSession(voiceSessions.getSession(session.id)),
      reply: spokenReply,
      content: spokenReply,
      latency_ms: latencyMs,
      chat: {
        source: payload.source || null,
        taskId: payload.taskId || null,
        workflow_run: payload.workflow_run || null,
        memory_router: payload.memory_router || null,
        structured_reply: reply,
      },
    });
  } catch (err) {
    voiceSessions.setError(session.id, String(err.message || err));
    return res.status(502).json({
      ok: false,
      session: voiceSessions.publicSession(voiceSessions.getSession(session.id)),
      error: String(err.message || err),
    });
  }
}

function sendSse(res, event) {
  res.write(`data: ${JSON.stringify(event)}\n\n`);
}

function tempWavPath(sessionId) {
  const safeId = String(sessionId || 'voice').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 48) || 'voice';
  return path.join(os.tmpdir(), `voice-session-${safeId}-${Date.now()}-${crypto.randomUUID()}.wav`);
}

async function processVoiceAudioTurn(req, res, session, audioBuffer) {
  if (!Buffer.isBuffer(audioBuffer) || audioBuffer.length < 44) {
    voiceSessions.setError(session.id, 'Audio upload was empty or invalid.');
    return res.status(400).json({
      ok: false,
      error: 'invalid_audio',
      session: voiceSessions.publicSession(voiceSessions.getSession(session.id)),
    });
  }

  voiceSessions.setPhase(session.id, voiceSessions.VOICE_PHASES.TRANSCRIBING);
  const runtime = await voiceRuntime.getStatus();
  voiceSessions.setRuntime(session.id, runtime);

  if (runtime.stt?.state !== 'ready') {
    const message = runtime.stt?.recommendation || runtime.recommendation || 'Local Whisper STT is not ready.';
    voiceSessions.setError(session.id, message, { stt: runtime.stt });
    return res.status(503).json({
      ok: false,
      error: 'local_stt_unavailable',
      message,
      runtime,
      session: voiceSessions.publicSession(voiceSessions.getSession(session.id)),
    });
  }

  const speech = voiceRuntime.hasLikelySpeech(audioBuffer);
  if (speech.detected === false) {
    const message = 'No speech was detected in the uploaded audio.';
    voiceSessions.setError(session.id, message, { vad: { ...runtime.vad, fallback: speech } });
    return res.status(422).json({
      ok: false,
      error: 'no_speech_detected',
      message,
      runtime,
      vad: speech,
      session: voiceSessions.publicSession(voiceSessions.getSession(session.id)),
    });
  }

  const filePath = tempWavPath(session.id);
  try {
    await fs.promises.writeFile(filePath, audioBuffer);
    const transcription = await voiceRuntime.transcribeWav(filePath);
    const transcript = String(transcription?.text || '').trim();
    if (!transcript) {
      const message = 'Whisper returned an empty transcript.';
      voiceSessions.setError(session.id, message, { transcription });
      return res.status(422).json({
        ok: false,
        error: 'empty_transcript',
        message,
        transcription,
        session: voiceSessions.publicSession(voiceSessions.getSession(session.id)),
      });
    }
    voiceSessions.emit(session.id, 'transcript.metadata', { transcription });
    return processVoiceTextTurn(req, res, session, transcript);
  } catch (err) {
    voiceSessions.setError(session.id, String(err.message || err), { stt: runtime.stt });
    return res.status(500).json({
      ok: false,
      error: 'transcription_failed',
      message: String(err.message || err),
      runtime,
      session: voiceSessions.publicSession(voiceSessions.getSession(session.id)),
    });
  } finally {
    fs.promises.unlink(filePath).catch(() => {});
  }
}

// ── System voice ──────────────────────────────────────────────────────────────

// GET /api/voice/runtime
router.get('/runtime', async (_req, res) => {
  try {
    res.json(await getVoiceRuntimeStatus());
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/runtime/logs
router.get('/runtime/logs', (_req, res) => {
  const limit = Math.max(1, Math.min(500, Number(_req.query?.limit) || 100));
  res.json(voiceRuntime.getLogs(limit));
});

// GET /api/voice/runtime/doctor
router.get('/runtime/doctor', async (_req, res) => {
  try {
    res.json(await voiceRuntime.doctor());
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/bundle/status
router.get('/bundle/status', async (_req, res) => {
  try {
    res.json(await voiceRuntime.voiceCoreStatus());
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/bundle/verify
router.post('/bundle/verify', async (req, res) => {
  try {
    res.json(await voiceRuntime.verifyVoiceCoreBundle(req.body || {}));
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err), runtime: await getVoiceRuntimeStatus().catch(() => null) });
  }
});

// GET /api/voice/model/samples
router.get('/model/samples', (_req, res) => {
  try {
    res.json({ ok: true, samples: voiceRuntime.voiceCoreSamples() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/bundle/samples/:sampleId
router.get('/bundle/samples/:sampleId', (req, res) => {
  try {
    const sample = voiceRuntime.getVoiceCoreSampleFile(req.params.sampleId);
    if (!sample) return res.status(404).json({ ok: false, error: 'voice_core_sample_missing' });
    res.setHeader('Content-Type', 'audio/wav');
    return res.sendFile(sample.path);
  } catch (err) {
    return res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/model/benchmark
router.post('/model/benchmark', async (req, res) => {
  try {
    const result = await voiceRuntime.benchmarkVoiceCore(req.body || {});
    res.status(result.ok === false ? 503 : 200).json(result);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err), runtime: await getVoiceRuntimeStatus().catch(() => null) });
  }
});

// POST /api/voice/runtime/self-test
router.post('/runtime/self-test', async (req, res) => {
  try {
    const result = await voiceRuntime.selfTest(req.body || {});
    res.json(result);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err), runtime: await getVoiceRuntimeStatus().catch(() => null) });
  }
});

// POST /api/voice/runtime/download
router.post('/runtime/download', async (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  const component = req.body?.component || req.body?.target;
  try {
    sendSse(res, { type: 'download.started', component, state: 'starting', percent: 0 });
    const result = await voiceRuntime.download(component, req.body || {}, (event) => sendSse(res, event));
    sendSse(res, { type: 'download.complete', component, state: 'complete', percent: 100, result });
  } catch (err) {
    sendSse(res, {
      type: 'download.error',
      component,
      state: 'error',
      error: String(err.message || err),
      message: String(err.message || err),
    });
  } finally {
    res.end();
  }
});

// POST /api/voice/runtime/download/cancel
router.post('/runtime/download/cancel', (req, res) => {
  try {
    res.json(voiceRuntime.cancelDownload(req.body?.component || null));
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/runtime/start
router.post('/runtime/start', async (req, res) => {
  try {
    const component = req.body?.component || 'voice_core_local';
    let result;
    if (['voice_core', 'voice_core_local', 'voice_core_bundle', 'default_voice'].includes(component)) {
      result = await voiceRuntime.startVoiceCore(req.body || {});
    } else if (['voice_lite', 'voice-lite', 'piper', 'voice_lite_runtime'].includes(component)) {
      result = await voiceRuntime.startVoiceLite(req.body || {});
    } else if (['fish', 'fish_speech', 'tts'].includes(component)) {
      result = await voiceRuntime.startFish(req.body || {});
    } else {
      return res.status(400).json({ ok: false, error: `Unsupported voice runtime start component: ${component}` });
    }
    res.json({ ok: true, result, runtime: await getVoiceRuntimeStatus() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err), runtime: await getVoiceRuntimeStatus().catch(() => null) });
  }
});

// POST /api/voice/runtime/stop
router.post('/runtime/stop', async (_req, res) => {
  try {
    const component = _req.body?.component || 'fish_speech';
    const result = ['voice_core', 'voice_core_local', 'voice_core_bundle', 'default_voice'].includes(component)
      ? { ok: true, stopped: false, message: 'Default Human Voice is process-per-synthesis; no background process to stop.' }
      : ['voice_lite', 'voice-lite', 'piper', 'voice_lite_runtime'].includes(component)
        ? { ok: true, stopped: false, message: 'Voice Lite CPU runtime is process-per-synthesis; no background process to stop.' }
      : await voiceRuntime.stopFish();
    res.json({ ok: true, result, runtime: await getVoiceRuntimeStatus() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err), runtime: await getVoiceRuntimeStatus().catch(() => null) });
  }
});

// GET /api/voice/custom-voice/dataset/status
router.get('/custom-voice/dataset/status', (_req, res) => {
  try {
    res.json(voiceRuntime.voiceLiteDatasetStatus());
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/custom-voice/dataset
router.post('/custom-voice/dataset', (req, res) => {
  try {
    res.json(voiceRuntime.saveVoiceLiteDatasetManifest(req.body || {}));
  } catch (err) {
    res.status(400).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/custom-voice/train
router.post('/custom-voice/train', (req, res) => {
  try {
    const job = voiceRuntime.startVoiceLiteTraining(req.body || {});
    res.status(job.state === 'blocked' ? 422 : 202).json({ ok: job.state !== 'blocked', job });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/custom-voice/train/:jobId
router.get('/custom-voice/train/:jobId', (req, res) => {
  try {
    const job = voiceRuntime.getVoiceLiteTrainingJob(req.params.jobId);
    res.status(job.state === 'not_found' ? 404 : 200).json({ ok: job.state !== 'not_found', job });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/custom-voice/benchmark
router.post('/custom-voice/benchmark', async (req, res) => {
  try {
    const result = await voiceRuntime.benchmarkVoiceLite(req.body || {});
    res.status(result.ok === false ? 503 : 200).json(result);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/custom-voice/activate
router.post('/custom-voice/activate', (req, res) => {
  try {
    res.json(voiceRuntime.activateVoiceLite(req.body || {}));
  } catch (err) {
    res.status(422).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/sessions
router.post('/sessions', async (req, res) => {
  try {
    const runtime = await getVoiceRuntimeStatus();
    const session = voiceSessions.createSession({
      source: req.body?.source || 'voice_modal',
      user_id: req.jwtPayload?.sub || req.user?.id || null,
      tenant_id: req.tenant?.id || req.jwtPayload?.tenant_id || null,
      runtime,
    });
    res.status(201).json({ ok: true, session: voiceSessions.publicSession(session), runtime });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/sessions/:sessionId
router.get('/sessions/:sessionId', (req, res) => {
  const session = voiceSessions.getSession(req.params.sessionId);
  if (!session) return res.status(404).json({ ok: false, error: 'voice session not found' });
  res.json({ ok: true, session: voiceSessions.publicSession(session) });
});

// GET /api/voice/sessions/:sessionId/events
router.get('/sessions/:sessionId/events', (req, res) => {
  const ok = voiceSessions.subscribe(req.params.sessionId, res);
  if (!ok) return res.status(404).json({ ok: false, error: 'voice session not found' });
});

// POST /api/voice/sessions/:sessionId/text
router.post('/sessions/:sessionId/text', async (req, res) => {
  const session = voiceSessions.getSession(req.params.sessionId);
  if (!session) return res.status(404).json({ ok: false, error: 'voice session not found' });
  const text = req.body?.text || req.body?.transcript || req.body?.message;
  return processVoiceTextTurn(req, res, session, text);
});

// POST /api/voice/sessions/:sessionId/audio
router.post('/sessions/:sessionId/audio', audioBodyParser, async (req, res) => {
  const session = voiceSessions.getSession(req.params.sessionId);
  if (!session) return res.status(404).json({ ok: false, error: 'voice session not found' });

  const transcript = req.body?.transcript || req.body?.text;
  if (transcript) return processVoiceTextTurn(req, res, session, transcript);
  return processVoiceAudioTurn(req, res, session, req.body);
});

// POST /api/voice/sessions/:sessionId/interrupt
router.post('/sessions/:sessionId/interrupt', async (req, res) => {
  const session = voiceSessions.getSession(req.params.sessionId);
  if (!session) return res.status(404).json({ ok: false, error: 'voice session not found' });
  try {
    voiceSessions.interrupt(session.id);
    await voiceManager.getPipeline().interrupt();
    res.json({ ok: true, session: voiceSessions.publicSession(voiceSessions.getSession(session.id)) });
  } catch (err) {
    voiceSessions.setError(session.id, String(err.message || err));
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/converse — compatibility wrapper for legacy clients.
router.post('/converse', async (req, res) => {
  try {
    const runtime = await getVoiceRuntimeStatus();
    const session = voiceSessions.createSession({
      source: 'voice_converse_compat',
      user_id: req.jwtPayload?.sub || req.user?.id || null,
      tenant_id: req.tenant?.id || req.jwtPayload?.tenant_id || null,
      runtime,
    });
    const text = req.body?.text || req.body?.transcript || req.body?.message;
    return processVoiceTextTurn(req, res, session, text);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/config
router.get('/config', async (_req, res) => {
  const profiles = Object.keys(VOICE_PROFILES);
  const pipeline = voiceManager.getPipeline();
  const cfg = voiceManager.getConfig();
  fishSpeech.configure(cfg.fishSpeech || {});
  const fishAvailable = await fishSpeech.checkAvailability();
  const runtime = await getVoiceRuntimeStatus(cfg);
  res.json({
    config: cfg,
    profiles: profiles.filter((p) => !p.startsWith('customer_')),
    customer_profiles: profiles.filter((p) => p.startsWith('customer_')),
    tones: ['futuristic', 'neutral', 'calm', 'sharp'],
    customer_tones: ['warm', 'professional'],
    providers: [
      {
        id: 'voice_core_local',
        label: 'Default Human Voice',
        status: runtime.tts?.voice_core_local?.state === 'ready' ? 'live' : 'not_configured',
        local: true,
        recommended: true,
        docs_hint: 'Bundled zero-install EN/NL voice core. No user voice training, GPU, internet, or Fish setup required.',
      },
      {
        id: 'voice_lite',
        label: 'Voice Lite CPU compatibility',
        status: runtime.tts?.voice_lite?.state === 'ready' ? 'live' : 'not_configured',
        local: true,
        recommended: false,
        docs_hint: 'Optional compatibility route. Default production speech uses the bundled Default Human Voice.',
      },
      {
        id: 'fish_speech',
        label: 'Fish Speech S2 Premium',
        status: fishAvailable ? 'live' : 'unavailable',
        local: true,
        docs_hint: 'Premium/research route only when hardware, license, runtime, and model checks pass.',
      },
      {
        id: 'local',
        label: 'Local OS voice fallback',
        status: voiceManager.getEngineStatus().silent ? 'unavailable' : 'fallback',
        local: true,
        docs_hint: 'Uses installed OS TTS commands such as espeak-ng, say, or spd-say.',
      },
      {
        id: 'personaplex',
        label: 'Nvidia PersonaPlex',
        status: personaplex.isAvailable() ? 'live' : 'not_configured',
        local: false,
        docs_hint: 'Legacy optional cloud voice route. Fish Speech is preferred for local ownership.',
      },
    ],
    verbosity_levels: { 0: 'silent', 1: 'critical', 2: 'important', 3: 'normal', 4: 'verbose' },
    mode: voiceManager.getMode(),
    pipeline: pipeline.getOptions(),
    engine: voiceManager.getEngineStatus(),
    fish_speech: fishSpeech.getStatus(),
    runtime,
  });
});

// POST /api/voice/config
router.post('/config', (req, res) => {
  const patch = req.body;
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
    return res.status(400).json({ ok: false, error: 'Body must be a JSON object.' });
  }
  try {
    voiceManager.applyConfig(patch);
    // If pipeline settings are included, apply them too
    if (patch.pipeline && typeof patch.pipeline === 'object') {
      voiceManager.getPipeline().configure(patch.pipeline);
    }
    const cfg = voiceManager.getConfig();
    fishSpeech.configure(cfg.fishSpeech || {});
    res.json({ ok: true, config: cfg, engine: voiceManager.getEngineStatus(), fish_speech: fishSpeech.getStatus() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/test
router.post('/test', async (req, res) => {
  try {
    const cfg = voiceManager.getConfig();
    if (!cfg.enabled) return res.json({ ok: false, message: 'Voice is disabled.' });
    const text = String(req.body?.text || 'Voice system online. Default human voice route checked.').slice(0, 500);
    void voiceManager.speak(text, true);
    res.json({
      ok: true,
      message: 'Test phrase dispatched.',
      provider: cfg.provider || 'voice_core_local',
      fish_speech: fishSpeech.getStatus(),
      engine: voiceManager.getEngineStatus(),
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// ── Mode switching ────────────────────────────────────────────────────────────

// POST /api/voice/mode   { mode: 'system' | 'customer' }
router.post('/mode', (req, res) => {
  const { mode } = req.body || {};
  if (mode !== 'system' && mode !== 'customer') {
    return res.status(400).json({ ok: false, error: 'mode must be "system" or "customer".' });
  }
  voiceManager.setMode(mode);
  res.json({ ok: true, mode: voiceManager.getMode() });
});

// GET /api/voice/mode
router.get('/mode', (_req, res) => {
  res.json({ mode: voiceManager.getMode() });
});

// ── Pipeline control ──────────────────────────────────────────────────────────

// GET /api/voice/pipeline
// Returns current pipeline settings and speaking status.
router.get('/pipeline', (_req, res) => {
  const pipeline = voiceManager.getPipeline();
  res.json({
    options: pipeline.getOptions(),
    speaking: pipeline.isSpeaking(),
    interrupted: pipeline.isInterrupted(),
  });
});

// POST /api/voice/pipeline/config
// Update pipeline settings (microPauseMs, thinkingDelayMs, preRollEnabled, etc.)
router.post('/pipeline/config', (req, res) => {
  const patch = req.body;
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
    return res.status(400).json({ ok: false, error: 'Body must be a JSON object.' });
  }
  try {
    voiceManager.getPipeline().configure(patch);
    res.json({ ok: true, options: voiceManager.getPipeline().getOptions() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/pipeline/interrupt
// Immediately stop all speech (manual override — works for both system and call sessions).
router.post('/pipeline/interrupt', async (_req, res) => {
  try {
    await voiceManager.getPipeline().interrupt();
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/pipeline/preroll   { type?, channel? }
// Speak an immediate filler phrase.
router.post('/pipeline/preroll', async (req, res) => {
  const { type = 'thinking', channel } = req.body || {};
  try {
    const phrase = await voiceManager.getPipeline().preRoll(type, channel || voiceManager.getMode());
    res.json({ ok: true, phrase });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// ── Customer call control ─────────────────────────────────────────────────────

// POST /api/voice/calls/start   { sessionId, greeting?, profile? }
router.post('/calls/start', async (req, res) => {
  const { sessionId, greeting, profile } = req.body || {};
  if (!sessionId) return res.status(400).json({ ok: false, error: 'sessionId is required.' });

  const cfg = voiceManager.getConfig();
  if (!cfg.customer?.enabled) {
    return res.status(403).json({ ok: false, error: 'Customer voice is disabled.' });
  }

  try {
    const session = await voiceManager.triggerCall(sessionId, {
      greeting,
      profile: profile || cfg.customer?.profile || 'customer_default',
    });
    res.json({ ok: true, session: session || { sessionId } });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/calls/:sessionId/speak   { text }
router.post('/calls/:sessionId/speak', async (req, res) => {
  const { sessionId } = req.params;
  const { text } = req.body || {};
  if (!text) return res.status(400).json({ ok: false, error: 'text is required.' });
  if (!callEngine.isActive(sessionId)) {
    return res.status(404).json({ ok: false, error: `No active call session: ${sessionId}` });
  }
  try {
    await callEngine.speak(sessionId, text);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/calls/:sessionId/interrupt
router.post('/calls/:sessionId/interrupt', async (req, res) => {
  const { sessionId } = req.params;
  try {
    await callEngine.interrupt(sessionId);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/calls/:sessionId/end
router.post('/calls/:sessionId/end', async (req, res) => {
  const { sessionId } = req.params;
  try {
    await voiceManager.stopCall(sessionId);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/calls
router.get('/calls', (_req, res) => {
  res.json({ sessions: callEngine.listActiveSessions() });
});

// POST /api/voice/calls/test  — test customer voice phrase
router.post('/calls/test', async (req, res) => {
  const cfg = voiceManager.getConfig();
  if (!cfg.customer?.enabled) {
    return res.json({ ok: false, message: 'Customer voice is disabled.' });
  }
  const sid = `test-${Date.now()}`;
  try {
    await callEngine.startCall(sid, {
      profile: cfg.customer?.profile || 'customer_default',
      greeting: 'Hello! This is a customer voice test. Everything sounds great.',
    });
    await callEngine.endCall(sid, 'user_ended');
    res.json({ ok: true, message: 'Customer voice test dispatched.' });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// ── Local Fish Speech S2 + legacy PersonaPlex synthesis ───────────────────────

// POST /api/voice/synthesize
// Body: { text: string, provider?: 'voice_core_local'|'voice_lite'|'fish_speech'|'personaplex', persona?: {...} }
// Returns audio/wav binary on success, or JSON error.
router.post('/synthesize', async (req, res) => {
  const { text, persona = {}, provider, language, voice, gender, emotion, emotion_intensity, speaking_rate, energy, pause_style } = req.body || {};
  if (!text || typeof text !== 'string' || !text.trim()) {
    return res.status(400).json({ ok: false, error: 'text is required.' });
  }
  const cfg = voiceManager.getConfig();
  const selectedProvider = provider || persona.provider || cfg.provider || 'voice_core_local';

  if (selectedProvider === 'voice_core_local' || selectedProvider === 'voice_core' || selectedProvider === 'default_voice') {
    try {
      const synth = await voiceRuntime.synthesizeVoiceCore(text.trim(), {
        language: language || persona.language,
        voice: voice || persona.voice || 'default',
        gender: gender || persona.gender,
        emotion: emotion || persona.emotion || persona.tone,
        emotion_intensity: emotion_intensity ?? persona.emotion_intensity,
        speaking_rate: speaking_rate ?? persona.speaking_rate ?? persona.speed,
        energy: energy ?? persona.energy,
        pause_style: pause_style || persona.pause_style,
        persona,
        threads: persona?.voiceCore?.threads || persona?.voiceLite?.threads,
        timeoutMs: persona?.voiceCore?.timeoutMs || persona?.voiceLite?.timeoutMs,
      });
      const audioBuf = synth.audioBuf || synth;
      const meta = synth.meta || {};
      const artifact = voiceRuntime.saveVoiceCoreArtifact(audioBuf, cfg.voiceCore || cfg.voiceLite || {});
      res.setHeader('Content-Type', 'audio/wav');
      res.setHeader('Content-Length', audioBuf.length);
      res.setHeader('X-Voice-Provider', 'voice_core_local');
      res.setHeader('X-Voice-Language', meta.language || language || '');
      res.setHeader('X-Voice-Voice', meta.voice || voice || '');
      if (meta.speech_plan?.emotion) res.setHeader('X-Voice-Emotion', meta.speech_plan.emotion);
      if (meta.rtf != null) res.setHeader('X-Voice-RTF', String(meta.rtf));
      if (meta.ttfa_ms != null) res.setHeader('X-Voice-TTFA', String(meta.ttfa_ms));
      res.setHeader('X-Voice-Artifact-Id', artifact.id);
      res.setHeader('X-Voice-Artifact-Url', artifact.url);
      return res.send(audioBuf);
    } catch (err) {
      const runtime = await getVoiceRuntimeStatus(cfg).catch(() => null);
      return res.status(503).json({
        ok: false,
        provider: 'voice_core_local',
        status: runtime?.tts?.voice_core_local?.state || 'error',
        error: String(err.message || err),
        setup: runtime?.tts?.voice_core_local?.recommendation || runtime?.recommendation?.details || 'Verify the bundled Default Human Voice package.',
        fallback: cfg.voiceCore?.localFallback === true ? 'browser_or_os_tts' : 'explicit_only',
        runtime,
      });
    }
  }

  if (selectedProvider === 'voice_lite' || selectedProvider === 'voice_lite_custom' || selectedProvider === 'voice_lite_base') {
    try {
      const synth = await voiceRuntime.synthesizeVoiceLite(text.trim(), {
        language: language || persona.language,
        voice: voice || persona.voice || (selectedProvider === 'voice_lite_base' ? 'base' : 'custom'),
        emotion: emotion || persona.emotion || persona.tone,
        emotion_intensity: emotion_intensity ?? persona.emotion_intensity,
        speaking_rate: speaking_rate ?? persona.speaking_rate ?? persona.speed,
        energy: energy ?? persona.energy,
        pause_style: pause_style || persona.pause_style,
        persona,
        threads: persona?.voiceLite?.threads,
        timeoutMs: persona?.voiceLite?.timeoutMs,
      });
      const audioBuf = synth.audioBuf || synth;
      const meta = synth.meta || {};
      const artifact = voiceRuntime.saveVoiceLiteArtifact(audioBuf, cfg.voiceLite || {});
      res.setHeader('Content-Type', 'audio/wav');
      res.setHeader('Content-Length', audioBuf.length);
      res.setHeader('X-Voice-Provider', 'voice_lite_cpu');
      res.setHeader('X-Voice-Language', meta.language || language || '');
      res.setHeader('X-Voice-Voice', meta.voice || voice || '');
      if (meta.rtf != null) res.setHeader('X-Voice-RTF', String(meta.rtf));
      if (meta.ttfa_ms != null) res.setHeader('X-Voice-TTFA', String(meta.ttfa_ms));
      res.setHeader('X-Voice-Artifact-Id', artifact.id);
      res.setHeader('X-Voice-Artifact-Url', artifact.url);
      return res.send(audioBuf);
    } catch (err) {
      const runtime = await getVoiceRuntimeStatus(cfg).catch(() => null);
      return res.status(503).json({
        ok: false,
        provider: 'voice_lite',
        status: runtime?.tts?.voice_lite?.state || 'error',
        error: String(err.message || err),
        setup: runtime?.tts?.voice_lite?.recommendation || runtime?.recommendation?.details || 'Install Piper runtime and download Voice Lite base EN/NL voices.',
        fallback: cfg.voiceLite?.localFallback !== false ? 'browser_or_os_tts' : 'disabled',
        runtime,
      });
    }
  }

  if (selectedProvider === 'fish_speech') {
    fishSpeech.configure({ ...(cfg.fishSpeech || {}), ...(persona.fishSpeech || {}) });
    const fishAvailable = await fishSpeech.checkAvailability();
    if (!fishAvailable) {
      return res.status(503).json({
        ok: false,
        provider: 'fish_speech',
        status: 'unavailable',
        error: fishSpeech.getStatus().last_error || 'Fish Speech S2 local server is not reachable.',
        setup: 'Start the local Fish Speech server on http://127.0.0.1:8080, then retry.',
        fallback: cfg.fishSpeech?.localFallback ? 'local_os_voice' : 'disabled',
      });
    }
    try {
      const audioBuf = await fishSpeech.synthesize(text.trim(), {
        ...(cfg.fishSpeech || {}),
        ...(persona.fishSpeech || {}),
      });
      const artifact = fishSpeech.saveArtifact(audioBuf, cfg.fishSpeech || {});
      res.setHeader('Content-Type', contentTypeFor(cfg.fishSpeech?.format || 'wav'));
      res.setHeader('Content-Length', audioBuf.length);
      res.setHeader('X-Voice-Provider', 'fish_speech_s2_local');
      res.setHeader('X-Voice-Artifact-Id', artifact.id);
      res.setHeader('X-Voice-Artifact-Url', artifact.url);
      return res.send(audioBuf);
    } catch (err) {
      return res.status(500).json({ ok: false, provider: 'fish_speech', error: String(err.message || err) });
    }
  }

  if (selectedProvider === 'local') {
    return res.status(501).json({
      ok: false,
      provider: 'local',
      status: 'fallback',
      error: 'Local OS voice fallback can play on the server, but cannot return browser-playable synthesized audio.',
      setup: 'Use browser speech fallback on the client, or verify the bundled Default Human Voice package.',
    });
  }

  if (!personaplex.isAvailable()) {
    return res.status(503).json({
      ok: false,
      provider: 'personaplex',
      status: 'not_configured',
      error: 'Nvidia PersonaPlex is not configured. Set NVIDIA_API_KEY, or use provider voice_core_local for bundled local CPU voice.',
    });
  }
  try {
    const audioBuf = await personaplex.synthesize(text.trim(), persona);
    res.setHeader('Content-Type', 'audio/wav');
    res.setHeader('Content-Length', audioBuf.length);
    res.send(audioBuf);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

function contentTypeFor(format) {
  if (format === 'mp3') return 'audio/mpeg';
  if (format === 'opus') return 'audio/ogg';
  if (format === 'pcm') return 'application/octet-stream';
  return 'audio/wav';
}

// GET /api/voice/status
router.get('/status', async (_req, res) => {
  const cfg = voiceManager.getConfig();
  fishSpeech.configure(cfg.fishSpeech || {});
  await fishSpeech.checkAvailability();
  const runtime = await getVoiceRuntimeStatus(cfg);
  res.json({
    ok: true,
    provider: cfg.provider || 'voice_core_local',
    mode: voiceManager.getMode(),
    enabled: Boolean(cfg.enabled),
    engine: voiceManager.getEngineStatus(),
    fish_speech: fishSpeech.getStatus(),
    runtime,
    personaplex: {
      available: personaplex.isAvailable(),
      configured: Boolean(process.env.NVIDIA_API_KEY || process.env.NVIDIA_PERSONAPLEX_KEY),
      model: 'nvidia/personaplex-tts-v1',
    },
  });
});

// GET /api/voice/fish-speech/status
router.get('/fish-speech/status', async (_req, res) => {
  const cfg = voiceManager.getConfig();
  fishSpeech.configure(cfg.fishSpeech || {});
  await fishSpeech.checkAvailability();
  res.json(fishSpeech.getStatus());
});

// POST /api/voice/fish-speech/test
router.post('/fish-speech/test', async (req, res) => {
  const cfg = voiceManager.getConfig();
  fishSpeech.configure({ ...(cfg.fishSpeech || {}), ...(req.body?.fishSpeech || {}) });
  const available = await fishSpeech.checkAvailability();
  if (!available) {
    return res.status(503).json({
      ok: false,
      provider: 'fish_speech',
      status: 'unavailable',
      error: fishSpeech.getStatus().last_error,
      setup: 'Start the local Fish Speech server on http://127.0.0.1:8080.',
    });
  }
  try {
    const text = String(req.body?.text || 'Fish Speech S2 local voice test.').slice(0, 500);
    const audioBuf = await fishSpeech.synthesize(text, cfg.fishSpeech || {});
    const artifact = fishSpeech.saveArtifact(audioBuf, cfg.fishSpeech || {});
    res.json({ ok: true, provider: 'fish_speech', artifact, status: fishSpeech.getStatus() });
  } catch (err) {
    res.status(500).json({ ok: false, provider: 'fish_speech', error: String(err.message || err) });
  }
});

// GET /api/voice/personaplex/status
router.get('/personaplex/status', async (_req, res) => {
  const available = await personaplex.checkAvailability();
  res.json({
    available,
    configured: Boolean(process.env.NVIDIA_API_KEY || process.env.NVIDIA_PERSONAPLEX_KEY),
    model: 'nvidia/personaplex-tts-v1',
    tones: Object.keys(personaplex.TONE_STYLE_MAP),
    genders: Object.keys(personaplex.GENDER_VOICE_MAP),
    defaults: personaplex.DEFAULT_PERSONA,
  });
});

module.exports = router;

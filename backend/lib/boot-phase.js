'use strict';

/**
 * boot-phase — validate an inbound UI boot-phase report (desktop F2).
 *
 * The frontend reports its boot progress (e.g. 'react-rendered', 'auth', 'ready') so
 * the desktop shell knows the UI mounted, even under Tauri's remote-origin webview
 * where the Electron preload bridge does not exist. The report arrives as untrusted
 * HTTP input, so it is validated strictly here: fixed types, length caps, safe charset.
 * The result is stored as data and logged only, never executed or rendered as HTML.
 */

const PHASE_RE = /^[A-Za-z0-9 :._-]{1,64}$/;
// Strip C0 controls + DEL (incl. CR/LF) so a detail string can't inject log lines.
const CONTROL_CHARS = new RegExp('[\\x00-\\x1f\\x7f]', 'g');
const MAX_DETAIL = 200;

function validateBootPhase(body) {
  if (!body || typeof body !== 'object') return { ok: false, error: 'body must be an object' };
  const phase = typeof body.phase === 'string' ? body.phase.trim() : '';
  if (!PHASE_RE.test(phase)) return { ok: false, error: 'invalid or missing phase' };
  let detail = null;
  if (body.detail != null) {
    if (typeof body.detail !== 'string') return { ok: false, error: 'detail must be a string' };
    detail = body.detail.replace(CONTROL_CHARS, ' ').trim().slice(0, MAX_DETAIL) || null;
  }
  return { ok: true, value: { phase, detail } };
}

module.exports = { validateBootPhase, PHASE_RE, MAX_DETAIL };

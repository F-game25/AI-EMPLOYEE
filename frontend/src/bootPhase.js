// Boot handshake — report UI boot phases to the shell across every runtime:
//   1. in-page CustomEvent ('nx:boot-phase') for any browser listeners
//   2. Electron preload bridge (window.ai.notifyUiBootPhase) when present
//   3. HTTP POST /api/boot/phase — the transport that works under Tauri's
//      remote-origin webview, where no Electron preload bridge exists (desktop F2)
// Best-effort and non-blocking: boot must never wait on or fail because of this.
export function reportBootPhase(phase, message, extra = {}) {
  const payload = { phase, message, ...extra, ts: Date.now() };
  try { window.dispatchEvent(new CustomEvent('nx:boot-phase', { detail: payload })); } catch { /* pre-DOM */ }
  try { window.ai?.notifyUiBootPhase?.(payload); } catch { /* not in Electron */ }
  try {
    fetch('/api/boot/phase', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase, detail: message }),
      keepalive: true,
    }).catch(() => { /* shell not up yet — best-effort */ });
  } catch { /* fetch unavailable — best-effort */ }
  return payload;
}

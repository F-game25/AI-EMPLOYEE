'use strict';

/**
 * Conversations JSONL persistence helper.
 *
 * Manages state/conversations.jsonl — one JSON record per line.
 * Each record: { id, timestamp, summary, message_count, tags }
 *
 * Import this module anywhere in the backend to append or read conversations.
 * Example (chat/task pipeline):
 *   const { appendConversation } = require('./conversations');
 *   appendConversation({ summary: 'User asked about leads', message_count: 4, tags: ['sales'] });
 */

const fs = require('fs');
const os = require('os');
const path = require('path');

const STATE_DIR = path.resolve(
  process.env.STATE_DIR
    || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'), 'state'),
);
const CONV_FILE = path.join(STATE_DIR, 'conversations.jsonl');

function _ensureDir() {
  try { fs.mkdirSync(STATE_DIR, { recursive: true }); } catch {}
}

/**
 * Read all conversation entries from conversations.jsonl.
 * Returns an array of parsed objects; malformed lines are skipped silently.
 */
function readConversations() {
  try {
    if (!fs.existsSync(CONV_FILE)) return [];
    return fs.readFileSync(CONV_FILE, 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((line) => { try { return JSON.parse(line); } catch { return null; } })
      .filter(Boolean);
  } catch { return []; }
}

/**
 * Append a conversation entry to conversations.jsonl.
 * Preserves full message content when provided so history shows the real exchange,
 * not just a summary. Backward compatible — legacy fields stay, new fields are optional.
 * @param {{ id?, timestamp?, summary?, message_count?, tags?, user_message?, assistant_message?, model?, session_id?, tenant_id? }} entry
 * @returns {object} the normalised record that was written, or null on error
 */
function appendConversation(entry) {
  try {
    _ensureDir();
    const record = {
      id: entry.id || `conv-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: entry.timestamp || new Date().toISOString(),
      summary: String(entry.summary || entry.user_message || '').slice(0, 500),
      message_count: Math.max(0, Number(entry.message_count) || 0),
      tags: Array.isArray(entry.tags) ? entry.tags.slice(0, 20) : [],
    };
    // Full content (optional) — capped to keep the JSONL line bounded.
    // assistant_message may be a string or a structured reply object; extract text.
    const _text = (v) => {
      if (v == null) return '';
      if (typeof v === 'string') return v;
      return String(v.reply || v.message || v.content || v.answer || JSON.stringify(v));
    };
    if (entry.user_message != null) record.user_message = _text(entry.user_message).slice(0, 8000);
    if (entry.assistant_message != null) record.assistant_message = _text(entry.assistant_message).slice(0, 8000);
    if (entry.model) record.model = String(entry.model).slice(0, 80);
    if (entry.session_id) record.session_id = String(entry.session_id).slice(0, 120);
    if (entry.tenant_id) record.tenant_id = String(entry.tenant_id).slice(0, 120);
    fs.appendFileSync(CONV_FILE, JSON.stringify(record) + '\n', 'utf8');
    return record;
  } catch { return null; }
}

/**
 * Delete a conversation entry by id.
 * Rewrites the file atomically.
 * @returns {boolean} true if the entry was found and removed
 */
function deleteConversation(id) {
  try {
    const all = readConversations();
    const filtered = all.filter((c) => c.id !== id);
    if (filtered.length === all.length) return false;
    _ensureDir();
    const tmp = CONV_FILE + '.tmp';
    const content = filtered.map((c) => JSON.stringify(c)).join('\n') + (filtered.length ? '\n' : '');
    fs.writeFileSync(tmp, content, 'utf8');
    fs.renameSync(tmp, CONV_FILE);
    return true;
  } catch { return false; }
}

module.exports = { readConversations, appendConversation, deleteConversation, CONV_FILE };

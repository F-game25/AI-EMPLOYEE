'use strict';

/**
 * routing.js — Shared subsystem routing logic.
 *
 * Determines which subsystem a chat message targets based on keywords.
 * Used by both server.js (WebSocket) and orchestrator/index.js (REST).
 *
 * Also classifies agent *category* so the orchestrator can prefer
 * agents whose specialty matches the user's intent.
 */

const NN_PATTERN = /brain|neural|nn|learn|network|decision|confidence|loss/;
const MEMORY_PATTERN = /memory|remember|know|entity|fact|store/;
const DOCTOR_PATTERN = /doctor|health|check|diagnos|status|grade|score/;

// Category keyword patterns — maps user intent to agent_capabilities categories
const CATEGORY_PATTERNS = [
  { category: 'sales', pattern: /\b(sales?|leads?|prospect|crm|outreach|cold.?call|pipeline|deal|closing|revenue|upsell)\b/ },
  { category: 'marketing', pattern: /\b(marketing|campaign|ads?|advertis|brand|promo|funnel|newsletter|email.?market)\b/ },
  { category: 'content', pattern: /\b(content|blog|article|write|writing|seo|copy|copywriting|editorial)\b/ },
  { category: 'analytics', pattern: /\b(analy[sz]|data|report|metric|dashboard|insight|kpi|chart|statistic)\b/ },
  { category: 'research', pattern: /\b(research|investigate|study|survey|competitive|market.?research|intel)\b/ },
  { category: 'finance', pattern: /\b(financ|budget|accounting|invoice|cost|expense|profit|margin|tax)\b/ },
  { category: 'engineering', pattern: /\b(engineer|code|develop|program|build|deploy|api|backend|frontend|debug|refactor)\b/ },
  { category: 'social', pattern: /\b(social|twitter|linkedin|instagram|tiktok|post|engage|follower|community)\b/ },
  { category: 'support', pattern: /\b(support|customer|ticket|help.?desk|issue|complain|assist|resolve)\b/ },
  { category: 'design', pattern: /\b(design|ui|ux|wireframe|mockup|figma|layout|visual|graphic)\b/ },
  { category: 'strategy', pattern: /\b(strateg|plan|roadmap|vision|objective|goal|initiative|priorit)\b/ },
  { category: 'trading', pattern: /\b(trad(e|ing)|stock|crypto|bitcoin|eth|token|swap|defi|portfolio)\b/ },
  { category: 'ecommerce', pattern: /\b(ecommerce|e-commerce|shop|store|product|inventory|order|cart|checkout)\b/ },
  { category: 'coordination', pattern: /\b(coordinat|orchestrat|assign|delegate|workflow|automat)\b/ },
];

/**
 * Classify a chat message into a subsystem target.
 * @param {string} message
 * @returns {'nn'|'memory'|'doctor'|null}
 */
function classifyMessage(message) {
  const msg = message.toLowerCase();
  if (NN_PATTERN.test(msg)) return 'nn';
  if (MEMORY_PATTERN.test(msg)) return 'memory';
  if (DOCTOR_PATTERN.test(msg)) return 'doctor';
  return null;
}

/**
 * Classify a chat message into an agent category for smarter routing.
 * Returns the best-matching category or null if no strong match.
 * @param {string} message
 * @returns {string|null}
 */
function classifyCategory(message) {
  const msg = message.toLowerCase();
  for (const { category, pattern } of CATEGORY_PATTERNS) {
    if (pattern.test(msg)) return category;
  }
  return null;
}

module.exports = { classifyMessage, classifyCategory };

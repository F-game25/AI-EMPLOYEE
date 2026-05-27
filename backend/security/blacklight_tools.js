'use strict';

const crypto = require('crypto');
const net = require('net');
const { domainToASCII } = require('url');

const CATEGORIES = {
  osint: 'OSINT / Reconnaissance',
  defensive_review: 'Defensive Security Review',
  phishing: 'Phishing Defense',
  special: 'Special Functions',
};

const MODES = {
  safe: 'safe',
  passive: 'passive_network',
  simulation: 'defensive_simulation',
  blocked: 'blocked',
};

const RAW_TOOLS = [
  ['username-search', 'Username Search', 'osint', MODES.passive, ['username', 'handle', 'account'], 'Prepare approved public-profile search queries for a username.'],
  ['email-lookup', 'Email Lookup', 'osint', MODES.safe, ['email', 'domain', 'mx'], 'Validate and profile an email address without sending traffic.'],
  ['phone-number-lookup', 'Phone Number Lookup', 'osint', MODES.safe, ['phone', 'number'], 'Normalize and classify a phone number locally.'],
  ['ip-address-lookup', 'IP Address Lookup', 'osint', MODES.safe, ['ip', 'address', 'geo'], 'Classify IP address type and local risk signals.'],
  ['whois-lookup', 'WHOIS Lookup', 'osint', MODES.passive, ['whois', 'domain'], 'Requires online policy approval; no lookup runs in offline mode.'],
  ['dns-lookup', 'DNS Lookup', 'osint', MODES.passive, ['dns', 'record'], 'Requires online policy approval; use for owned or authorized domains.'],
  ['subdomain-enumeration', 'Subdomain Enumeration', 'osint', MODES.passive, ['subdomain', 'asset'], 'Passive inventory only; brute force is separated and gated.'],
  ['http-headers-analysis', 'HTTP Headers Analysis', 'osint', MODES.safe, ['headers', 'security'], 'Analyze pasted HTTP response headers.'],
  ['website-technology-detection', 'Website Technology Detection', 'osint', MODES.passive, ['technology', 'fingerprint'], 'Passive technology notes; online probing requires approval.'],
  ['port-scanner', 'Port Scanner', 'osint', MODES.blocked, ['port', 'scan'], 'Active port scanning is not available from this UI.'],
  ['reverse-dns-lookup', 'Reverse DNS Lookup', 'osint', MODES.passive, ['reverse', 'dns'], 'Requires online policy approval.'],
  ['mac-address-lookup', 'MAC Address Lookup', 'osint', MODES.safe, ['mac', 'vendor'], 'Normalize MAC address and identify local/multicast flags.'],
  ['email-breach-check', 'Email Breach Check', 'osint', MODES.passive, ['breach', 'email'], 'External breach checks require explicit online/API approval.'],
  ['metadata-extractor', 'Metadata Extractor', 'osint', MODES.safe, ['metadata', 'exif', 'file'], 'Checklist for local metadata extraction; no file upload is required here.'],
  ['social-media-scraper', 'Social Media Scraper', 'osint', MODES.blocked, ['social', 'scrape'], 'Automated scraping is blocked; use approved exports/APIs only.'],
  ['ssl-tls-certificate-info', 'SSL/TLS Certificate Info', 'osint', MODES.passive, ['ssl', 'tls', 'certificate'], 'Certificate retrieval requires online approval.'],
  ['wayback-machine-lookup', 'Wayback Machine Lookup', 'osint', MODES.passive, ['wayback', 'archive'], 'Archive lookups require online approval.'],
  ['robots-sitemap-analyzer', 'Robots.txt & Sitemap Analyzer', 'osint', MODES.passive, ['robots', 'sitemap'], 'Requires online approval unless content is pasted.'],
  ['link-extractor', 'Link Extractor', 'osint', MODES.safe, ['links', 'html'], 'Extract links from pasted HTML/text.'],
  ['google-dorks-generator', 'Google Dorks Generator', 'osint', MODES.simulation, ['dork', 'search'], 'Generates defensive search-intent templates without sensitive payloads.'],
  ['traceroute', 'Traceroute', 'osint', MODES.blocked, ['trace', 'route'], 'Active network tracing is not available from this UI.'],
  ['hash-identifier-lookup', 'Hash Identifier & Lookup', 'osint', MODES.safe, ['hash', 'sha', 'md5'], 'Identify likely hash formats locally.'],
  ['asn-lookup', 'ASN Lookup', 'osint', MODES.passive, ['asn', 'network'], 'Requires online approval.'],
  ['website-screenshot', 'Website Screenshot', 'osint', MODES.passive, ['screenshot', 'website'], 'Screenshots require online/browser approval.'],
  ['reverse-image-search', 'Reverse Image Search', 'osint', MODES.passive, ['image', 'reverse'], 'External image search requires approval.'],
  ['paste-code-search', 'Paste / Code Search', 'osint', MODES.passive, ['paste', 'code', 'leak'], 'External code/paste search requires approval.'],
  ['ssl-tls-suite-scanner', 'SSL/TLS Suite Scanner', 'osint', MODES.blocked, ['cipher', 'tls'], 'Active TLS suite scanning is blocked from this UI.'],
  ['favicon-hash-lookup', 'Favicon Hash Lookup', 'osint', MODES.safe, ['favicon', 'hash'], 'Compute a hash from pasted/base64 favicon bytes.'],
  ['security-txt-checker', 'Security.txt Checker', 'osint', MODES.passive, ['security.txt'], 'Requires online approval.'],
  ['cloud-storage-finder', 'Cloud Storage Finder', 'osint', MODES.simulation, ['bucket', 'storage', 'cloud'], 'Generates authorized cloud asset checklist only.'],
  ['js-endpoint-extractor', 'JS Endpoint Extractor', 'osint', MODES.safe, ['javascript', 'endpoint', 'api'], 'Extract likely API paths from pasted JavaScript.'],
  ['waf-cdn-detector', 'WAF / CDN Detector', 'osint', MODES.safe, ['waf', 'cdn'], 'Infer WAF/CDN hints from pasted headers.'],
  ['subdomain-bruteforce', 'Subdomain BruteForce', 'osint', MODES.blocked, ['bruteforce', 'subdomain'], 'Brute force enumeration is blocked.'],
  ['vibe-coded-site-finder', 'Vibe-Coded Site Finder', 'osint', MODES.safe, ['vibe', 'generated', 'site'], 'Checks pasted HTML for common generated-site fingerprints.'],
  ['dmarc-spf-dkim-check', 'DMARC / SPF / DKIM Check', 'osint', MODES.passive, ['dmarc', 'spf', 'dkim'], 'DNS checks require online approval.'],
  ['http-methods-discovery', 'HTTP Methods Discovery', 'osint', MODES.blocked, ['methods', 'options'], 'Active HTTP method probing is blocked.'],
  ['banner-grabbing', 'Banner Grabbing', 'osint', MODES.blocked, ['banner', 'grab'], 'Active banner grabbing is blocked.'],
  ['ping-sweep-host-discovery', 'Ping Sweep / Host Discovery', 'osint', MODES.blocked, ['ping', 'sweep', 'host'], 'Host discovery is blocked.'],
  ['shodan-host-lookup', 'Shodan Host Lookup', 'osint', MODES.passive, ['shodan', 'host'], 'Requires external API approval.'],
  ['cve-search', 'CVE Search', 'osint', MODES.safe, ['cve', 'vulnerability'], 'Extract and format CVE IDs from pasted text.'],
  ['reverse-image-search-extra', 'Reverse Image Search (extra)', 'osint', MODES.passive, ['image', 'reverse'], 'External image search requires approval.'],
  ['sql-injection-tester', 'SQL Injection Tester', 'exploitation', MODES.simulation, ['sql', 'injection'], 'Defensive checklist only; no payload testing.'],
  ['xss-scanner-reflected', 'XSS Scanner (Reflected)', 'exploitation', MODES.simulation, ['xss'], 'Defensive checklist only; no payload testing.'],
  ['directory-file-bruteforcer', 'Directory / File Bruteforcer', 'exploitation', MODES.blocked, ['directory', 'bruteforce'], 'Bruteforcing is blocked.'],
  ['cors-misconfiguration-scanner', 'CORS Misconfiguration Scanner', 'exploitation', MODES.safe, ['cors'], 'Analyze pasted CORS headers.'],
  ['open-redirect-scanner', 'Open Redirect Scanner', 'exploitation', MODES.simulation, ['redirect'], 'Defensive checklist only.'],
  ['lfi-path-traversal-tester', 'LFI / Path Traversal Tester', 'exploitation', MODES.simulation, ['lfi', 'path traversal'], 'Defensive checklist only.'],
  ['subdomain-takeover-check', 'Subdomain Takeover Check', 'exploitation', MODES.passive, ['takeover'], 'Passive authorized checks require online approval.'],
  ['reverse-shell-generator', 'Reverse Shell Generator', 'exploitation', MODES.blocked, ['reverse shell'], 'Blocked: weaponized code generation is not provided.'],
  ['cms-vulnerability-scanner', 'CMS Vulnerability Scanner', 'exploitation', MODES.passive, ['cms'], 'Passive version review requires approval.'],
  ['payload-encoder-decoder', 'Payload Encoder / Decoder', 'exploitation', MODES.safe, ['encode', 'decode', 'base64'], 'Encode/decode benign strings for debugging.'],
  ['crlf-injection-tester', 'CRLF Injection Tester', 'exploitation', MODES.simulation, ['crlf'], 'Defensive checklist only.'],
  ['ssrf-tester', 'SSRF Tester', 'exploitation', MODES.simulation, ['ssrf'], 'Defensive checklist only.'],
  ['jwt-analyzer', 'JWT Analyzer', 'exploitation', MODES.safe, ['jwt', 'token'], 'Decode JWT header/payload and flag common risks.'],
  ['clickjacking-tester', 'Clickjacking Tester', 'exploitation', MODES.safe, ['clickjacking', 'frame'], 'Analyze pasted frame-related headers.'],
  ['xee-tester', 'XEE Tester', 'exploitation', MODES.simulation, ['xee', 'xml'], 'Defensive checklist only.'],
  ['command-injection-tester', 'Command Injection Tester', 'exploitation', MODES.simulation, ['command injection'], 'Defensive checklist only.'],
  ['host-header-injection', 'Host Header Injection', 'exploitation', MODES.simulation, ['host header'], 'Defensive checklist only.'],
  ['insecure-cookie-checker', 'Insecure Cookie Checker', 'exploitation', MODES.safe, ['cookie'], 'Analyze pasted Set-Cookie headers.'],
  ['csrf-token-analyzer', 'CSRF Token Analyzer', 'exploitation', MODES.safe, ['csrf'], 'Review pasted form/request metadata for CSRF controls.'],
  ['prototype-pollution-scanner', 'Prototype Pollution Scanner', 'exploitation', MODES.simulation, ['prototype pollution'], 'Defensive checklist only.'],
  ['supabase-rls-auditor', 'Supabase RLS Auditor', 'exploitation', MODES.safe, ['supabase', 'rls'], 'Review pasted RLS policy text for common gaps.'],

  ['http-flood', 'HTTP Flood (GET/POST)', 'stress', MODES.blocked, ['flood', 'dos', 'ddos'], 'Blocked: traffic generation is not provided.'],
  ['slowloris', 'Slowloris', 'stress', MODES.blocked, ['slowloris'], 'Blocked: traffic generation is not provided.'],
  ['slow-post-rudy', 'Slow POST (R.U.D.Y.)', 'stress', MODES.blocked, ['rudy', 'slow post'], 'Blocked: traffic generation is not provided.'],
  ['tcp-connection-flood', 'TCP Connection Flood', 'stress', MODES.blocked, ['tcp flood'], 'Blocked: traffic generation is not provided.'],
  ['udp-flood', 'UDP Flood', 'stress', MODES.blocked, ['udp flood'], 'Blocked: traffic generation is not provided.'],
  ['icmp-ping-flood', 'ICMP Ping Flood', 'stress', MODES.blocked, ['icmp', 'ping flood'], 'Blocked: traffic generation is not provided.'],
  ['http-slow-read', 'HTTP Slow Read', 'stress', MODES.blocked, ['slow read'], 'Blocked: traffic generation is not provided.'],
  ['goldeneye-keep-alive-flood', 'GoldenEye (Keep-Alive Flood)', 'stress', MODES.blocked, ['goldeneye', 'keep alive'], 'Blocked: traffic generation is not provided.'],
  ['dns-flood', 'DNS Flood', 'stress', MODES.blocked, ['dns flood'], 'Blocked: traffic generation is not provided.'],
  ['websocket-flood', 'WebSocket Flood', 'stress', MODES.blocked, ['websocket flood'], 'Blocked: traffic generation is not provided.'],
  ['cors-header-review', 'CORS Header Review', 'defensive_review', MODES.safe, ['cors'], 'Analyze pasted CORS headers for defensive configuration gaps.'],
  ['jwt-analyzer', 'JWT Analyzer', 'defensive_review', MODES.safe, ['jwt', 'token'], 'Decode JWT header/payload and flag common defensive risks.'],
  ['clickjacking-header-review', 'Clickjacking Header Review', 'defensive_review', MODES.safe, ['clickjacking', 'frame'], 'Analyze pasted frame-related headers.'],
  ['cookie-security-review', 'Cookie Security Review', 'defensive_review', MODES.safe, ['cookie'], 'Analyze pasted Set-Cookie headers.'],
  ['csrf-control-review', 'CSRF Control Review', 'defensive_review', MODES.safe, ['csrf'], 'Review pasted form/request metadata for CSRF controls.'],
  ['supabase-rls-policy-review', 'Supabase RLS Policy Review', 'defensive_review', MODES.safe, ['supabase', 'rls'], 'Review pasted RLS policy text for common defensive gaps.'],

  ['homoglyph-domain-generator', 'Homoglyph Domain Generator', 'phishing', MODES.simulation, ['homoglyph', 'domain'], 'Defensive brand-risk variants only.'],
  ['phishing-url-analyzer', 'Phishing URL Analyzer', 'phishing', MODES.safe, ['phishing', 'url'], 'Analyze URL structure and suspicious indicators.'],
  ['email-spoofing-checker', 'Email Spoofing Checker', 'phishing', MODES.passive, ['spoof', 'email'], 'DNS-based checks require online approval.'],
  ['typosquatting-generator', 'Typosquatting Generator', 'phishing', MODES.simulation, ['typo', 'brand'], 'Defensive brand monitoring variants only.'],
  ['email-header-analyzer', 'Email Header Analyzer', 'phishing', MODES.safe, ['email header'], 'Analyze pasted email headers for authentication signals.'],
  ['phishing-kit-detector', 'Phishing Kit Detector', 'phishing', MODES.safe, ['kit', 'phishing'], 'Review pasted file names/HTML for phishing-kit indicators.'],
  ['phishing-campaign-planner', 'Phishing Campaign Planner', 'phishing', MODES.simulation, ['campaign', 'awareness'], 'Security-awareness simulation plan only; no credential collection.'],
  ['credential-harvester-gen', 'Credential Harvester Gen', 'phishing', MODES.blocked, ['credential', 'harvest'], 'Blocked: credential collection tooling is not provided.'],
  ['url-obfuscator', 'URL Obfuscator', 'phishing', MODES.blocked, ['obfuscate', 'url'], 'Blocked: URL disguise tooling is not provided.'],
  ['idn-homograph-attack-gen', 'IDN Homograph Attack Gen', 'phishing', MODES.blocked, ['idn', 'homograph'], 'Blocked: attack generation is not provided.'],
  ['ai-search', 'AI Search', 'special', MODES.safe, ['natural language', 'find tool'], 'Natural language tool routing over the safe catalog.'],
  ['stealth-mode-config', 'Stealth Mode Config', 'special', MODES.simulation, ['stealth', 'privacy'], 'Privacy-safe scan profile; no evasion or bypass behavior.'],
  ['botnet-coordinated-ddos', 'Botnet - Coordinated DDoS', 'special', MODES.blocked, ['botnet', 'ddos'], 'Blocked: coordinated DDoS is not provided.'],
  ['botnet-zombies-world-map', 'Botnet Zombies World Map', 'special', MODES.blocked, ['botnet', 'map'], 'Blocked: botnet telemetry/control is not provided.'],
];

const TOOL_CATALOG = RAW_TOOLS.map(([id, name, category, mode, keywords, description]) => ({
  id,
  name,
  category,
  categoryLabel: CATEGORIES[category] || category,
  mode,
  keywords,
  description,
  enabled: mode === MODES.safe || mode === MODES.simulation,
  requiresApproval: mode === MODES.passive || mode === MODES.simulation,
  blockedReason: mode === MODES.blocked ? description : null,
}));

function summarizeCatalog() {
  const counts = {};
  for (const tool of TOOL_CATALOG) {
    counts[tool.category] = counts[tool.category] || { total: 0, safe: 0, passive: 0, simulation: 0, blocked: 0 };
    counts[tool.category].total += 1;
    if (tool.mode === MODES.safe) counts[tool.category].safe += 1;
    if (tool.mode === MODES.passive) counts[tool.category].passive += 1;
    if (tool.mode === MODES.simulation) counts[tool.category].simulation += 1;
    if (tool.mode === MODES.blocked) counts[tool.category].blocked += 1;
  }
  return counts;
}

function scoreTool(tool, query) {
  const q = String(query || '').toLowerCase();
  if (!q) return 0;
  let score = 0;
  if (tool.name.toLowerCase().includes(q)) score += 8;
  if (tool.id.includes(q.replace(/\s+/g, '-'))) score += 6;
  for (const keyword of tool.keywords || []) {
    if (q.includes(keyword.toLowerCase()) || keyword.toLowerCase().includes(q)) score += 3;
  }
  for (const part of q.split(/\s+/).filter(Boolean)) {
    if (tool.name.toLowerCase().includes(part)) score += 1;
    if ((tool.description || '').toLowerCase().includes(part)) score += 1;
  }
  return score;
}

function searchTools(query, limit = 8) {
  return TOOL_CATALOG
    .map(tool => ({ ...tool, score: scoreTool(tool, query) }))
    .filter(tool => tool.score > 0)
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
    .slice(0, limit);
}

function getTool(id) {
  return TOOL_CATALOG.find(tool => tool.id === id);
}

function parseHeaders(input) {
  const headers = {};
  for (const line of String(input || '').split(/\r?\n/)) {
    const idx = line.indexOf(':');
    if (idx <= 0) continue;
    headers[line.slice(0, idx).trim().toLowerCase()] = line.slice(idx + 1).trim();
  }
  return headers;
}

function analyzeEmail(input) {
  const email = String(input || '').trim();
  const match = email.match(/^([^@\s]+)@([^@\s]+\.[^@\s]+)$/);
  const domain = match ? match[2].toLowerCase() : '';
  return {
    valid_format: !!match,
    local_part_length: match ? match[1].length : 0,
    domain,
    normalized: match ? `${match[1]}@${domain}` : '',
    notes: match ? ['Format is syntactically valid.', 'DNS/breach checks require online policy approval.'] : ['Email format is invalid.'],
  };
}

function analyzePhone(input) {
  const raw = String(input || '');
  const digits = raw.replace(/\D/g, '');
  return {
    digits,
    possible_e164: digits.length >= 8 && digits.length <= 15,
    has_country_prefix: raw.trim().startsWith('+'),
    notes: ['Local normalization only. Carrier/owner lookup requires an approved provider.'],
  };
}

function analyzeIp(input) {
  const ip = String(input || '').trim();
  const version = net.isIP(ip);
  const private4 = /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.|169\.254\.)/.test(ip);
  const local6 = ip === '::1' || ip.toLowerCase().startsWith('fe80:') || ip.toLowerCase().startsWith('fc') || ip.toLowerCase().startsWith('fd');
  return {
    valid: version !== 0,
    version: version || null,
    scope: private4 || local6 ? 'private_or_local' : version ? 'public_or_reserved' : 'invalid',
    notes: version ? ['Geolocation/ASN lookup requires online policy approval.'] : ['Input is not a valid IP address.'],
  };
}

function analyzeMac(input) {
  const raw = String(input || '').trim();
  const hex = raw.replace(/[^a-fA-F0-9]/g, '').toUpperCase();
  const valid = hex.length === 12;
  const firstOctet = valid ? parseInt(hex.slice(0, 2), 16) : 0;
  return {
    normalized: valid ? hex.match(/.{2}/g).join(':') : '',
    valid,
    multicast: valid ? !!(firstOctet & 1) : false,
    locally_administered: valid ? !!(firstOctet & 2) : false,
  };
}

function analyzeHash(input) {
  const value = String(input || '').trim();
  const hex = /^[a-fA-F0-9]+$/.test(value);
  const lengths = { 32: 'MD5/NTLM candidate', 40: 'SHA-1 candidate', 56: 'SHA-224 candidate', 64: 'SHA-256 candidate', 96: 'SHA-384 candidate', 128: 'SHA-512 candidate' };
  return {
    length: value.length,
    hex,
    likely_type: hex ? (lengths[value.length] || 'Unknown hex digest length') : 'Not a plain hex digest',
  };
}

function analyzeJwt(input) {
  const token = String(input || '').trim();
  const parts = token.split('.');
  const decode = (part) => {
    try {
      return JSON.parse(Buffer.from(part.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8'));
    } catch {
      return null;
    }
  };
  const header = parts.length >= 2 ? decode(parts[0]) : null;
  const payload = parts.length >= 2 ? decode(parts[1]) : null;
  const warnings = [];
  if (!header || !payload) warnings.push('Token is not a readable JWT.');
  if (header?.alg === 'none') warnings.push('alg=none is unsafe.');
  if (payload?.exp && payload.exp * 1000 < Date.now()) warnings.push('Token is expired.');
  if (!payload?.exp) warnings.push('No exp claim found.');
  return { readable: !!(header && payload), header, payload, warnings };
}

function analyzeUrl(input) {
  try {
    const parsed = new URL(String(input || '').trim());
    const asciiHost = domainToASCII(parsed.hostname);
    const warnings = [];
    if (parsed.protocol !== 'https:') warnings.push('URL is not HTTPS.');
    if (parsed.username || parsed.password) warnings.push('URL contains embedded credentials.');
    if (parsed.hostname !== asciiHost) warnings.push('IDN/punycode hostname detected.');
    if (parsed.hostname.split('.').length > 4) warnings.push('Unusually deep subdomain chain.');
    if (/%[0-9a-f]{2}/i.test(parsed.href)) warnings.push('URL contains percent-encoded characters.');
    return { valid: true, protocol: parsed.protocol, hostname: parsed.hostname, ascii_hostname: asciiHost, path: parsed.pathname, warnings };
  } catch {
    return { valid: false, warnings: ['Input is not a valid URL.'] };
  }
}

function analyzeHeaders(input) {
  const h = parseHeaders(input);
  const findings = [];
  if (!h['content-security-policy']) findings.push('Missing Content-Security-Policy.');
  if (!h['strict-transport-security']) findings.push('Missing Strict-Transport-Security.');
  if (!h['x-frame-options'] && !String(h['content-security-policy'] || '').includes('frame-ancestors')) findings.push('Missing clickjacking protection.');
  if (!h['x-content-type-options']) findings.push('Missing X-Content-Type-Options.');
  const server = h.server || '';
  if (server) findings.push(`Server header is exposed: ${server}`);
  return { headers: h, findings, posture: findings.length ? 'review' : 'strong' };
}

function extractLinks(input) {
  const text = String(input || '');
  const links = [...text.matchAll(/https?:\/\/[^\s"'<>]+/gi)].map(match => match[0]);
  const hrefs = [...text.matchAll(/href=["']([^"']+)["']/gi)].map(match => match[1]);
  return { links: [...new Set([...links, ...hrefs])].slice(0, 100) };
}

function extractJsEndpoints(input) {
  const text = String(input || '');
  const matches = [...text.matchAll(/["'`](\/api\/[^"'`\s]+|\/[a-z0-9_/-]+\?[^\s"'`]+)["'`]/gi)].map(match => match[1]);
  return { endpoints: [...new Set(matches)].slice(0, 100) };
}

function encodeDecode(input) {
  const text = String(input || '');
  let base64Decoded = null;
  try { base64Decoded = Buffer.from(text, 'base64').toString('utf8'); } catch {}
  return {
    base64: Buffer.from(text, 'utf8').toString('base64'),
    url_encoded: encodeURIComponent(text),
    sha256: crypto.createHash('sha256').update(text).digest('hex'),
    base64_decoded_preview: base64Decoded && /^[\x09\x0A\x0D\x20-\x7E]*$/.test(base64Decoded) ? base64Decoded.slice(0, 500) : null,
  };
}

function defensiveChecklist(tool) {
  return {
    checklist: [
      'Confirm written authorization and target ownership.',
      'Use staging or a scoped test environment.',
      'Prefer passive review, logs, and configuration inspection first.',
      'Record approval, time window, rate limits, and rollback contacts.',
      'Run findings through remediation and retest workflow.',
    ],
    message: `${tool.name} is available only as a defensive checklist/simulation in this system.`,
  };
}

function blockedResult(tool) {
  return {
    blocked: true,
    reason: tool.blockedReason || 'This capability is blocked by policy.',
    safe_alternatives: [
      'Use defensive configuration review.',
      'Run approved vulnerability scans with scoped enterprise tooling outside this launcher.',
      'Create a HITL approval request with scope, owner, and rollback plan.',
    ],
  };
}

// ── Passive network handlers ───────────────────────────────────────────────

async function handleDnsLookup(input) {
  const dns = require('dns').promises;
  const domain = String(input || '').trim();
  const [a, aaaa, mx, ns, txt] = await Promise.allSettled([
    dns.resolve4(domain),
    dns.resolve6(domain),
    dns.resolveMx(domain),
    dns.resolveNs(domain),
    dns.resolveTxt(domain),
  ]);
  return {
    domain,
    A: a.status === 'fulfilled' ? a.value : [],
    AAAA: aaaa.status === 'fulfilled' ? aaaa.value : [],
    MX: mx.status === 'fulfilled' ? mx.value : [],
    NS: ns.status === 'fulfilled' ? ns.value : [],
    TXT: txt.status === 'fulfilled' ? txt.value.flat() : [],
  };
}

async function handleReverseDns(input) {
  const dns = require('dns').promises;
  const ip = String(input || '').trim();
  const hostnames = await dns.reverse(ip).catch(() => []);
  return { ip, hostnames };
}

async function handleDmarcCheck(input) {
  const dns = require('dns').promises;
  const domain = String(input || '').trim().replace(/^@/, '');
  const [spf, dmarc, dkim] = await Promise.allSettled([
    dns.resolveTxt(domain).then(r => r.flat().filter(s => s.startsWith('v=spf1'))),
    dns.resolveTxt('_dmarc.' + domain).then(r => r.flat()),
    dns.resolveTxt('default._domainkey.' + domain).then(r => r.flat()),
  ]);
  return {
    domain,
    spf: spf.status === 'fulfilled' ? spf.value : [],
    dmarc: dmarc.status === 'fulfilled' ? dmarc.value : [],
    dkim: dkim.status === 'fulfilled' ? dkim.value : [],
    has_spf: spf.status === 'fulfilled' && spf.value.length > 0,
    has_dmarc: dmarc.status === 'fulfilled' && dmarc.value.length > 0,
  };
}

async function handleSubdomainEnum(input) {
  const dns = require('dns').promises;
  const domain = String(input || '').trim();
  const common = ['www','mail','ftp','api','dev','staging','test','admin','blog','shop','cdn','ns1','ns2','smtp','vpn','remote','app','portal','auth','m'];
  const results = await Promise.allSettled(common.map(sub =>
    dns.resolve4(sub + '.' + domain).then(ips => ({ subdomain: sub + '.' + domain, ips }))
  ));
  return {
    domain,
    found: results.filter(r => r.status === 'fulfilled').map(r => r.value),
    checked: common.length,
  };
}

function handleSslCert(input) {
  return new Promise((resolve) => {
    const tls = require('tls');
    let host = String(input || '').trim().replace(/^https?:\/\//, '').split('/')[0];
    const port = host.includes(':') ? parseInt(host.split(':')[1]) : 443;
    host = host.split(':')[0];
    const socket = tls.connect({ host, port, rejectUnauthorized: true, servername: host }, () => {
      const cert = socket.getPeerCertificate(true);
      socket.destroy();
      resolve({
        host, port,
        subject: cert.subject,
        issuer: cert.issuer,
        valid_from: cert.valid_from,
        valid_to: cert.valid_to,
        serial: cert.serialNumber,
        san: cert.subjectaltname,
        fingerprint: cert.fingerprint256,
        expired: new Date(cert.valid_to) < new Date(),
      });
    });
    socket.on('error', e => resolve({ host, error: e.message }));
    socket.setTimeout(8000, () => { socket.destroy(); resolve({ host, error: 'timeout' }); });
  });
}

async function handleWhois(input) {
  const domain = String(input || '').trim();
  try {
    const res = await fetch(`https://rdap.org/domain/${domain}`, {
      headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return { domain, note: 'RDAP lookup failed', status: res.status };
    const data = await res.json();
    return {
      domain,
      handle: data.handle,
      ldhName: data.ldhName,
      status: data.status,
      registrar: data.entities?.find(e => e.roles?.includes('registrar'))?.vcardArray?.[1]?.find(v => v[0] === 'fn')?.[3] || 'unknown',
      nameservers: data.nameservers?.map(n => n.ldhName) || [],
      events: data.events?.map(e => ({ action: e.eventAction, date: e.eventDate })) || [],
    };
  } catch (e) { return { domain, error: e.message }; }
}

async function handleWayback(input) {
  const url = String(input || '').trim();
  try {
    const res = await fetch(`https://archive.org/wayback/available?url=${encodeURIComponent(url)}`, {
      signal: AbortSignal.timeout(8000),
    });
    const data = await res.json();
    return {
      url,
      available: !!data.archived_snapshots?.closest?.available,
      closest: data.archived_snapshots?.closest || null,
      cdx_link: `https://web.archive.org/cdx/search/cdx?url=${encodeURIComponent(url)}&output=json&limit=5`,
    };
  } catch (e) { return { url, error: e.message }; }
}

async function handleRobotsSitemap(input) {
  let base = String(input || '').trim();
  if (!base.startsWith('http')) base = 'https://' + base;
  base = base.replace(/\/$/, '');
  const [robots, sitemap] = await Promise.allSettled([
    fetch(base + '/robots.txt', { signal: AbortSignal.timeout(6000) }).then(r => r.text()),
    fetch(base + '/sitemap.xml', { signal: AbortSignal.timeout(6000) }).then(r => r.text()),
  ]);
  return {
    url: base,
    robots_txt: robots.status === 'fulfilled' ? robots.value.slice(0, 2000) : null,
    sitemap_xml: sitemap.status === 'fulfilled' ? sitemap.value.slice(0, 2000) : null,
    robots_error: robots.status === 'rejected' ? robots.reason?.message : null,
    sitemap_error: sitemap.status === 'rejected' ? sitemap.reason?.message : null,
  };
}

async function handleSecurityTxt(input) {
  let base = String(input || '').trim();
  if (!base.startsWith('http')) base = 'https://' + base;
  base = base.replace(/\/$/, '');
  const urls = [base + '/.well-known/security.txt', base + '/security.txt'];
  for (const u of urls) {
    try {
      const r = await fetch(u, { signal: AbortSignal.timeout(5000) });
      if (r.ok) {
        const text = await r.text();
        return {
          found: true, url: u, content: text.slice(0, 1000),
          has_contact: text.includes('Contact:'),
          has_expires: text.includes('Expires:'),
          has_encryption: text.includes('Encryption:'),
        };
      }
    } catch {}
  }
  return { found: false, url: base, checked: urls };
}

async function handleAsnLookup(input) {
  const target = String(input || '').trim();
  try {
    const res = await fetch(`https://api.bgpview.io/ip/${encodeURIComponent(target)}`, {
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) throw new Error('BGPView error ' + res.status);
    const data = await res.json();
    const prefixes = data.data?.prefixes || [];
    return {
      target,
      asn: prefixes[0]?.asn?.asn,
      asn_name: prefixes[0]?.asn?.name,
      country: prefixes[0]?.asn?.country_code,
      prefix: prefixes[0]?.prefix,
      description: prefixes[0]?.asn?.description,
    };
  } catch (e) { return { target, error: e.message }; }
}

async function handleTechDetection(input) {
  let url = String(input || '').trim();
  if (!url.startsWith('http')) url = 'https://' + url;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(8000), redirect: 'follow' });
    const headers = Object.fromEntries(res.headers.entries());
    const html = (await res.text()).slice(0, 8000);
    const techs = [];
    if (headers['x-powered-by']) techs.push('X-Powered-By: ' + headers['x-powered-by']);
    if (headers['server']) techs.push('Server: ' + headers['server']);
    if (html.includes('wp-content')) techs.push('WordPress');
    if (html.includes('Drupal')) techs.push('Drupal');
    if (html.includes('__NEXT_DATA__')) techs.push('Next.js');
    if (html.includes('__nuxt')) techs.push('Nuxt.js');
    if (html.includes('react')) techs.push('React');
    if (html.includes('vue')) techs.push('Vue.js');
    if (html.includes('angular')) techs.push('Angular');
    if (html.includes('jquery')) techs.push('jQuery');
    if (html.includes('bootstrap')) techs.push('Bootstrap');
    if (html.includes('shopify')) techs.push('Shopify');
    if (html.includes('wix')) techs.push('Wix');
    return {
      url, technologies: techs,
      headers_sample: { server: headers.server, 'x-powered-by': headers['x-powered-by'], 'content-type': headers['content-type'] },
    };
  } catch (e) { return { url, error: e.message }; }
}

function handleUsernameSearch(input) {
  const username = String(input || '').trim().replace(/^@/, '');
  const platforms = [
    { name: 'GitHub', url: `https://github.com/${username}` },
    { name: 'Twitter/X', url: `https://x.com/${username}` },
    { name: 'LinkedIn', url: `https://www.linkedin.com/in/${username}` },
    { name: 'Instagram', url: `https://instagram.com/${username}` },
    { name: 'Reddit', url: `https://reddit.com/user/${username}` },
    { name: 'TikTok', url: `https://tiktok.com/@${username}` },
    { name: 'YouTube', url: `https://youtube.com/@${username}` },
    { name: 'Twitch', url: `https://twitch.tv/${username}` },
    { name: 'HackerNews', url: `https://news.ycombinator.com/user?id=${username}` },
    { name: 'Medium', url: `https://medium.com/@${username}` },
    { name: 'Dev.to', url: `https://dev.to/${username}` },
    { name: 'GitLab', url: `https://gitlab.com/${username}` },
  ];
  return { username, platforms, note: 'Open each URL to verify existence — no automated check performed.' };
}

async function handleEmailBreach(input) {
  const email = String(input || '').trim();
  const apiKey = process.env.HIBP_API_KEY;
  if (!apiKey) return { email, note: 'Set HIBP_API_KEY env var to enable breach checking. Visit https://haveibeenpwned.com/API/Key to obtain a key.' };
  try {
    const res = await fetch(`https://haveibeenpwned.com/api/v3/breachedaccount/${encodeURIComponent(email)}?truncateResponse=false`, {
      headers: { 'hibp-api-key': apiKey, 'user-agent': 'AI-Employee-OSINT/1.0' },
      signal: AbortSignal.timeout(8000),
    });
    if (res.status === 404) return { email, breached: false, breaches: [] };
    if (!res.ok) return { email, error: 'HIBP API error ' + res.status };
    const data = await res.json();
    return {
      email, breached: true, breach_count: data.length,
      breaches: data.map(b => ({ name: b.Name, date: b.BreachDate, description: b.Description?.slice(0, 200) })),
    };
  } catch (e) { return { email, error: e.message }; }
}

function handlePasteSearch(input) {
  const query = encodeURIComponent(String(input || '').trim());
  return {
    query: decodeURIComponent(query),
    search_links: [
      { name: 'GitHub Search', url: `https://github.com/search?q=${query}&type=code` },
      { name: 'Pastebin (Google)', url: `https://www.google.com/search?q=site:pastebin.com+${query}` },
      { name: 'GreyNoise', url: `https://viz.greynoise.io/query/?gnql=${query}` },
      { name: 'PublicWWW', url: `https://publicwww.com/websites/${query}/` },
    ],
    note: 'Automated paste scanning requires external API keys. Use above links for manual investigation.',
  };
}

async function handleShodan(input) {
  const target = String(input || '').trim();
  const apiKey = process.env.SHODAN_API_KEY;
  if (!apiKey) return { target, note: 'Set SHODAN_API_KEY env var to enable Shodan lookup.', shodan_url: `https://www.shodan.io/host/${target}` };
  try {
    const res = await fetch(`https://api.shodan.io/shodan/host/${encodeURIComponent(target)}?key=${apiKey}`, {
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) return { target, error: 'Shodan API error ' + res.status };
    const d = await res.json();
    return { target, ip: d.ip_str, org: d.org, country: d.country_name, ports: d.ports, vulns: d.vulns, hostnames: d.hostnames, os: d.os };
  } catch (e) { return { target, error: e.message }; }
}

async function handleScreenshot(input) {
  let url = String(input || '').trim();
  if (!url.startsWith('http')) url = 'https://' + url;
  try {
    const res = await fetch('http://127.0.0.1:18790/api/screenshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
      signal: AbortSignal.timeout(30000),
    });
    if (res.ok) {
      const data = await res.json();
      return { url, screenshot_b64: data.screenshot_b64, title: data.title, note: 'Screenshot via CloakBrowser' };
    }
  } catch {}
  return { url, note: 'Screenshot requires CloakBrowser (Python backend). Start the Python AI backend to enable this feature.', open_url: url };
}

function handleReverseImage(input) {
  const imgUrl = encodeURIComponent(String(input || '').trim());
  return {
    image_url: decodeURIComponent(imgUrl),
    search_links: [
      { name: 'Google Images', url: `https://lens.google.com/uploadbyurl?url=${imgUrl}` },
      { name: 'Bing Visual Search', url: `https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:${imgUrl}` },
      { name: 'TinEye', url: `https://tineye.com/search?url=${imgUrl}` },
      { name: 'Yandex Images', url: `https://yandex.com/images/search?url=${imgUrl}&rpt=imageview` },
    ],
    note: 'Click a link to perform reverse image search in your browser.',
  };
}

// ── Safe replacements for blocked tools ───────────────────────────────────

function handlePortScanner(input) {
  const host = String(input || '').trim();
  const commonPorts = [
    {port:21,service:'FTP'},{port:22,service:'SSH'},{port:23,service:'Telnet'},
    {port:25,service:'SMTP'},{port:53,service:'DNS'},{port:80,service:'HTTP'},
    {port:110,service:'POP3'},{port:143,service:'IMAP'},{port:443,service:'HTTPS'},
    {port:465,service:'SMTPS'},{port:587,service:'SMTP/TLS'},{port:993,service:'IMAPS'},
    {port:995,service:'POP3S'},{port:3306,service:'MySQL'},{port:5432,service:'PostgreSQL'},
    {port:6379,service:'Redis'},{port:8080,service:'HTTP-Alt'},{port:8443,service:'HTTPS-Alt'},
    {port:27017,service:'MongoDB'},{port:3389,service:'RDP'},
  ];
  return { host, note: 'Port scanning requires authorization. Reference list of common ports below.', common_ports: commonPorts, nmap_reference: `nmap -sV -p- ${host} (run only on authorized targets)` };
}

async function handleTraceroute(input) {
  const dns = require('dns').promises;
  const host = String(input || '').trim();
  const ips = await dns.resolve4(host).catch(() => []);
  return { host, resolved_ips: ips, note: 'Live traceroute requires network access. Resolved IPs shown above. Use: traceroute ' + host + ' (in terminal)', tool_hint: 'https://ping.eu/traceroute/' };
}

function handleSslSuiteScanner(input) {
  const host = String(input || '').trim().replace(/^https?:\/\//, '').split('/')[0];
  return {
    host,
    ssl_labs_url: `https://www.ssllabs.com/ssltest/analyze.html?d=${host}`,
    checklist: [
      'TLS 1.0/1.1 disabled?', 'TLS 1.3 supported?', 'Certificate valid and not expired?',
      'HSTS header present?', 'No RC4/3DES ciphers?', 'Certificate chain complete?', 'OCSP stapling enabled?',
    ],
    note: 'Use SSL Labs for full automated suite analysis.',
  };
}

function handleSubdomainBrute(input) {
  const domain = String(input || '').trim();
  const wordlist = ['www','mail','ftp','api','dev','staging','test','admin','blog','shop','cdn','ns1','ns2','smtp','vpn','remote','app','portal','auth','m','mobile','static','media','images','assets','docs','support','help','status','beta','prod','internal','intranet','extranet','login','secure','dashboard','git','gitlab','jenkins','jira','confluence','grafana','kibana','elastic','redis','db','database','backup','files','upload','downloads'];
  return { domain, wordlist, dns_query_hint: `for sub in ${wordlist.slice(0, 5).join(' ')} ...; do host $sub.${domain}; done`, note: 'Subdomain brute-force against unauthorized targets is illegal. Use this wordlist on owned domains only.' };
}

function handleHttpMethods(input) {
  let url = String(input || '').trim();
  if (!url.startsWith('http')) url = 'https://' + url;
  return {
    url,
    safe_methods: ['GET','POST','HEAD','OPTIONS'],
    dangerous_methods: ['PUT','DELETE','PATCH','TRACE','CONNECT'],
    checklist: [
      'Disable TRACE (XST attack vector)',
      'Disable unused methods in server config',
      'OPTIONS response should not expose sensitive methods',
      'CORS policy restricts allowed methods',
      'Test with: curl -X OPTIONS ' + url + ' -i',
    ],
    note: 'Unauthorized method testing against third-party targets is prohibited.',
  };
}

async function handleBannerGrab(input) {
  return analyzeHeaders(input);
}

function handlePingSweep(input) {
  const range = String(input || '').trim();
  const parts = range.split('/');
  const base = parts[0];
  const cidr = parseInt(parts[1]) || 24;
  const totalHosts = cidr <= 30 ? Math.pow(2, 32 - cidr) - 2 : 0;
  return { range, base_ip: base, cidr, total_hosts: totalHosts, note: 'Live ping sweep against unauthorized networks is prohibited. CIDR info shown above.', nmap_hint: `nmap -sn ${range} (authorized targets only)` };
}

// ── runTool (async-capable) ────────────────────────────────────────────────

async function runTool(toolId, input = '', options = {}) {
  const tool = getTool(toolId);
  if (!tool) return { ok: false, error: 'unknown_tool' };

  // Blocked tools: return safe alternative result instead of hard-blocking
  const blockedSafeHandlers = {
    'port-scanner': handlePortScanner,
    'social-media-scraper': handleUsernameSearch,
    'traceroute': handleTraceroute,
    'ssl-tls-suite-scanner': handleSslSuiteScanner,
    'subdomain-bruteforce': handleSubdomainBrute,
    'http-methods-discovery': handleHttpMethods,
    'banner-grabbing': handleBannerGrab,
    'ping-sweep-host-discovery': handlePingSweep,
  };
  if (tool.mode === MODES.blocked) {
    const safeHandler = blockedSafeHandlers[tool.id];
    if (safeHandler) {
      const result = await Promise.resolve(safeHandler(input));
      return { ok: true, tool, result };
    }
    return { ok: false, tool, result: blockedResult(tool) };
  }

  if (tool.mode === MODES.passive && !options.allowNetwork) {
    return {
      ok: false,
      tool,
      result: {
        blocked: true,
        reason: 'Network-backed OSINT is disabled by offline-first policy.',
        required_policy: ['allowNetwork', 'authorized_target'],
      },
    };
  }

  const handlers = {
    // existing safe handlers
    'email-lookup': analyzeEmail,
    'phone-number-lookup': analyzePhone,
    'ip-address-lookup': analyzeIp,
    'mac-address-lookup': analyzeMac,
    'hash-identifier-lookup': analyzeHash,
    'jwt-analyzer': analyzeJwt,
    'phishing-url-analyzer': analyzeUrl,
    'http-headers-analysis': analyzeHeaders,
    'waf-cdn-detector': analyzeHeaders,
    'clickjacking-tester': analyzeHeaders,
    'cors-misconfiguration-scanner': analyzeHeaders,
    'insecure-cookie-checker': analyzeHeaders,
    'email-header-analyzer': analyzeHeaders,
    'link-extractor': extractLinks,
    'js-endpoint-extractor': extractJsEndpoints,
    'payload-encoder-decoder': encodeDecode,
    'cve-search': (value) => ({ cves: [...new Set(String(value || '').match(/CVE-\d{4}-\d{4,7}/gi) || [])] }),
    'favicon-hash-lookup': (value) => ({ sha256: crypto.createHash('sha256').update(String(value || '')).digest('hex') }),
    'ai-search': (value) => ({ matches: searchTools(value, 10) }),
    // passive network handlers
    'dns-lookup': handleDnsLookup,
    'reverse-dns-lookup': handleReverseDns,
    'dmarc-spf-dkim-check': handleDmarcCheck,
    'subdomain-enumeration': handleSubdomainEnum,
    'ssl-tls-certificate-info': handleSslCert,
    'whois-lookup': handleWhois,
    'wayback-machine-lookup': handleWayback,
    'robots-sitemap-analyzer': handleRobotsSitemap,
    'security-txt-checker': handleSecurityTxt,
    'asn-lookup': handleAsnLookup,
    'website-technology-detection': handleTechDetection,
    'username-search': handleUsernameSearch,
    'email-breach-check': handleEmailBreach,
    'paste-code-search': handlePasteSearch,
    'shodan-host-lookup': handleShodan,
    'website-screenshot': handleScreenshot,
    'reverse-image-search': handleReverseImage,
    'reverse-image-search-extra': handleReverseImage,
  };

  const handler = handlers[tool.id];
  const result = await Promise.resolve(handler ? handler(input) : defensiveChecklist(tool));
  return { ok: true, tool, result };
}

module.exports = {
  CATEGORIES,
  MODES,
  TOOL_CATALOG,
  summarizeCatalog,
  searchTools,
  getTool,
  runTool,
};

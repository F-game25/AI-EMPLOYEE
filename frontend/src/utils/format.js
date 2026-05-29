// Shared formatting utilities — use these everywhere instead of inline one-liners

export function fmtDate(ts, { time = false, relative = false } = {}) {
  if (!ts) return '—'
  const d = new Date(typeof ts === 'string' && !ts.includes('T') ? Number(ts) : ts)
  if (isNaN(d.getTime())) return '—'
  if (relative) {
    const diff = Date.now() - d.getTime()
    if (diff < 60000) return 'just now'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
    return `${Math.floor(diff / 86400000)}d ago`
  }
  const opts = { month: 'short', day: 'numeric' }
  if (time) { opts.hour = '2-digit'; opts.minute = '2-digit' }
  return d.toLocaleDateString('en-US', opts)
}

export function fmtCurrency(v, { currency = 'USD', compact = true } = {}) {
  const n = Number(v)
  if (v === null || v === undefined || isNaN(n)) return '—'
  if (compact) {
    if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`
  }
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(n)
}

export function fmtNumber(v, { dec = 0, compact = true } = {}) {
  const n = Number(v)
  if (v === null || v === undefined || isNaN(n)) return '—'
  if (compact) {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  }
  return dec > 0 ? n.toFixed(dec) : String(Math.round(n))
}

export function fmtDuration(ms) {
  if (!ms) return '—'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export function fmtPct(v, dec = 1) {
  const n = Number(v)
  if (v === null || v === undefined || isNaN(n)) return '—'
  return `${n.toFixed(dec)}%`
}

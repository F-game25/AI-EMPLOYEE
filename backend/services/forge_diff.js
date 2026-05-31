'use strict'

const MAX_DIFF_LINES = 50000

function generateUnifiedDiff(beforeContent, afterContent, filePath) {
  const before = String(beforeContent || '').split('\n')
  const after  = String(afterContent  || '').split('\n')
  if (before.length > MAX_DIFF_LINES || after.length > MAX_DIFF_LINES) {
    return `--- ${filePath}\n+++ ${filePath}\n@@ diff truncated: file too large (>${MAX_DIFF_LINES} lines) @@\n`
  }
  if (before.join('\n') === after.join('\n')) return ''

  const lcs = (a, b) => {
    const m = a.length, n = b.length
    const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
    for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1])
    const seq = []
    let i = m, j = n
    while (i > 0 && j > 0) {
      if (a[i-1] === b[j-1]) { seq.unshift([i-1, j-1]); i--; j-- }
      else if (dp[i-1][j] >= dp[i][j-1]) i--
      else j--
    }
    return seq
  }

  const common = lcs(before, after)
  const ops = []
  let bi = 0, ai = 0
  for (const [cb, ca] of common) {
    while (bi < cb) { ops.push({ type: 'del', bi, line: before[bi] }); bi++ }
    while (ai < ca) { ops.push({ type: 'add', ai, line: after[ai]  }); ai++ }
    ops.push({ type: 'ctx', bi, ai, line: before[bi] }); bi++; ai++
  }
  while (bi < before.length) { ops.push({ type: 'del', bi, line: before[bi] }); bi++ }
  while (ai < after.length)  { ops.push({ type: 'add', ai, line: after[ai]  }); ai++ }

  const CTX = 3
  const changed = ops.reduce((acc, op, i) => { if (op.type !== 'ctx') acc.push(i); return acc }, [])
  if (!changed.length) return ''

  const hunks = []
  let hunkOps = null, hunkStart = -1
  for (const ci of changed) {
    const lo = Math.max(0, ci - CTX), hi = Math.min(ops.length - 1, ci + CTX)
    if (hunkOps && lo <= hunkStart + hunkOps.length + CTX) {
      const needed = ops.slice(hunkStart + hunkOps.length, hi + 1)
      hunkOps.push(...needed)
    } else {
      if (hunkOps) hunks.push({ start: hunkStart, ops: hunkOps })
      hunkStart = lo
      hunkOps = ops.slice(lo, hi + 1)
    }
  }
  if (hunkOps) hunks.push({ start: hunkStart, ops: hunkOps })

  const lines = [`--- a/${filePath}`, `+++ b/${filePath}`]
  for (const { start, ops: hops } of hunks) {
    const dels = hops.filter(o => o.type !== 'add')
    const adds = hops.filter(o => o.type !== 'del')
    const bStart = (dels[0]?.bi ?? 0) + 1
    const aStart = (adds[0]?.ai ?? 0) + 1
    lines.push(`@@ -${bStart},${dels.length} +${aStart},${adds.length} @@`)
    for (const op of hops) {
      if (op.type === 'ctx') lines.push(` ${op.line}`)
      else if (op.type === 'del') lines.push(`-${op.line}`)
      else lines.push(`+${op.line}`)
    }
  }
  return lines.join('\n')
}

function buildDiffForFiles(files) {
  if (!files?.length) return null
  if (files.length === 1) {
    const ud = generateUnifiedDiff('', files[0].content || '', files[0].path)
    return ud ? { unified: ud, path: files[0].path, isNew: true } : null
  }
  return {
    path: `${files.length} files`,
    isNew: true,
    hunks: files.slice(0, 4).map(file => ({
      header: `create ${file.path}`,
      lines: String(file.content || '').split('\n').slice(0, 40).map(line => ({ type: 'add', content: line })),
    })),
  }
}

module.exports = { generateUnifiedDiff, buildDiffForFiles }

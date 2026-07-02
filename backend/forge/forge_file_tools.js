'use strict'

const fs = require('fs')
const path = require('path')
const { resolveInsideWorkspace } = require('../services/forge_path')

// Simple glob implementation without external dependencies
function simpleGlob(cwd, pattern, opts = {}) {
  const ignore = new Set(opts.ignore || ['node_modules', '.git', '__pycache__', '.DS_Store', 'dist', 'build'])
  const maxDepth = opts.maxDepth || 6
  const results = []

  function walk(dir, depth, prefix) {
    if (depth > maxDepth) return
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true })
      for (const entry of entries) {
        if (ignore.has(entry.name)) continue
        const fullPath = path.join(dir, entry.name)
        const relPath = prefix ? path.join(prefix, entry.name) : entry.name
        if (entry.isDirectory()) {
          walk(fullPath, depth + 1, relPath)
        } else if (entry.isFile()) {
          if (matchesPattern(relPath, pattern)) results.push(relPath)
        }
      }
    } catch { /* skip unreadable dirs */ }
  }

  function matchesPattern(filePath, pattern) {
    // Simple pattern matching: * = any chars in a segment, ** = any depth
    if (pattern === '**/*') return true
    if (pattern.startsWith('**/*.')) {
      const ext = pattern.slice(5)
      return filePath.endsWith(ext)
    }
    if (pattern.startsWith('*.')) {
      const ext = pattern.slice(1)
      return path.basename(filePath).endsWith(ext)
    }
    // Direct match
    return filePath === pattern
  }

  walk(cwd, 0, '')
  return results
}

// Scoped file operations for forge agents: read, grep, glob
// All operations are scoped to a workspace root to prevent traversal attacks

const MAX_READ_SIZE = 100 * 1024 // 100 KB per file
const MAX_GREP_RESULTS = 50
const MAX_GLOB_RESULTS = 100
const MAX_GREP_BYTES = 500 * 1024 // 500 KB total grep output

function readFile(workspaceRoot, filePath, opts = {}) {
  try {
    const resolved = resolveInsideWorkspace(workspaceRoot, filePath)
    if (!fs.existsSync(resolved)) {
      return { error: `File not found: ${filePath}` }
    }
    const stat = fs.statSync(resolved)
    if (stat.size > MAX_READ_SIZE) {
      return { error: `File too large (${stat.size} bytes > ${MAX_READ_SIZE} limit): ${filePath}` }
    }
    const content = fs.readFileSync(resolved, 'utf8')
    const lines = content.split('\n').length - 1
    return {
      ok: true,
      path: filePath,
      content,
      size: content.length,
      lines,
    }
  } catch (err) {
    if (err.status === 403) return { error: `Access denied (path escape attempt): ${filePath}` }
    return { error: `Failed to read ${filePath}: ${err.message}` }
  }
}

function grepProject(workspaceRoot, pattern, opts = {}) {
  try {
    const flags = opts.flags || 'i' // case-insensitive by default
    const regex = new RegExp(pattern, flags)
    const maxResults = opts.maxResults || MAX_GREP_RESULTS
    const filePatterns = opts.filePattern ? [opts.filePattern] : ['**/*.js', '**/*.ts', '**/*.py', '**/*.json', '**/*.md']
    const ignore = opts.ignore || ['node_modules', '.git', '__pycache__', '.DS_Store', 'dist', 'build']

    const allFiles = new Set()
    for (const fp of filePatterns) {
      simpleGlob(workspaceRoot, fp, { ignore, maxDepth: 6 }).forEach(f => allFiles.add(f))
    }
    const files = Array.from(allFiles).slice(0, 500) // limit file scan

    const results = []
    let totalBytes = 0

    for (const file of files) {
      if (results.length >= maxResults || totalBytes > MAX_GREP_BYTES) break
      const resolved = path.join(workspaceRoot, file)
      try {
        if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) continue
        const stat = fs.statSync(resolved)
        if (stat.size > 200 * 1024) continue // skip large files in grep
        const content = fs.readFileSync(resolved, 'utf8')
        const lines = content.split('\n')
        lines.forEach((line, idx) => {
          if (results.length >= maxResults || totalBytes > MAX_GREP_BYTES) return
          if (regex.test(line)) {
            results.push({
              file,
              line: idx + 1,
              match: line.slice(0, 200),
            })
            totalBytes += line.length
          }
        })
      } catch { /* skip unreadable files */ }
    }

    return {
      ok: true,
      pattern,
      matches: results.length,
      results: results.slice(0, maxResults),
      truncated: results.length >= maxResults || totalBytes >= MAX_GREP_BYTES,
    }
  } catch (err) {
    return { error: `Grep failed: ${err.message}` }
  }
}

function globProject(workspaceRoot, pattern, opts = {}) {
  try {
    const ignore = opts.ignore || ['node_modules', '.git', '__pycache__', '.DS_Store', 'dist', 'build']
    const maxResults = opts.maxResults || MAX_GLOB_RESULTS

    const files = simpleGlob(workspaceRoot, pattern, { ignore, maxDepth: 6 }).slice(0, maxResults)

    return {
      ok: true,
      pattern,
      count: files.length,
      files,
      truncated: files.length >= maxResults,
    }
  } catch (err) {
    return { error: `Glob failed: ${err.message}` }
  }
}

module.exports = {
  readFile,
  grepProject,
  globProject,
  MAX_READ_SIZE,
  MAX_GREP_RESULTS,
  MAX_GLOB_RESULTS,
  MAX_GREP_BYTES,
}

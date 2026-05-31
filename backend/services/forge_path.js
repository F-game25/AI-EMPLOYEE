'use strict'
const path = require('path')
const os = require('os')
const fs = require('fs')

const PROJECT_SKIP = new Set(['.git', 'node_modules', '__pycache__', '.ascendforge', 'dist', 'build', '.DS_Store'])

const PROTECTED_PATH_PATTERNS = [
  /^launcher\//,
  /^backend\/routes\/auth/i,
  /^backend\/auth/i,
  /^runtime\/runtime\/sandbox_executor\.py$/,
  /^runtime\/runtime\/hot_reload_manager\.py$/,
  /^runtime\/runtime\/version_control\.py$/,
  /^runtime\/core\/forge_controller\.py$/,
  /^runtime\/config\/.*policy/i,
  /^runtime\/config\/.*wallet/i,
  /^start\.sh$/,
  /^stop\.sh$/,
]

function safeProjectRoot(project) {
  const root = path.resolve(project.root_path || '')
  return root
}

function resolveInsideProject(project, relativePath) {
  const root = safeProjectRoot(project)
  const target = path.resolve(root, String(relativePath || ''))
  if (target !== root && !target.startsWith(root + path.sep)) {
    const err = new Error('path escapes project root')
    err.status = 403
    throw err
  }
  return target
}

function normalizeRelPath(filePath) {
  return String(filePath || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .replace(/\.\.+/g, '.')
}

function resolveInsideWorkspace(workspaceRoot, relativePath) {
  const target = path.resolve(workspaceRoot, normalizeRelPath(relativePath))
  if (target !== workspaceRoot && !target.startsWith(workspaceRoot + path.sep)) {
    const err = new Error('path escapes run workspace')
    err.status = 403
    throw err
  }
  return target
}

function isProtectedPath(project, filePath) {
  const normalized = normalizeRelPath(filePath)
  if (project.target_type !== 'internal_repo') return false
  return PROTECTED_PATH_PATTERNS.some(pattern => pattern.test(normalized))
}

function canWritePath(project, filePath) {
  if (project.write_access !== true) return false
  const allowed = Array.isArray(project.allowed_write_paths) && project.allowed_write_paths.length
    ? project.allowed_write_paths
    : ['.']
  const normalized = normalizeRelPath(filePath)
  return allowed.some(prefix => {
    const p = normalizeRelPath(prefix)
    return p === '.' || normalized === p || normalized.startsWith(p.replace(/\/+$/, '') + '/')
  })
}

module.exports = {
  PROJECT_SKIP,
  PROTECTED_PATH_PATTERNS,
  safeProjectRoot,
  resolveInsideProject,
  resolveInsideWorkspace,
  normalizeRelPath,
  isProtectedPath,
  canWritePath,
}

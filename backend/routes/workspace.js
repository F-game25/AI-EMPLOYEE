'use strict';

const express = require('express');
const path = require('path');
const fs = require('fs/promises');
const os = require('os');
const { upload } = require('../middleware/upload');
const { createRouteRateLimit } = require('../middleware/route-rate-limit');
const { requireTenant } = require('../tenancy');

const router = express.Router();

// Each handler below does filesystem work (readdir/stat over the tenant's
// upload directory, or a file read for download) — bound the request rate
// per IP so repeated calls can't be used to hammer the disk.
const rateLimit = createRouteRateLimit({ keyPrefix: 'workspace-fs', max: 30, windowMs: 60_000 });

// Fail closed on missing tenant context instead of defaulting to "default":
// these routes read/write/delete tenant-scoped files, and a silent fallback
// would turn any missed middleware registration into a shared-tenant path.
// Placed before upload.fields() on /upload too, so a request with no tenant
// context never reaches multer's disk-write step in the first place.
router.use(requireTenant());

async function uploadDir(tenantId) {
  return path.join(os.homedir(), '.ai-employee', 'tenants', tenantId, 'workspace', 'uploads');
}

// Resolves fileId to its on-disk entry name via an exact match against the
// UUID basename multer assigned (see middleware/upload.js filename()), never
// a prefix match — a truncated/colliding id must not be able to select
// another file in the same tenant's directory.
async function resolveEntry(dir, fileId) {
  let entries;
  try {
    entries = await fs.readdir(dir);
  } catch {
    return null;
  }
  return entries.find(name => path.basename(name, path.extname(name)) === fileId) || null;
}

// POST /upload — upload files into tenant workspace
router.post('/upload', rateLimit, upload.fields([{ name: 'files', maxCount: 100 }, { name: 'file', maxCount: 100 }]), (req, res) => {
  const uploaded = [
    ...(req.files?.files || []),
    ...(req.files?.file || []),
  ];
  if (!uploaded.length) return res.status(400).json({ ok: false, error: 'No files uploaded' });

  const tenantId = req.tenant.tenantId;
  const files = uploaded.map(f => ({
    fileId: path.basename(f.filename, path.extname(f.filename)),
    name: f.originalname,
    size: f.size,
    path: f.path,
  }));
  res.json({ ok: true, tenant: tenantId, files });
});

// GET /files — list workspace files
router.get('/files', rateLimit, async (req, res) => {
  try {
    const dir = await uploadDir(req.tenant.tenantId);
    let names;
    try {
      names = await fs.readdir(dir);
    } catch {
      return res.json({ files: [] });
    }
    const files = await Promise.all(names.map(async name => {
      const stat = await fs.stat(path.join(dir, name));
      return { fileId: name, name, size: stat.size, mtime: stat.mtime };
    }));
    res.json({ files });
  } catch {
    res.json({ files: [] });
  }
});

// GET /download/:fileId — download a workspace file
router.get('/download/:fileId', rateLimit, async (req, res) => {
  const dir = await uploadDir(req.tenant.tenantId);
  const match = await resolveEntry(dir, req.params.fileId);
  if (!match) return res.status(404).json({ ok: false, error: 'File not found' });
  res.download(path.join(dir, match));
});

// DELETE /files/:fileId — delete a workspace file
router.delete('/files/:fileId', rateLimit, async (req, res) => {
  const dir = await uploadDir(req.tenant.tenantId);
  const match = await resolveEntry(dir, req.params.fileId);
  if (!match) return res.status(404).json({ ok: false, error: 'File not found' });
  try {
    await fs.unlink(path.join(dir, match));
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

module.exports = router;

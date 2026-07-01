'use strict';

const express = require('express');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { upload } = require('../middleware/upload');
const { createRouteRateLimit } = require('../middleware/route-rate-limit');

const router = express.Router();

// Each handler below does synchronous filesystem work (readdirSync/statSync
// over the tenant's upload directory, or a file read for download) — bound
// the request rate per IP so repeated calls can't be used to hammer the disk.
const rateLimit = createRouteRateLimit({ keyPrefix: 'workspace-fs', max: 30, windowMs: 60_000 });

// POST /upload — upload files into tenant workspace
router.post('/upload', rateLimit, upload.fields([{ name: 'files', maxCount: 100 }, { name: 'file', maxCount: 100 }]), (req, res) => {
  const uploaded = [
    ...(req.files?.files || []),
    ...(req.files?.file || []),
  ];
  if (!uploaded.length) return res.status(400).json({ ok: false, error: 'No files uploaded' });

  const tenantId = req.tenant?.tenantId || 'default';
  const files = uploaded.map(f => ({
    fileId: path.basename(f.filename, path.extname(f.filename)),
    name: f.originalname,
    size: f.size,
    path: f.path,
  }));
  res.json({ ok: true, tenant: tenantId, files });
});

// GET /files — list workspace files
router.get('/files', rateLimit, (req, res) => {
  try {
    const tenantId = req.tenant?.tenantId || 'default';
    const dir = path.join(os.homedir(), '.ai-employee', 'tenants', tenantId, 'workspace', 'uploads');
    if (!fs.existsSync(dir)) return res.json({ files: [] });
    const entries = fs.readdirSync(dir).map(name => {
      const stat = fs.statSync(path.join(dir, name));
      return { fileId: name, name, size: stat.size, mtime: stat.mtime };
    });
    res.json({ files: entries });
  } catch {
    res.json({ files: [] });
  }
});

// GET /download/:fileId — download a workspace file
router.get('/download/:fileId', rateLimit, (req, res) => {
  const tenantId = req.tenant?.tenantId || 'default';
  const dir = path.join(os.homedir(), '.ai-employee', 'tenants', tenantId, 'workspace', 'uploads');
  const entries = fs.existsSync(dir) ? fs.readdirSync(dir) : [];
  const match = entries.find(n => n.startsWith(req.params.fileId));
  if (!match) return res.status(404).json({ ok: false, error: 'File not found' });
  res.download(path.join(dir, match));
});

// DELETE /files/:fileId — delete a workspace file
router.delete('/files/:fileId', rateLimit, (req, res) => {
  const tenantId = req.tenant?.tenantId || 'default';
  const dir = path.join(os.homedir(), '.ai-employee', 'tenants', tenantId, 'workspace', 'uploads');
  const entries = fs.existsSync(dir) ? fs.readdirSync(dir) : [];
  const match = entries.find(n => n.startsWith(req.params.fileId));
  if (!match) return res.status(404).json({ ok: false, error: 'File not found' });
  try {
    fs.unlinkSync(path.join(dir, match));
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

module.exports = router;

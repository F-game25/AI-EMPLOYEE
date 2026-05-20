'use strict';

const express = require('express');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');
const { v4: uuidv4 } = require('uuid');
const { upload, handleUploadError } = require('../middleware/upload');
const { requireTenant } = require('../tenancy');

const router = express.Router();

/**
 * Get tenant's upload directory path
 */
function getUploadDir(tenantId) {
  return path.join(
    os.homedir(),
    '.ai-employee',
    'tenants',
    tenantId,
    'workspace',
    'uploads'
  );
}

/**
 * Get metadata file path for an uploaded file
 */
function getMetadataPath(uploadDir, fileId) {
  return path.join(uploadDir, `${fileId}.metadata.json`);
}

/**
 * Store file metadata alongside the uploaded file
 */
async function storeMetadata(uploadDir, fileId, file, originalPath) {
  const stats = await fs.stat(originalPath);
  const metadata = {
    fileId,
    originalName: file.originalname,
    fileName: file.filename,
    size: stats.size,
    mimeType: file.mimetype,
    uploadedAt: new Date().toISOString(),
    tenantId: file.tenantId
  };

  const metadataPath = getMetadataPath(uploadDir, fileId);
  await fs.writeFile(metadataPath, JSON.stringify(metadata, null, 2), 'utf8');
  return metadata;
}

/**
 * Load metadata for a file
 */
async function loadMetadata(uploadDir, fileId) {
  try {
    const metadataPath = getMetadataPath(uploadDir, fileId);
    const data = await fs.readFile(metadataPath, 'utf8');
    return JSON.parse(data);
  } catch {
    return null;
  }
}

/**
 * POST /api/workspace/upload
 * Upload file(s) with multipart/form-data
 */
router.post('/upload', requireTenant(), upload.array('files', 100), async (req, res) => {
  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).json({
        ok: false,
        error: 'No files provided'
      });
    }

    const tenantId = req.tenant.tenantId;
    const uploadDir = getUploadDir(tenantId);
    const uploadedFiles = [];

    // Process each uploaded file
    for (const file of req.files) {
      const fileId = path.basename(file.filename, path.extname(file.filename));
      const originalPath = file.path;

      try {
        // Store metadata
        file.tenantId = tenantId;
        const metadata = await storeMetadata(uploadDir, fileId, file, originalPath);

        uploadedFiles.push({
          fileId,
          ...metadata
        });
      } catch (error) {
        console.error(`[UPLOAD] Failed to store metadata for ${file.originalname}:`, error);
        // Clean up the uploaded file if metadata storage failed
        try {
          await fs.unlink(originalPath);
        } catch {}
        return res.status(500).json({
          ok: false,
          error: 'Failed to store file metadata',
          details: error.message
        });
      }
    }

    // Trigger async ingestion for each uploaded file (non-blocking)
    for (const f of uploadedFiles) {
      const filePath = path.join(uploadDir, f.fileName);
      const tenantId = f.tenantId || 'default';
      setImmediate(async () => {
        try {
          const { execFile } = require('child_process');
          execFile(process.env.PYTHON_BIN || 'python3', [
            path.join(__dirname, '../../runtime/core/document_ingestion_pipeline.py'),
            '--file', filePath,
            '--tenant', tenantId
          ], { timeout: 120000 }, (err, stdout, stderr) => {
            if (err) console.error('[ingestion] failed:', err.message);
            else console.log('[ingestion] done:', stdout.trim());
          });
        } catch (e) {
          console.error('[ingestion] spawn error:', e.message);
        }
      });
    }

    res.status(200).json({
      ok: true,
      files: uploadedFiles,
      count: uploadedFiles.length
    });
  } catch (error) {
    console.error('[UPLOAD] Upload handler error:', error);
    res.status(500).json({
      ok: false,
      error: 'Upload failed',
      details: error.message
    });
  }
});

/**
 * GET /api/workspace/files
 * List uploaded files for the current tenant
 */
router.get('/files', requireTenant(), async (req, res) => {
  try {
    const tenantId = req.tenant.tenantId;
    const uploadDir = getUploadDir(tenantId);

    // Check if upload directory exists
    try {
      await fs.access(uploadDir);
    } catch {
      return res.status(200).json({
        ok: true,
        files: [],
        count: 0
      });
    }

    // Read all files in the directory
    const entries = await fs.readdir(uploadDir);
    const files = [];

    for (const entry of entries) {
      // Skip metadata files, only process actual uploaded files
      if (entry.endsWith('.metadata.json')) continue;

      const fullPath = path.join(uploadDir, entry);
      const stats = await fs.stat(fullPath);

      // Skip directories
      if (!stats.isFile()) continue;

      // Extract file ID from filename (UUID before extension)
      const fileId = path.basename(entry, path.extname(entry));

      // Load metadata
      const metadata = await loadMetadata(uploadDir, fileId);

      if (metadata) {
        files.push(metadata);
      }
    }

    // Sort by upload time (newest first)
    files.sort((a, b) => new Date(b.uploadedAt) - new Date(a.uploadedAt));

    res.status(200).json({
      ok: true,
      files,
      count: files.length
    });
  } catch (error) {
    console.error('[WORKSPACE] List files error:', error);
    res.status(500).json({
      ok: false,
      error: 'Failed to list files',
      details: error.message
    });
  }
});

/**
 * GET /api/workspace/download/:fileId
 * Download a file by ID
 */
router.get('/download/:fileId', requireTenant(), async (req, res) => {
  try {
    const tenantId = req.tenant.tenantId;
    const { fileId } = req.params;

    // Validate fileId format (UUID)
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(fileId)) {
      return res.status(400).json({
        ok: false,
        error: 'Invalid file ID format'
      });
    }

    const uploadDir = getUploadDir(tenantId);

    // Load metadata to get original filename
    const metadata = await loadMetadata(uploadDir, fileId);
    if (!metadata) {
      return res.status(404).json({
        ok: false,
        error: 'File not found'
      });
    }

    // Construct file path
    const ext = path.extname(metadata.fileName);
    const filePath = path.join(uploadDir, metadata.fileName);

    // Verify file exists
    try {
      await fs.access(filePath);
    } catch {
      return res.status(404).json({
        ok: false,
        error: 'File not found'
      });
    }

    // Send file with original name (escape quotes in filename)
    const escapedName = metadata.originalName.replace(/"/g, '\\"');
    res.setHeader('Content-Disposition', `attachment; filename="${escapedName}"`);
    res.setHeader('Content-Type', metadata.mimeType || 'application/octet-stream');

    const stream = require('fs').createReadStream(filePath);
    stream.pipe(res);
    stream.on('error', (error) => {
      console.error('[WORKSPACE] Download stream error:', error);
      if (!res.headersSent) {
        res.status(500).json({
          ok: false,
          error: 'Download failed'
        });
      }
    });
  } catch (error) {
    console.error('[WORKSPACE] Download error:', error);
    if (!res.headersSent) {
      res.status(500).json({
        ok: false,
        error: 'Download failed',
        details: error.message
      });
    }
  }
});

/**
 * DELETE /api/workspace/files/:fileId
 * Delete a file by ID
 */
router.delete('/files/:fileId', requireTenant(), async (req, res) => {
  try {
    const tenantId = req.tenant.tenantId;
    const { fileId } = req.params;

    // Validate fileId format
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(fileId)) {
      return res.status(400).json({
        ok: false,
        error: 'Invalid file ID format'
      });
    }

    const uploadDir = getUploadDir(tenantId);

    // Load metadata
    const metadata = await loadMetadata(uploadDir, fileId);
    if (!metadata) {
      return res.status(404).json({
        ok: false,
        error: 'File not found'
      });
    }

    // Delete the file and its metadata
    try {
      const ext = path.extname(metadata.fileName);
      const filePath = path.join(uploadDir, metadata.fileName);
      const metadataPath = getMetadataPath(uploadDir, fileId);

      await fs.unlink(filePath).catch(() => {});
      await fs.unlink(metadataPath).catch(() => {});

      res.status(200).json({
        ok: true,
        message: 'File deleted'
      });
    } catch (error) {
      console.error(`[WORKSPACE] Delete failed for ${fileId}:`, error);
      res.status(500).json({
        ok: false,
        error: 'Failed to delete file',
        details: error.message
      });
    }
  } catch (error) {
    console.error('[WORKSPACE] Delete error:', error);
    res.status(500).json({
      ok: false,
      error: 'Delete failed',
      details: error.message
    });
  }
});

/**
 * POST /api/workspace/analyze
 * Re-trigger ingestion pipeline for an already-uploaded file
 */
router.post('/analyze', requireTenant(), async (req, res) => {
  try {
    const tenantId = req.tenant.tenantId;
    const { fileId } = req.body || {};
    if (!fileId) return res.status(400).json({ ok: false, error: 'fileId required' });

    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(fileId)) return res.status(400).json({ ok: false, error: 'Invalid fileId format' });

    const uploadDir = getUploadDir(tenantId);
    const metadata = await loadMetadata(uploadDir, fileId);
    if (!metadata) return res.status(404).json({ ok: false, error: 'File not found' });

    const filePath = path.join(uploadDir, metadata.fileName);
    try { await fs.access(filePath); } catch {
      return res.status(404).json({ ok: false, error: 'File data not found on disk' });
    }

    // Spawn ingestion non-blocking
    const { execFile } = require('child_process');
    execFile(process.env.PYTHON_BIN || 'python3', [
      path.join(__dirname, '../../runtime/core/document_ingestion_pipeline.py'),
      '--file', filePath,
      '--tenant', tenantId
    ], { timeout: 120000 }, (err, stdout) => {
      if (err) console.error('[ingestion] re-analyze failed:', err.message);
      else console.log('[ingestion] re-analyze done:', stdout.trim());
    });

    res.status(202).json({ ok: true, message: 'Ingestion queued', fileId, file: metadata.originalName });
  } catch (error) {
    console.error('[WORKSPACE] Analyze error:', error);
    res.status(500).json({ ok: false, error: 'Analyze failed', details: error.message });
  }
});

/**
 * GET /api/workspace/ingestion-log
 * Return the last 50 ingestion log entries
 */
router.get('/ingestion-log', requireTenant(), async (req, res) => {
  try {
    const logPath = path.join(__dirname, '../../state/ingestion_log.jsonl');
    let entries = [];
    try {
      const raw = await fs.readFile(logPath, 'utf8');
      entries = raw.trim().split('\n').filter(Boolean).slice(-50).map(line => {
        try { return JSON.parse(line); } catch { return null; }
      }).filter(Boolean);
    } catch {
      // File doesn't exist yet — return empty list
    }
    res.status(200).json({ ok: true, entries, count: entries.length });
  } catch (error) {
    console.error('[WORKSPACE] Ingestion log error:', error);
    res.status(500).json({ ok: false, error: 'Failed to read ingestion log', details: error.message });
  }
});

module.exports = router;

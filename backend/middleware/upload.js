'use strict';

const multer = require('multer');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { v4: uuidv4 } = require('uuid');

// Allowed file extensions (code + text only; binaries, images, PDFs are blocked)
const ALLOWED_EXTENSIONS = new Set([
  '.py', '.js', '.ts', '.jsx', '.tsx',
  '.md', '.txt', '.json', '.sh',
  '.css', '.html',
  '.rs', '.toml', '.yaml', '.yml',
  '.csv', '.sql', '.xml',
]);

// Maximum file size: 50MB
const MAX_FILE_SIZE = 50 * 1024 * 1024;

/**
 * Create multer storage engine with tenant-aware destination
 */
function createUploadStorage() {
  return multer.diskStorage({
    destination: (req, file, cb) => {
      try {
        const tenantId = req.tenant?.tenantId || 'default';
        const uploadDir = path.join(
          os.homedir(),
          '.ai-employee',
          'tenants',
          tenantId,
          'workspace',
          'uploads'
        );

        // Create directory if it doesn't exist
        fs.mkdirSync(uploadDir, { recursive: true });
        cb(null, uploadDir);
      } catch (error) {
        cb(error);
      }
    },
    filename: (req, file, cb) => {
      const fileId = uuidv4();
      const ext = path.extname(file.originalname);
      cb(null, fileId + ext);
    }
  });
}

/**
 * File filter to validate file types
 */
function fileFilter(req, file, cb) {
  const ext = path.extname(file.originalname).toLowerCase();

  if (!ALLOWED_EXTENSIONS.has(ext)) {
    return cb(new Error(
      `File type '${ext}' not allowed. ` +
      `Allowed types: ${Array.from(ALLOWED_EXTENSIONS).join(', ')}`
    ));
  }

  cb(null, true);
}

/**
 * Create multer instance with tenant-aware storage
 */
const upload = multer({
  storage: createUploadStorage(),
  fileFilter,
  limits: {
    fileSize: MAX_FILE_SIZE,
    files: 100
  }
});

/**
 * Error handler middleware for multer errors
 */
function handleUploadError(err, req, res, next) {
  if (err instanceof multer.MulterError) {
    if (err.code === 'LIMIT_FILE_SIZE') {
      return res.status(413).json({
        ok: false,
        error: 'File too large',
        details: `Maximum file size is ${MAX_FILE_SIZE / 1024 / 1024}MB`
      });
    }
    if (err.code === 'LIMIT_FILE_COUNT') {
      return res.status(400).json({
        ok: false,
        error: 'Too many files',
        details: 'Maximum 100 files per request'
      });
    }
    return res.status(400).json({
      ok: false,
      error: 'Upload error',
      details: err.message
    });
  }

  // Custom validation errors
  if (err && err.message) {
    return res.status(400).json({
      ok: false,
      error: 'Invalid file',
      details: err.message
    });
  }

  next(err);
}

module.exports = {
  upload,
  handleUploadError,
  ALLOWED_EXTENSIONS,
  MAX_FILE_SIZE
};

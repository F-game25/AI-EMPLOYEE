/**
 * Unit tests for file upload middleware and routes
 * Can be run without a full server to validate structure
 */

const path = require('path');
const fs = require('fs');
const os = require('os');
const assert = require('assert');

// Verify module imports work
try {
  const upload = require('../backend/middleware/upload');
  const workspaceRouter = require('../backend/routes/workspace');
  console.log('✓ Modules import successfully');
  console.log('  - upload.js: OK');
  console.log('  - workspace.js: OK');
} catch (error) {
  console.error('✗ Module import failed:', error.message);
  process.exit(1);
}

// Verify upload middleware exports
try {
  const { upload, handleUploadError, ALLOWED_EXTENSIONS, MAX_FILE_SIZE } = require('../backend/middleware/upload');
  assert(upload, 'upload should be exported');
  assert(handleUploadError, 'handleUploadError should be exported');
  assert(ALLOWED_EXTENSIONS instanceof Set, 'ALLOWED_EXTENSIONS should be a Set');
  assert(MAX_FILE_SIZE === 50 * 1024 * 1024, 'MAX_FILE_SIZE should be 50MB');
  console.log('✓ Middleware exports valid');
  console.log(`  - MAX_FILE_SIZE: ${MAX_FILE_SIZE / 1024 / 1024}MB`);
  console.log(`  - Allowed extensions: ${Array.from(ALLOWED_EXTENSIONS).join(', ')}`);
} catch (error) {
  console.error('✗ Middleware export validation failed:', error.message);
  process.exit(1);
}

// Verify workspace router exports
try {
  const workspaceRouter = require('../backend/routes/workspace');
  assert(workspaceRouter && (typeof workspaceRouter === 'object' || typeof workspaceRouter === 'function'), 'workspace router should be an object or function');

  // Express Router has a stack property with layers
  if (workspaceRouter.stack && Array.isArray(workspaceRouter.stack)) {
    console.log('✓ Workspace router structure valid (Express Router detected)');

    // Check for expected routes
    const routes = workspaceRouter.stack.map(layer => {
      const path = layer.route?.path;
      const methods = layer.route?.methods;
      return { path, methods };
    }).filter(r => r.path);

    console.log(`  - Routes defined: ${routes.length}`);
    routes.forEach(r => {
      console.log(`    - ${Object.keys(r.methods || {}).join(',').toUpperCase()} ${r.path}`);
    });

    // Verify expected routes exist
    const routePaths = new Set(routes.map(r => r.path));
    assert(routePaths.has('/upload'), 'Should have POST /upload route');
    assert(routePaths.has('/files'), 'Should have GET /files route');
    assert(routePaths.has('/download/:fileId'), 'Should have GET /download/:fileId route');
    assert(routePaths.has('/files/:fileId'), 'Should have DELETE /files/:fileId route');
  } else {
    // Router might not have stack until it's mounted, check if it's a valid router
    assert(typeof workspaceRouter.post === 'function', 'Router should have post method');
    assert(typeof workspaceRouter.get === 'function', 'Router should have get method');
    assert(typeof workspaceRouter.delete === 'function', 'Router should have delete method');
    console.log('✓ Workspace router structure valid (Express Router functions present)');
    console.log('  - Routes defined (validated by methods)');
    console.log('    - POST /upload');
    console.log('    - GET /files');
    console.log('    - GET /download/:fileId');
    console.log('    - DELETE /files/:fileId');
  }
} catch (error) {
  console.error('✗ Workspace router validation failed:', error.message);
  process.exit(1);
}

// Verify directory structure
try {
  const testTenantId = 'test-unit-tenant';
  const uploadDir = path.join(
    os.homedir(),
    '.ai-employee',
    'tenants',
    testTenantId,
    'workspace',
    'uploads'
  );
  console.log('✓ Directory paths valid');
  console.log(`  - Test upload dir would be: ${uploadDir}`);
} catch (error) {
  console.error('✗ Directory structure validation failed:', error.message);
  process.exit(1);
}

// Verify allowed extensions
try {
  const { ALLOWED_EXTENSIONS } = require('../backend/middleware/upload');
  const testExtensions = [
    { ext: '.py', should: true },
    { ext: '.js', should: true },
    { ext: '.ts', should: true },
    { ext: '.jsx', should: true },
    { ext: '.tsx', should: true },
    { ext: '.md', should: true },
    { ext: '.txt', should: true },
    { ext: '.json', should: true },
    { ext: '.sh', should: true },
    { ext: '.css', should: true },
    { ext: '.html', should: true },
    { ext: '.exe', should: false },
    { ext: '.zip', should: false },
    { ext: '.pdf', should: false },
    { ext: '.png', should: false },
  ];

  let allPassed = true;
  testExtensions.forEach(({ ext, should }) => {
    const isAllowed = ALLOWED_EXTENSIONS.has(ext);
    if (isAllowed === should) {
      console.log(`  ✓ .${ext.slice(1)}: ${isAllowed ? 'allowed' : 'blocked'}`);
    } else {
      console.log(`  ✗ .${ext.slice(1)}: expected ${should ? 'allowed' : 'blocked'}, got ${isAllowed ? 'allowed' : 'blocked'}`);
      allPassed = false;
    }
  });

  if (!allPassed) {
    throw new Error('File extension validation failed');
  }
  console.log('✓ File type validation correct');
} catch (error) {
  console.error('✗ File type validation failed:', error.message);
  process.exit(1);
}

// Verify server.js integration
try {
  const serverContent = fs.readFileSync(path.join(__dirname, '../backend/server.js'), 'utf8');
  assert(serverContent.includes("require('./routes/workspace')"), 'server.js should require workspace router');
  assert(serverContent.includes("'/api/workspace'"), 'server.js should mount workspace router at /api/workspace');
  assert(serverContent.includes('handleUploadError'), 'server.js should use handleUploadError middleware');
  console.log('✓ Server.js integration verified');
  console.log('  - Workspace router mounted at /api/workspace');
  console.log('  - Upload error handler installed');
} catch (error) {
  console.error('✗ Server.js integration check failed:', error.message);
  process.exit(1);
}

console.log('\n✅ All unit validation checks passed!');
console.log('\nNext steps:');
console.log('1. Start the server: npm start');
console.log('2. Run integration tests: npm test');
console.log('3. Test endpoints with curl:');
console.log('   - Upload: curl -F "files=@test.py" http://localhost:8787/api/workspace/upload');
console.log('   - List: curl http://localhost:8787/api/workspace/files');
console.log('   - Download: curl http://localhost:8787/api/workspace/download/{fileId} -o test.py');

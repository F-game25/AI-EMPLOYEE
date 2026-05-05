"""
Comprehensive tests for file upload backend (Phase 2.1)
Tests: POST /api/workspace/upload, GET /api/workspace/files, GET /api/workspace/download/:fileId
"""

import pytest
import requests
import json
import os
import sys
import time
import shutil
from pathlib import Path
from io import BytesIO

# Add runtime to path
RUNTIME_DIR = Path(__file__).parent.parent / 'runtime'
sys.path.insert(0, str(RUNTIME_DIR))

# Configuration
BASE_URL = 'http://localhost:8787'
AUTH_TOKEN = 'test-token'  # Will be set by auth flow
TENANT_ID = 'test-tenant-upload'
UPLOAD_DIR = Path.home() / '.ai-employee' / 'tenants' / TENANT_ID / 'workspace' / 'uploads'


@pytest.fixture(scope='module')
def auth_token():
    """Get JWT token for testing"""
    # In a real test, this would authenticate via /auth/login
    # For now, return a mock token (server test setup should configure JWT)
    return 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJ0ZXN0LXRlbmFudC11cGxvYWQiLCJvcmdfbmFtZSI6InRlc3Qtb3JnIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIn0.test'


@pytest.fixture(autouse=True)
def cleanup_uploads():
    """Clean up upload directory before and after tests"""
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    yield
    # Keep uploads for post-test inspection
    # shutil.rmtree(UPLOAD_DIR, ignore_errors=True)


class TestFileUpload:
    """Test file upload endpoint"""

    def test_upload_single_python_file(self, auth_token):
        """Upload a single Python file"""
        file_content = b'print("Hello, World!")\n'
        files = {'files': ('test.py', BytesIO(file_content), 'text/plain')}

        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert len(data['files']) == 1
        assert data['files'][0]['originalName'] == 'test.py'
        assert data['files'][0]['size'] > 0
        assert 'fileId' in data['files'][0]
        assert 'uploadedAt' in data['files'][0]

    def test_upload_multiple_files(self, auth_token):
        """Upload multiple files in one request"""
        files = [
            ('files', ('script.py', BytesIO(b'print("test")\n'), 'text/plain')),
            ('files', ('data.json', BytesIO(b'{"key": "value"}\n'), 'application/json')),
            ('files', ('style.css', BytesIO(b'body { color: red; }\n'), 'text/css')),
        ]

        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert data['count'] == 3
        assert len(data['files']) == 3
        assert {f['originalName'] for f in data['files']} == {'script.py', 'data.json', 'style.css'}

    def test_upload_no_files_error(self, auth_token):
        """Uploading without files returns 400"""
        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=[],
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 400
        data = response.json()
        assert data['ok'] is False
        assert 'error' in data

    def test_upload_invalid_file_type_error(self, auth_token):
        """Uploading unsupported file type returns 400"""
        files = {'files': ('malware.exe', BytesIO(b'MZ\x90\x00'), 'application/x-msdownload')}

        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 400
        data = response.json()
        assert data['ok'] is False
        assert 'not allowed' in data['error'].lower() or 'invalid' in data['details'].lower()

    def test_upload_file_too_large_error(self, auth_token):
        """Uploading file > 50MB returns 413"""
        # Create a large file (51MB)
        large_content = b'x' * (51 * 1024 * 1024)
        files = {'files': ('large.txt', BytesIO(large_content), 'text/plain')}

        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token},
            timeout=30
        )

        assert response.status_code == 413
        data = response.json()
        assert data['ok'] is False
        assert 'too large' in data['error'].lower() or '50' in data['details']

    def test_upload_stores_metadata(self, auth_token):
        """Uploaded file has metadata stored alongside it"""
        files = {'files': ('readme.md', BytesIO(b'# Test\n'), 'text/markdown')}

        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        file_id = response.json()['files'][0]['fileId']

        # Check metadata file exists
        metadata_file = UPLOAD_DIR / f'{file_id}.metadata.json'
        assert metadata_file.exists()

        # Verify metadata content
        with open(metadata_file) as f:
            metadata = json.load(f)
        assert metadata['fileId'] == file_id
        assert metadata['originalName'] == 'readme.md'
        assert metadata['size'] > 0
        assert metadata['mimeType'] == 'text/markdown'
        assert metadata['tenantId'] == TENANT_ID


class TestFileList:
    """Test file listing endpoint"""

    def test_list_empty_files(self, auth_token):
        """GET /api/workspace/files returns empty list when no files uploaded"""
        response = requests.get(
            f'{BASE_URL}/api/workspace/files',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert data['files'] == []
        assert data['count'] == 0

    def test_list_uploaded_files(self, auth_token):
        """GET /api/workspace/files lists all uploaded files"""
        # Upload files first
        files = [
            ('files', ('file1.py', BytesIO(b'print(1)\n'), 'text/plain')),
            ('files', ('file2.js', BytesIO(b'console.log(2);\n'), 'text/javascript')),
            ('files', ('file3.md', BytesIO(b'# File 3\n'), 'text/markdown')),
        ]

        requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        # List files
        response = requests.get(
            f'{BASE_URL}/api/workspace/files',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert data['count'] == 3
        assert len(data['files']) == 3
        assert {f['originalName'] for f in data['files']} == {'file1.py', 'file2.js', 'file3.md'}

    def test_list_files_sorted_by_time(self, auth_token):
        """Files are sorted by upload time (newest first)"""
        # Upload file 1
        files1 = {'files': ('file1.txt', BytesIO(b'first\n'), 'text/plain')}
        requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files1,
            headers={'Authorization': auth_token}
        )

        time.sleep(1)  # Ensure different timestamps

        # Upload file 2
        files2 = {'files': ('file2.txt', BytesIO(b'second\n'), 'text/plain')}
        requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files2,
            headers={'Authorization': auth_token}
        )

        # List files
        response = requests.get(
            f'{BASE_URL}/api/workspace/files',
            headers={'Authorization': auth_token}
        )

        data = response.json()
        assert data['count'] == 2
        # Newest first
        assert data['files'][0]['originalName'] == 'file2.txt'
        assert data['files'][1]['originalName'] == 'file1.txt'

    def test_list_files_contains_metadata(self, auth_token):
        """Listing files includes all metadata fields"""
        files = {'files': ('document.txt', BytesIO(b'content\n'), 'text/plain')}
        requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        response = requests.get(
            f'{BASE_URL}/api/workspace/files',
            headers={'Authorization': auth_token}
        )

        data = response.json()
        file_info = data['files'][0]
        assert 'fileId' in file_info
        assert 'originalName' in file_info
        assert 'size' in file_info
        assert 'mimeType' in file_info
        assert 'uploadedAt' in file_info
        assert 'tenantId' in file_info


class TestFileDownload:
    """Test file download endpoint"""

    def test_download_file(self, auth_token):
        """Download a file by ID"""
        # Upload file
        original_content = b'Hello, Download!\n'
        files = {'files': ('hello.txt', BytesIO(original_content), 'text/plain')}
        upload_response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )
        file_id = upload_response.json()['files'][0]['fileId']

        # Download file
        response = requests.get(
            f'{BASE_URL}/api/workspace/download/{file_id}',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        assert response.content == original_content
        assert 'attachment' in response.headers.get('Content-Disposition', '')
        assert 'hello.txt' in response.headers.get('Content-Disposition', '')

    def test_download_nonexistent_file(self, auth_token):
        """Download nonexistent file returns 404"""
        fake_file_id = '00000000-0000-0000-0000-000000000000'
        response = requests.get(
            f'{BASE_URL}/api/workspace/download/{fake_file_id}',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 404
        data = response.json()
        assert data['ok'] is False
        assert 'not found' in data['error'].lower()

    def test_download_invalid_file_id(self, auth_token):
        """Download with invalid file ID format returns 400"""
        response = requests.get(
            f'{BASE_URL}/api/workspace/download/not-a-uuid',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 400
        data = response.json()
        assert data['ok'] is False

    def test_download_preserves_content_type(self, auth_token):
        """Downloaded file has correct MIME type"""
        files = {
            'files': ('data.json', BytesIO(b'{"test": true}\n'), 'application/json')
        }
        upload_response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )
        file_id = upload_response.json()['files'][0]['fileId']

        response = requests.get(
            f'{BASE_URL}/api/workspace/download/{file_id}',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        assert 'application/json' in response.headers.get('Content-Type', '')


class TestFileDelete:
    """Test file deletion endpoint"""

    def test_delete_file(self, auth_token):
        """Delete a file by ID"""
        # Upload file
        files = {'files': ('temp.txt', BytesIO(b'temporary\n'), 'text/plain')}
        upload_response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )
        file_id = upload_response.json()['files'][0]['fileId']

        # Delete file
        response = requests.delete(
            f'{BASE_URL}/api/workspace/files/{file_id}',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True

        # Verify file is gone from listing
        list_response = requests.get(
            f'{BASE_URL}/api/workspace/files',
            headers={'Authorization': auth_token}
        )
        assert list_response.json()['count'] == 0

    def test_delete_nonexistent_file(self, auth_token):
        """Delete nonexistent file returns 404"""
        fake_file_id = '00000000-0000-0000-0000-000000000000'
        response = requests.delete(
            f'{BASE_URL}/api/workspace/files/{fake_file_id}',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 404
        data = response.json()
        assert data['ok'] is False

    def test_delete_invalid_file_id(self, auth_token):
        """Delete with invalid file ID returns 400"""
        response = requests.delete(
            f'{BASE_URL}/api/workspace/files/invalid-id',
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 400
        data = response.json()
        assert data['ok'] is False


class TestMultitenancy:
    """Test multi-tenant isolation"""

    def test_uploads_isolated_by_tenant(self):
        """Files uploaded by one tenant are not visible to another"""
        tenant1_token = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJ0ZW5hbnQtMSIsIm9yZ19uYW1lIjoib3JnLTEiLCJlbWFpbCI6InQxQHRlc3QuY29tIn0.test'
        tenant2_token = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJ0ZW5hbnQtMiIsIm9yZ19uYW1lIjoib3JnLTIiLCJlbWFpbCI6InQyQHRlc3QuY29tIn0.test'

        # Tenant 1 uploads file
        files1 = {'files': ('tenant1.txt', BytesIO(b'tenant1 data\n'), 'text/plain')}
        requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files1,
            headers={'Authorization': tenant1_token}
        )

        # Tenant 2 uploads different file
        files2 = {'files': ('tenant2.txt', BytesIO(b'tenant2 data\n'), 'text/plain')}
        requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files2,
            headers={'Authorization': tenant2_token}
        )

        # Tenant 1 should only see their file
        list1 = requests.get(
            f'{BASE_URL}/api/workspace/files',
            headers={'Authorization': tenant1_token}
        ).json()
        assert list1['count'] == 1
        assert list1['files'][0]['originalName'] == 'tenant1.txt'

        # Tenant 2 should only see their file
        list2 = requests.get(
            f'{BASE_URL}/api/workspace/files',
            headers={'Authorization': tenant2_token}
        ).json()
        assert list2['count'] == 1
        assert list2['files'][0]['originalName'] == 'tenant2.txt'


class TestAllowedFileTypes:
    """Test file type validation"""

    @pytest.mark.parametrize('filename,content_type', [
        ('script.py', 'text/plain'),
        ('app.js', 'text/javascript'),
        ('types.ts', 'text/plain'),
        ('component.jsx', 'text/javascript'),
        ('component.tsx', 'text/plain'),
        ('README.md', 'text/markdown'),
        ('data.txt', 'text/plain'),
        ('config.json', 'application/json'),
        ('deploy.sh', 'text/plain'),
        ('styles.css', 'text/css'),
        ('page.html', 'text/html'),
    ])
    def test_allowed_file_types(self, auth_token, filename, content_type):
        """All allowed file types can be uploaded"""
        files = {'files': (filename, BytesIO(b'content\n'), content_type)}
        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 200
        assert response.json()['ok'] is True

    @pytest.mark.parametrize('filename', [
        'virus.exe',
        'script.zip',
        'image.png',
        'document.pdf',
        'archive.tar.gz',
        'binary.bin',
        'library.so',
        'system.dll',
    ])
    def test_disallowed_file_types(self, auth_token, filename):
        """Disallowed file types are rejected"""
        files = {'files': (filename, BytesIO(b'content\n'), 'application/octet-stream')}
        response = requests.post(
            f'{BASE_URL}/api/workspace/upload',
            files=files,
            headers={'Authorization': auth_token}
        )

        assert response.status_code == 400
        assert response.json()['ok'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

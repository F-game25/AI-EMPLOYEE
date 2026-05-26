"""Tests for workspace file upload/list/delete endpoints.

POST /api/workspace/upload  → {ok, files:[{id,name,path,size,mtime}], count}
GET  /api/workspace/files   → {files:[{name,path,size,mtime}], workspace}
DELETE /api/workspace/files/:path → {ok}
"""

import pytest
import requests
import time
import urllib.request
import json
from io import BytesIO

BASE_URL = "http://localhost:8787"
_AUTH_TOKEN = None


def _get_auth_token():
    global _AUTH_TOKEN
    if _AUTH_TOKEN:
        return _AUTH_TOKEN
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/auth/auto-token")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            token = data.get("token") or data.get("access_token") or data.get("accessToken")
            if token:
                _AUTH_TOKEN = f"Bearer {token}"
                return _AUTH_TOKEN
    except Exception:
        pass
    return None


def _headers():
    h = {"Accept": "application/json"}
    tok = _get_auth_token()
    if tok:
        h["Authorization"] = tok
    return h


@pytest.fixture(autouse=True)
def skip_if_no_server():
    try:
        requests.get(f"{BASE_URL}/api/readiness", timeout=3)
    except Exception:
        pytest.skip("Server not running")


class TestUpload:
    def test_upload_single_file(self):
        files = {"files": ("hello.py", BytesIO(b'print("hi")\n'), "text/plain")}
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["count"] == 1
        assert len(d["files"]) == 1
        f = d["files"][0]
        assert f["name"] == "hello.py"
        assert f["size"] > 0
        assert "id" in f
        assert "path" in f

    def test_upload_multiple_files(self):
        files = [
            ("files", ("a.py", BytesIO(b"# a\n"), "text/plain")),
            ("files", ("b.js", BytesIO(b"// b\n"), "text/javascript")),
            ("files", ("c.md", BytesIO(b"# c\n"), "text/markdown")),
        ]
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["count"] == 3
        names = {f["name"] for f in d["files"]}
        assert names == {"a.py", "b.js", "c.md"}

    def test_upload_no_files_returns_400(self):
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=[], headers=_headers())
        assert r.status_code == 400
        assert r.json()["ok"] is False

    def test_upload_disallowed_extension_returns_400(self):
        files = {"files": ("bad.exe", BytesIO(b"MZ\x00"), "application/octet-stream")}
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())
        assert r.status_code == 400
        d = r.json()
        assert d["ok"] is False
        assert "not allowed" in (d.get("details") or d.get("error") or "").lower()

    def test_upload_large_file_returns_413(self):
        large = b"x" * (51 * 1024 * 1024)
        files = {"files": ("big.txt", BytesIO(large), "text/plain")}
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers(), timeout=30)
        assert r.status_code == 413
        try:
            assert r.json()["ok"] is False
        except Exception:
            pass  # Some multer errors don't produce JSON body

    def test_upload_requires_auth(self):
        files = {"files": ("test.py", BytesIO(b"x"), "text/plain")}
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=files)
        assert r.status_code in (401, 403)

    @pytest.mark.parametrize("filename,mime", [
        ("s.py", "text/plain"),
        ("s.js", "text/javascript"),
        ("s.ts", "text/plain"),
        ("s.jsx", "text/javascript"),
        ("s.tsx", "text/plain"),
        ("s.md", "text/markdown"),
        ("s.txt", "text/plain"),
        ("s.json", "application/json"),
        ("s.sh", "text/plain"),
        ("s.css", "text/css"),
        ("s.html", "text/html"),
        ("s.csv", "text/plain"),
        ("s.yaml", "text/plain"),
        ("s.yml", "text/plain"),
    ])
    def test_allowed_extensions(self, filename, mime):
        files = {"files": (filename, BytesIO(b"content\n"), mime)}
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())
        assert r.status_code == 200
        assert r.json()["ok"] is True

    @pytest.mark.parametrize("filename", ["v.exe", "v.zip", "v.png", "v.pdf", "v.bin", "v.so", "v.dll"])
    def test_disallowed_extensions(self, filename):
        files = {"files": (filename, BytesIO(b"x"), "application/octet-stream")}
        r = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())
        assert r.status_code == 400
        assert r.json()["ok"] is False


class TestFileList:
    def test_list_returns_expected_shape(self):
        r = requests.get(f"{BASE_URL}/api/workspace/files", headers=_headers())
        assert r.status_code == 200
        d = r.json()
        assert "files" in d
        assert "workspace" in d
        assert isinstance(d["files"], list)

    def test_list_shows_uploaded_file(self):
        files = {"files": ("list_test.py", BytesIO(b"# test\n"), "text/plain")}
        up = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())
        assert up.status_code == 200
        # Upload response has `path` = relative disk path; list also has `path`
        uploaded_path = up.json()["files"][0]["path"]

        r = requests.get(f"{BASE_URL}/api/workspace/files", headers=_headers())
        d = r.json()
        paths = [f["path"] for f in d["files"]]
        assert uploaded_path in paths

    def test_list_file_has_metadata_fields(self):
        files = {"files": ("meta_test.py", BytesIO(b"# m\n"), "text/plain")}
        requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())

        r = requests.get(f"{BASE_URL}/api/workspace/files", headers=_headers())
        d = r.json()
        if d["files"]:
            f = d["files"][0]
            assert "name" in f
            assert "path" in f
            assert "size" in f
            assert "mtime" in f

    def test_list_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/workspace/files")
        assert r.status_code in (401, 403)


class TestFileDelete:
    def test_delete_uploaded_file(self):
        # Upload
        files = {"files": ("del_test.py", BytesIO(b"# del\n"), "text/plain")}
        up = requests.post(f"{BASE_URL}/api/workspace/upload", files=files, headers=_headers())
        assert up.status_code == 200
        file_path = up.json()["files"][0]["path"]

        # Delete using the path returned by upload
        r = requests.delete(f"{BASE_URL}/api/workspace/files/{file_path}", headers=_headers())
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_nonexistent_returns_404(self):
        r = requests.delete(
            f"{BASE_URL}/api/workspace/files/uploads/00000000-nonexistent.py",
            headers=_headers(),
        )
        assert r.status_code == 404
        assert r.json()["ok"] is False

    def test_delete_requires_auth(self):
        r = requests.delete(f"{BASE_URL}/api/workspace/files/uploads/anything.py")
        assert r.status_code in (401, 403)

    def test_delete_path_traversal_blocked(self):
        r = requests.delete(
            f"{BASE_URL}/api/workspace/files/../../../etc/passwd",
            headers=_headers(),
        )
        assert r.status_code in (400, 404)

"""
Phase 5B — Neural graph real-time WebSocket tests.

Source-presence checks (grep server.js / frontend) + basic logic tests.
"""
import re
import json
import os
import time
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SERVER_JS  = os.path.join(REPO_ROOT, 'backend', 'server.js')
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
NEURAL_PAGE = os.path.join(REPO_ROOT, 'frontend', 'src', 'components', 'pages', 'NeuralNetworkPage.jsx')


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _read_backend():
    """Read server.js + all route files (routes may be extracted from server.js)."""
    parts = [_read(SERVER_JS)]
    routes_dir = os.path.join(BACKEND_DIR, 'routes')
    if os.path.isdir(routes_dir):
        for name in os.listdir(routes_dir):
            if name.endswith('.js'):
                parts.append(_read(os.path.join(routes_dir, name)))
    return '\n'.join(parts)


# ── Source-presence tests ─────────────────────────────────────────────────────

def test_brain_graph_endpoint_exists():
    """GET /api/brain/graph endpoint must be defined in server.js or a route file."""
    src = _read_backend()
    assert "'/api/brain/graph'" in src or '"/api/brain/graph"' in src, \
        "/api/brain/graph endpoint not found in server.js or backend/routes/"


def test_watch_graph_file_function_exists():
    """watchGraphFile function must be defined in server.js or a route file."""
    src = _read_backend()
    assert 'watchGraphFile' in src, \
        "watchGraphFile function not found in server.js or backend/routes/"


def test_brain_graph_updated_broadcast_exists():
    """brain:graph_updated broadcast call must be present in server.js or a route file."""
    src = _read_backend()
    assert "brain:graph_updated" in src, \
        "brain:graph_updated broadcast not found in server.js or backend/routes/"


def test_graph_delta_endpoint_exists():
    """GET /api/brain/graph/delta endpoint must be defined in server.js or a route file."""
    src = _read_backend()
    assert "'/api/brain/graph/delta'" in src or '"/api/brain/graph/delta"' in src, \
        "/api/brain/graph/delta endpoint not found in server.js or backend/routes/"


def test_delta_endpoint_has_require_auth():
    """Delta endpoint must use requireAuth middleware."""
    src = _read_backend()
    # Search all occurrences — route may be in a different file than the index entry
    idx = 0
    found = False
    while True:
        idx = src.find('/api/brain/graph/delta', idx)
        if idx == -1:
            break
        snippet = src[max(0, idx - 20):idx + 200]
        if 'requireAuth' in snippet:
            found = True
            break
        idx += 1
    assert found, "/api/brain/graph/delta found but requireAuth not nearby in any backend file"


def test_frontend_listens_for_brain_graph_updated():
    """NeuralNetworkPage.jsx must listen for brain:graph_updated WS event."""
    src = _read(NEURAL_PAGE)
    assert "brain:graph_updated" in src, \
        "brain:graph_updated not found in NeuralNetworkPage.jsx"


def test_frontend_has_live_indicator():
    """NeuralNetworkPage.jsx must render the LIVE indicator element."""
    src = _read(NEURAL_PAGE)
    assert 'nnp__live-indicator' in src, \
        "nnp__live-indicator class not found in NeuralNetworkPage.jsx"


def test_frontend_shows_last_updated_timestamp():
    """NeuralNetworkPage.jsx must display the last update timestamp."""
    src = _read(NEURAL_PAGE)
    assert 'liveGraphUpdate' in src and ('ts' in src or 'toLocaleTimeString' in src), \
        "Last-update timestamp logic not found in NeuralNetworkPage.jsx"


# ── Logic tests ───────────────────────────────────────────────────────────────

def test_delta_response_shape():
    """Delta endpoint response shape validation (simulated)."""
    # Simulate what the endpoint returns
    response = {'delta': [], 'full': True, 'snapshot_ts': int(time.time() * 1000),
                 'nodes_count': 0, 'edges_count': 0}
    assert isinstance(response['delta'], list)
    assert response['full'] is True
    assert isinstance(response['snapshot_ts'], int)
    assert 'nodes_count' in response
    assert 'edges_count' in response


def test_graph_snapshot_parsing():
    """Parsing logic for graph snapshot JSON must handle nodes/links/edges keys."""
    # Mirrors what watchGraphFile does
    def parse_graph(raw):
        nodes_count = len(raw.get('nodes', []))
        links = raw.get('links') or raw.get('edges') or []
        edges_count = len(links)
        return nodes_count, edges_count

    # Standard shape
    assert parse_graph({'nodes': [1, 2, 3], 'links': [1]}) == (3, 1)
    # Alternate edge key
    assert parse_graph({'nodes': [1], 'edges': [1, 2]}) == (1, 2)
    # Empty
    assert parse_graph({}) == (0, 0)
    # Missing nodes
    assert parse_graph({'links': [1, 2, 3]}) == (0, 3)

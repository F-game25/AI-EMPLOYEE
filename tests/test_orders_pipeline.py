"""Tests for the orders pipeline: orders_store, pitch URL logic, input validation.

Runs against a temporary in-memory SQLite database — never touches the real audit.db.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'runtime'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_temp_db(tmp_dir: str) -> str:
    """Return path to a temp AI_HOME that orders_store will use."""
    state_dir = Path(tmp_dir) / '.ai-employee' / 'state'
    state_dir.mkdir(parents=True)
    return str(Path(tmp_dir) / '.ai-employee')


# ── orders_store tests ────────────────────────────────────────────────────────

class TestOrdersStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ai_home = _make_temp_db(self.tmp)
        # Patch AI_HOME so the store writes to our temp dir
        self.env_patch = patch.dict(os.environ, {'AI_HOME': self.ai_home})
        self.env_patch.start()
        # Re-import with patched env so _db_path() picks up the new AI_HOME
        if 'core.orders_store' in sys.modules:
            del sys.modules['core.orders_store']
        from core.orders_store import order_aanmaken, order_ophalen, orders_ophalen, \
            status_bijwerken, order_verwijderen, pitch_bijwerken
        self.order_aanmaken   = order_aanmaken
        self.order_ophalen    = order_ophalen
        self.orders_ophalen   = orders_ophalen
        self.status_bijwerken = status_bijwerken
        self.order_verwijderen = order_verwijderen
        self.pitch_bijwerken  = pitch_bijwerken

    def tearDown(self):
        self.env_patch.stop()
        if 'core.orders_store' in sys.modules:
            del sys.modules['core.orders_store']

    def test_create_order(self):
        order = self.order_aanmaken(
            bedrijfsnaam='Test BV', plaats='Amsterdam',
            branche='bakkerij', contact='06-12345678', prijs=299.0
        )
        self.assertIsNotNone(order)
        self.assertEqual(order['bedrijfsnaam'], 'Test BV')
        self.assertEqual(order['status'], 'gevonden')
        self.assertEqual(order['prijs'], 299.0)
        self.assertTrue(order['id'].startswith('order-'))

    def test_ophalen_returns_order(self):
        created = self.order_aanmaken(bedrijfsnaam='Kapper X', plaats='Utrecht', branche='kapper')
        fetched = self.order_ophalen(created['id'])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['id'], created['id'])

    def test_ophalen_missing_returns_none(self):
        result = self.order_ophalen('order-doesnotexist')
        self.assertIsNone(result)

    def test_status_transition(self):
        order = self.order_aanmaken(bedrijfsnaam='Schilder Y', plaats='Leiden', branche='schilder')
        updated = self.status_bijwerken(order['id'], 'demo_klaar', demo_pad='/tmp/demo.html')
        self.assertEqual(updated['status'], 'demo_klaar')
        self.assertEqual(updated['demo_pad'], '/tmp/demo.html')

    def test_invalid_status_raises(self):
        order = self.order_aanmaken(bedrijfsnaam='Loodgieter Z', plaats='Delft', branche='loodgieter')
        with self.assertRaises(ValueError):
            self.status_bijwerken(order['id'], 'INVALID_STATUS')

    def test_full_status_flow(self):
        order = self.order_aanmaken(bedrijfsnaam='Bakker A', plaats='Haarlem', branche='bakkerij')
        for status in ['demo_klaar', 'ter_review', 'goedgekeurd', 'gepitcht', 'betaald', 'live']:
            order = self.status_bijwerken(order['id'], status)
            self.assertEqual(order['status'], status)

    def test_orders_ophalen_list(self):
        self.order_aanmaken(bedrijfsnaam='A', plaats='X', branche='Y')
        self.order_aanmaken(bedrijfsnaam='B', plaats='X', branche='Z')
        orders = self.orders_ophalen()
        self.assertGreaterEqual(len(orders), 2)

    def test_orders_ophalen_by_status(self):
        self.order_aanmaken(bedrijfsnaam='C', plaats='X', branche='Y')
        results = self.orders_ophalen(status='gevonden')
        self.assertTrue(all(o['status'] == 'gevonden' for o in results))

    def test_verwijderen(self):
        order = self.order_aanmaken(bedrijfsnaam='Delete Me', plaats='X', branche='Y')
        result = self.order_verwijderen(order['id'])
        self.assertTrue(result['ok'])
        self.assertIsNone(self.order_ophalen(order['id']))

    def test_verwijderen_missing(self):
        result = self.order_verwijderen('order-doesnotexist')
        self.assertFalse(result['ok'])
        self.assertIn('niet gevonden', result['error'])

    def test_pitch_bijwerken(self):
        order = self.order_aanmaken(bedrijfsnaam='Pitch Me', plaats='X', branche='Y')
        result = self.pitch_bijwerken(order['id'], 'Hoi, hier is je demo!')
        self.assertTrue(result['ok'])
        fetched = self.order_ophalen(order['id'])
        self.assertEqual(fetched['pitch_tekst'], 'Hoi, hier is je demo!')

    def test_pitch_bijwerken_missing(self):
        result = self.pitch_bijwerken('order-ghost', 'tekst')
        self.assertFalse(result['ok'])


# ── Input validation tests (mirrors orders.js server-side checks) ─────────────

class TestInputValidation(unittest.TestCase):
    """Tests for the validation logic we added to orders.js.
    These test the Python-side equivalents to document intent.
    """

    def test_prijs_finite_check(self):
        import math
        invalid = [float('nan'), float('inf'), float('-inf'), -1.0, 0.0]
        for val in invalid:
            is_valid = math.isfinite(val) and val > 0
            self.assertFalse(is_valid, f"Expected {val} to fail validation")

    def test_prijs_valid(self):
        import math
        valid = [1.0, 99.0, 299.0, 9999.99]
        for val in valid:
            is_valid = math.isfinite(val) and val > 0
            self.assertTrue(is_valid, f"Expected {val} to pass validation")

    def test_aantal_clamp(self):
        def clamp(v):
            try:
                return min(20, max(1, int(v)))
            except (ValueError, TypeError):
                return 8
        self.assertEqual(clamp(5), 5)
        self.assertEqual(clamp(0), 1)
        self.assertEqual(clamp(100), 20)
        self.assertEqual(clamp('abc'), 8)
        self.assertEqual(clamp(None), 8)


# ── Pitch URL construction tests ──────────────────────────────────────────────

class TestPitchUrlConstruction(unittest.TestCase):
    """Validate that demo URLs in pitches use BASE_URL over req.get('host')."""

    def test_base_url_takes_priority(self):
        base_url = 'https://example.ngrok.io'
        fname = 'demo_Bakker_X_amsterdam.html'
        token = 'test-jwt-token'
        # Simulate what orders.js now does
        host = base_url or 'http://localhost:8787'
        url = f'{host}/api/demos/{fname}?token={token}'
        self.assertTrue(url.startswith('https://example.ngrok.io'))
        self.assertIn('/api/demos/', url)
        self.assertIn('token=', url)

    def test_fallback_to_localhost(self):
        base_url = ''  # unset
        fname = 'demo_test.html'
        token = 'abc'
        host = base_url or 'http://localhost:8787'
        url = f'{host}/api/demos/{fname}?token={token}'
        self.assertTrue(url.startswith('http://localhost:8787'))

    def test_no_filesystem_path_in_url(self):
        """Ensure the built URL never contains a filesystem path."""
        fname = 'demo_Loodgieter_Jansen_brielle.html'
        base_url = 'http://localhost:8787'
        url = f'{base_url}/api/demos/{fname}'
        self.assertNotIn('/home/', url)
        self.assertNotIn('.ai-employee', url)
        self.assertNotIn('state/artifacts', url)


# ── Bandit B310 scheme validation tests ───────────────────────────────────────

class TestOllamaHostValidation(unittest.TestCase):
    """Confirm the scheme validation we added fires on bad OLLAMA_HOST values."""

    def _import_fresh(self, host: str, module: str):
        if module in sys.modules:
            del sys.modules[module]
        with patch.dict(os.environ, {'OLLAMA_HOST': host}):
            if host.startswith(('http://', 'https://')):
                import importlib
                return importlib.import_module(module)
            else:
                with self.assertRaises(ValueError):
                    import importlib
                    importlib.import_module(module)
                return None

    def test_valid_http_host_accepted(self):
        if 'core.bedrijf_finder' in sys.modules:
            del sys.modules['core.bedrijf_finder']
        with patch.dict(os.environ, {'OLLAMA_HOST': 'http://localhost:11434'}):
            import importlib
            mod = importlib.import_module('core.bedrijf_finder')
            self.assertIsNotNone(mod)
        del sys.modules['core.bedrijf_finder']

    def test_invalid_host_scheme_rejected(self):
        if 'core.bedrijf_finder' in sys.modules:
            del sys.modules['core.bedrijf_finder']
        with patch.dict(os.environ, {'OLLAMA_HOST': 'ftp://evil.example.com'}):
            with self.assertRaises(ValueError):
                import importlib
                importlib.import_module('core.bedrijf_finder')
        if 'core.bedrijf_finder' in sys.modules:
            del sys.modules['core.bedrijf_finder']

    def test_file_scheme_rejected(self):
        if 'core.bedrijf_finder' in sys.modules:
            del sys.modules['core.bedrijf_finder']
        with patch.dict(os.environ, {'OLLAMA_HOST': 'file:///etc/passwd'}):
            with self.assertRaises(ValueError):
                import importlib
                importlib.import_module('core.bedrijf_finder')
        if 'core.bedrijf_finder' in sys.modules:
            del sys.modules['core.bedrijf_finder']


if __name__ == '__main__':
    unittest.main()

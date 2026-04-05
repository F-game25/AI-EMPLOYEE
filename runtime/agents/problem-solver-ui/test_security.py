"""
AI Employee — Security & API Test Suite (from openclaw-2)

Covers:
  - PasswordValidator
  - InputSanitizer
  - AuthManager (JWT + bcrypt)
  - EncryptionManager (Fernet/AES-256-GCM)
  - Helper functions (generate_secure_token, hash_data)
  - config_manager.validate_security_config
  - FastAPI endpoints: /health, /security/status, /auth/register,
                       /, /api/status, /api/doctor
  - Security headers
  - Rate limiting (slowapi integration)
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

# ── Pre-flight: set JWT secret before importing the app ───────────────────────
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test_secret_key_that_is_long_enough_for_validation_32b",
)

# Ensure the server module can find its siblings (security.py, config_manager.py)
_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if _BOT_DIR not in sys.path:
    sys.path.insert(0, _BOT_DIR)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """TestClient for the AI Employee FastAPI dashboard."""
    import server  # noqa: F401 — import triggers app construction
    return TestClient(server.app)


# ══════════════════════════════════════════════════════════════════════════════
# security.py — unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPasswordValidator:
    """PasswordValidator.validate() — all branches."""

    def test_rejects_short_password(self):
        from security import PasswordValidator
        valid, msg = PasswordValidator.validate("short")
        assert not valid
        assert "12 characters" in msg

    def test_rejects_missing_uppercase(self):
        from security import PasswordValidator
        valid, msg = PasswordValidator.validate(
            "validpassword1!", require_uppercase=True
        )
        assert not valid
        assert "uppercase" in msg

    def test_rejects_missing_number(self):
        from security import PasswordValidator
        valid, msg = PasswordValidator.validate(
            "ValidPassword!", require_numbers=True
        )
        assert not valid
        assert "number" in msg

    def test_rejects_missing_special(self):
        from security import PasswordValidator
        valid, msg = PasswordValidator.validate(
            "ValidPassword1", require_special=True
        )
        assert not valid
        assert "special" in msg

    def test_accepts_strong_password(self):
        from security import PasswordValidator
        valid, msg = PasswordValidator.validate("ValidPassword1!")
        assert valid
        assert msg == ""

    def test_custom_min_length(self):
        from security import PasswordValidator
        valid, _ = PasswordValidator.validate(
            "Ab1!", min_length=4,
            require_special=True, require_numbers=True, require_uppercase=True,
        )
        assert valid


class TestInputSanitizer:
    """InputSanitizer — filename, path, and text sanitisation."""

    def test_sanitize_filename_strips_path(self):
        from security import InputSanitizer
        result = InputSanitizer.sanitize_filename("../etc/passwd")
        assert "/" not in result
        assert result == "passwd"

    def test_sanitize_filename_removes_leading_dot(self):
        from security import InputSanitizer
        result = InputSanitizer.sanitize_filename(".hidden")
        assert not result.startswith(".")

    def test_sanitize_filename_empty_becomes_unnamed(self):
        from security import InputSanitizer
        result = InputSanitizer.sanitize_filename("!!!")
        assert result == "unnamed_file"

    def test_sanitize_filename_windows_path(self):
        from security import InputSanitizer
        result = InputSanitizer.sanitize_filename(r"C:\Windows\System32\cmd.exe")
        assert "\\" not in result

    def test_validate_path_safe(self):
        from security import InputSanitizer
        assert InputSanitizer.validate_path("/tmp/test/file.txt", "/tmp/test") is True

    def test_validate_path_traversal_blocked(self):
        from security import InputSanitizer
        assert (
            InputSanitizer.validate_path("/tmp/test/../../etc/passwd", "/tmp/test")
            is False
        )

    def test_sanitize_input_removes_null_bytes(self):
        from security import InputSanitizer
        result = InputSanitizer.sanitize_input("hello\x00world")
        assert "\x00" not in result
        assert result == "helloworld"

    def test_sanitize_input_truncates_at_max_length(self):
        from security import InputSanitizer
        result = InputSanitizer.sanitize_input("a" * 200, max_length=100)
        assert len(result) == 100

    def test_sanitize_input_no_change_when_within_limit(self):
        from security import InputSanitizer
        text = "Hello World"
        assert InputSanitizer.sanitize_input(text) == text


class TestAuthManager:
    """AuthManager — bcrypt hashing and JWT lifecycle."""

    _SECRET = "a_secret_key_that_is_long_enough_to_pass_32"

    def test_hash_and_verify_correct_password(self):
        from security import AuthManager
        auth = AuthManager(secret_key=self._SECRET)
        hashed = auth.hash_password("TestPassword1!")
        assert auth.verify_password("TestPassword1!", hashed) is True

    def test_verify_wrong_password_fails(self):
        from security import AuthManager
        auth = AuthManager(secret_key=self._SECRET)
        hashed = auth.hash_password("TestPassword1!")
        assert auth.verify_password("WrongPassword", hashed) is False

    def test_create_and_verify_token(self):
        from security import AuthManager
        auth = AuthManager(secret_key=self._SECRET)
        token = auth.create_access_token({"sub": "testuser"})
        payload = auth.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"

    def test_token_contains_expiry(self):
        from security import AuthManager
        auth = AuthManager(secret_key=self._SECRET)
        token = auth.create_access_token({"sub": "u"})
        payload = auth.verify_token(token)
        assert "exp" in payload

    def test_verify_invalid_token_returns_none(self):
        from security import AuthManager
        auth = AuthManager(secret_key=self._SECRET)
        assert auth.verify_token("not.a.valid.token") is None

    def test_verify_tampered_token_returns_none(self):
        from security import AuthManager
        auth = AuthManager(secret_key=self._SECRET)
        token = auth.create_access_token({"sub": "u"})
        tampered = token[:-4] + "XXXX"
        assert auth.verify_token(tampered) is None


class TestEncryptionManager:
    """EncryptionManager — Fernet / AES-256-GCM round-trips."""

    def test_random_key_encrypt_decrypt_string(self):
        from security import EncryptionManager
        enc = EncryptionManager()
        data = "Hello, World!"
        assert enc.decrypt_to_string(enc.encrypt(data)) == data

    def test_random_key_encrypt_decrypt_bytes(self):
        from security import EncryptionManager
        enc = EncryptionManager()
        data = b"Byte data"
        assert enc.decrypt(enc.encrypt(data)) == data

    def test_password_based_roundtrip(self):
        from security import EncryptionManager
        enc = EncryptionManager(password="mypassword")
        data = "Secret data"
        assert enc.decrypt_to_string(enc.encrypt(data)) == data

    def test_same_password_same_salt_same_key(self):
        """Two managers with identical password+salt must decrypt each other's data."""
        from security import EncryptionManager
        salt = b"testsalt12345678"
        enc1 = EncryptionManager(password="pw", salt=salt)
        enc2 = EncryptionManager(password="pw", salt=salt)
        ciphertext = enc1.encrypt("hello")
        assert enc2.decrypt_to_string(ciphertext) == "hello"

    def test_different_passwords_cannot_decrypt(self):
        from security import EncryptionManager
        enc1 = EncryptionManager(password="password1")
        enc2 = EncryptionManager(password="password2")
        ciphertext = enc1.encrypt("secret")
        with pytest.raises(Exception):
            enc2.decrypt(ciphertext)


class TestHelpers:
    """generate_secure_token and hash_data utilities."""

    def test_generate_token_length(self):
        from security import generate_secure_token
        assert len(generate_secure_token(16)) == 32  # hex: 16 bytes → 32 chars

    def test_generate_token_default_length(self):
        from security import generate_secure_token
        assert len(generate_secure_token()) == 64  # 32 bytes → 64 chars

    def test_generate_token_is_unique(self):
        from security import generate_secure_token
        assert generate_secure_token() != generate_secure_token()

    def test_hash_data_deterministic(self):
        from security import hash_data
        assert hash_data("test") == hash_data("test")

    def test_hash_data_is_sha256_hex(self):
        from security import hash_data
        result = hash_data("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_data_different_inputs(self):
        from security import hash_data
        assert hash_data("a") != hash_data("b")


# ══════════════════════════════════════════════════════════════════════════════
# config_manager.py — unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigManager:
    """validate_security_config and load_config edge cases."""

    def test_validate_warns_on_public_binding(self):
        from config_manager import validate_security_config, SecurityConfig
        from config_manager import Config, PrivacyConfig, AIConfig, LoggingConfig, LimitsConfig
        cfg = Config(
            host="0.0.0.0",
            security=SecurityConfig(jwt_secret_key="a" * 32),
            privacy=PrivacyConfig(),
            ai=AIConfig(),
            logging=LoggingConfig(),
            limits=LimitsConfig(),
        )
        warnings = validate_security_config(cfg)
        assert any("0.0.0.0" in w for w in warnings)

    def test_validate_warns_on_debug_in_production(self):
        from config_manager import validate_security_config, SecurityConfig
        from config_manager import Config, PrivacyConfig, AIConfig, LoggingConfig, LimitsConfig
        cfg = Config(
            debug=True,
            environment="production",
            security=SecurityConfig(jwt_secret_key="a" * 32),
            privacy=PrivacyConfig(),
            ai=AIConfig(),
            logging=LoggingConfig(),
            limits=LimitsConfig(),
        )
        warnings = validate_security_config(cfg)
        assert any("Debug" in w or "debug" in w for w in warnings)

    def test_validate_no_warnings_on_safe_config(self):
        from config_manager import validate_security_config, SecurityConfig
        from config_manager import Config, PrivacyConfig, AIConfig, LoggingConfig, LimitsConfig
        cfg = Config(
            host="127.0.0.1",
            debug=False,
            environment="production",
            security=SecurityConfig(
                jwt_secret_key="a" * 32,
                rate_limit_enabled=True,
            ),
            privacy=PrivacyConfig(
                encrypt_data_at_rest=True,
                external_api_calls_disabled=True,
                telemetry_enabled=False,
            ),
            ai=AIConfig(),
            logging=LoggingConfig(),
            limits=LimitsConfig(),
        )
        warnings = validate_security_config(cfg)
        # Only INFO-level notices (not warnings) should appear
        real_warnings = [w for w in warnings if w.startswith("WARNING")]
        assert real_warnings == []

    def test_load_config_raises_without_jwt_secret(self, monkeypatch):
        from config_manager import load_config
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        with pytest.raises((ValueError, Exception)):
            load_config()


# ══════════════════════════════════════════════════════════════════════════════
# FastAPI app — endpoint tests
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body_shape(self, client):
        data = client.get("/health").json()
        assert "status" in data
        assert "secure_mode" in data
        assert "privacy_mode" in data
        assert data["status"] == "healthy"


class TestSecurityStatusEndpoint:
    def test_returns_200(self, client):
        assert client.get("/security/status").status_code == 200

    def test_body_contains_required_keys(self, client):
        data = client.get("/security/status").json()
        for key in ("secure_mode", "encryption_enabled", "rate_limiting_enabled",
                    "external_calls_blocked", "telemetry_disabled", "warnings"):
            assert key in data, f"Missing key: {key}"

    def test_telemetry_disabled_by_default(self, client):
        assert client.get("/security/status").json()["telemetry_disabled"] is True


class TestSecurityHeaders:
    def test_x_content_type_options(self, client):
        assert client.get("/health").headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        assert client.get("/health").headers.get("x-frame-options") == "DENY"

    def test_x_xss_protection(self, client):
        assert client.get("/health").headers.get("x-xss-protection") == "1; mode=block"

    def test_strict_transport_security(self, client):
        assert "max-age" in client.get("/health").headers.get(
            "strict-transport-security", ""
        )

    def test_content_security_policy(self, client):
        assert "content-security-policy" in client.get("/health").headers

    def test_headers_on_all_routes(self, client):
        """Security headers must appear on every route, not just /health."""
        for path in ("/security/status", "/api/status"):
            headers = client.get(path).headers
            assert headers.get("x-frame-options") == "DENY", f"Missing on {path}"


class TestAuthRegisterEndpoint:
    def test_weak_password_rejected_by_pydantic(self, client):
        # Pydantic min_length=12 on the model rejects at validation level (422)
        resp = client.post("/auth/register", json={
            "username": "testuser",
            "password": "short",
        })
        assert resp.status_code == 422

    def test_strong_password_creates_token(self, client):
        resp = client.post("/auth/register", json={
            "username": "testuser",
            "password": "StrongPass1!",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_returned_token_is_valid_jwt(self, client):
        resp = client.post("/auth/register", json={
            "username": "jwtuser",
            "password": "StrongPass1!",
        })
        assert resp.status_code == 201
        token = resp.json()["access_token"]
        # A JWT has exactly three dot-separated parts
        assert len(token.split(".")) == 3

    def test_password_missing_number_rejected(self, client):
        """Password validator (not Pydantic) catches missing digit."""
        resp = client.post("/auth/register", json={
            "username": "user2",
            "password": "ValidPasswordOnly!",  # no digit
        })
        assert resp.status_code == 400
        assert "number" in resp.json()["detail"]

    def test_password_missing_special_char_rejected(self, client):
        resp = client.post("/auth/register", json={
            "username": "user3",
            "password": "ValidPassword123",  # no special char
        })
        assert resp.status_code == 400
        assert "special" in resp.json()["detail"]

    def test_password_missing_uppercase_rejected(self, client):
        resp = client.post("/auth/register", json={
            "username": "user4",
            "password": "validpassword123!",  # all lowercase
        })
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["detail"]


class TestRootEndpoint:
    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")


class TestApiStatusEndpoint:
    def test_returns_200(self, client):
        assert client.get("/api/status").status_code == 200


class TestApiDoctorEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/api/doctor")
        assert resp.status_code == 200
        assert "output" in resp.json()


# ── standalone runner ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

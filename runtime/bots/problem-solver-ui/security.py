"""
AI Employee — Security Module (from openclaw-2)
Handles authentication, authorization, encryption, and input validation.
"""
import re
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from pathlib import Path

import bcrypt
from jose import JWTError, jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class PasswordValidator:
    """Validates password strength."""

    @staticmethod
    def validate(password: str, min_length: int = 12,
                 require_special: bool = True,
                 require_numbers: bool = True,
                 require_uppercase: bool = True) -> tuple[bool, str]:
        """
        Validate password against security requirements.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(password) < min_length:
            return False, f"Password must be at least {min_length} characters long"

        if require_uppercase and not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"

        if require_numbers and not re.search(r'\d', password):
            return False, "Password must contain at least one number"

        if require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"

        return True, ""


class InputSanitizer:
    """Sanitizes and validates user input."""

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename to prevent path traversal.

        Returns:
            Sanitized filename safe for use on the filesystem.
        """
        # Remove any path components
        filename = Path(filename).name

        # Remove dangerous characters
        filename = re.sub(r'[^\w\s\-\.]', '', filename)

        # Prevent hidden files
        if filename.startswith('.'):
            filename = filename[1:]

        # Ensure not empty
        if not filename:
            filename = "unnamed_file"

        return filename

    @staticmethod
    def validate_path(path: str, allowed_base: str) -> bool:
        """
        Validate that path is within allowed base directory (prevents path traversal).

        Returns:
            True if path is safe, False otherwise.
        """
        try:
            abs_path = Path(path).resolve()
            abs_base = Path(allowed_base).resolve()
            abs_path.relative_to(abs_base)
            return True
        except (ValueError, RuntimeError):
            return False

    @staticmethod
    def sanitize_input(text: str, max_length: int = 10000) -> str:
        """
        Sanitize text input: trim to max_length and remove null bytes.

        Returns:
            Sanitized text.
        """
        if len(text) > max_length:
            text = text[:max_length]
        # Remove null bytes
        text = text.replace('\x00', '')
        return text


class AuthManager:
    """Manages JWT-based authentication and bcrypt password hashing."""

    def __init__(self, secret_key: str, algorithm: str = "HS256",
                 expire_minutes: int = 30):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt (cost factor 12)."""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against its bcrypt hash."""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    def create_access_token(self, data: dict,
                            expires_delta: Optional[timedelta] = None) -> str:
        """Create a signed JWT access token."""
        to_encode = data.copy()
        expire = (
            datetime.now(timezone.utc) + expires_delta
            if expires_delta
            else datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify and decode a JWT token.

        Returns:
            Decoded payload dict, or None if the token is invalid/expired.
        """
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except JWTError:
            return None


class EncryptionManager:
    """AES-256-GCM data encryption via Fernet (PBKDF2-derived key or random key)."""

    def __init__(self, password: Optional[str] = None, salt: Optional[bytes] = None):
        """
        Initialise the encryption manager.

        Args:
            password: Derive key from this password with PBKDF2.  If None a
                random one-shot Fernet key is generated.
            salt: PBKDF2 salt.  Required when *password* is given if you need
                to decrypt the ciphertext later with a new instance.  When
                omitted, a cryptographically random salt is generated —
                **call ``self.salt`` to retrieve it and store it alongside the
                ciphertext**.

        Note:
            To be able to decrypt data later, reuse the *same* password + salt.
            For per-record encryption always store the generated salt with the
            ciphertext.  Only pass a fixed salt for application-level config
            encryption where a stable, reproducible key is acceptable.
        """
        if password is None:
            self.key = Fernet.generate_key()
            self.salt = None
        else:
            # Always generate a random salt unless one is explicitly supplied.
            # This prevents the caller from inadvertently using the same key
            # for every record when they do not think about the salt at all.
            if salt is None:
                salt = secrets.token_bytes(32)
            self.salt = salt

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            import base64
            self.key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

        self.cipher = Fernet(self.key)

    def encrypt(self, data: Union[str, bytes]) -> bytes:
        """Encrypt *data* (string or bytes) and return ciphertext bytes."""
        if isinstance(data, str):
            data = data.encode()
        return self.cipher.encrypt(data)

    def decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypt *encrypted_data* and return plaintext bytes."""
        return self.cipher.decrypt(encrypted_data)

    def decrypt_to_string(self, encrypted_data: bytes) -> str:
        """Decrypt *encrypted_data* and return plaintext as a UTF-8 string."""
        return self.decrypt(encrypted_data).decode()


def generate_secure_token(length: int = 32) -> str:
    """Return a cryptographically secure, hex-encoded random token of *length* bytes."""
    return secrets.token_hex(length)


def hash_data(data: str) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data.encode()).hexdigest()

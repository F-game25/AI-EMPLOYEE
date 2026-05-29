"""Field-level encryption (FLE) — AES-256-GCM, per-tenant keys."""

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

_VERSION_PREFIX = "fle1:"
_NONCE_LEN = 12
_TAG_LEN = 16  # GCM tag is always 16 bytes; AESGCM appends it to ciphertext


def derive_tenant_key(tenant_id: str, master_key: bytes) -> bytes:
    """HKDF-SHA256 derivation of a 32-byte tenant-specific key."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"aie-fle-v1-" + tenant_id.encode(),
    ).derive(master_key)


def encrypt(plaintext: str, key: bytes) -> str:
    """AES-256-GCM encrypt.

    Returns base64(nonce + tag + ciphertext) prefixed with 'fle1:'.
    The cryptography library appends the 16-byte GCM tag to the
    ciphertext, so the stored layout is: nonce(12) | ciphertext+tag.
    """
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt returns ciphertext || tag (tag appended by the library)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # Reorder to nonce | tag | ciphertext for explicit layout clarity
    tag = ct_with_tag[-_TAG_LEN:]
    ct = ct_with_tag[:-_TAG_LEN]
    blob = nonce + tag + ct
    return _VERSION_PREFIX + base64.b64encode(blob).decode()


def decrypt(ciphertext_b64: str, key: bytes) -> str:
    """AES-256-GCM decrypt.

    Raises ValueError on missing version prefix or authentication failure.
    """
    if not ciphertext_b64.startswith(_VERSION_PREFIX):
        raise ValueError(f"Missing version prefix '{_VERSION_PREFIX}'")
    raw = base64.b64decode(ciphertext_b64[len(_VERSION_PREFIX):])
    if len(raw) < _NONCE_LEN + _TAG_LEN:
        raise ValueError("Ciphertext blob too short")
    nonce = raw[:_NONCE_LEN]
    tag = raw[_NONCE_LEN: _NONCE_LEN + _TAG_LEN]
    ct = raw[_NONCE_LEN + _TAG_LEN:]
    aesgcm = AESGCM(key)
    try:
        # Reconstruct ciphertext+tag layout expected by the library
        plaintext_bytes = aesgcm.decrypt(nonce, ct + tag, None)
    except Exception as exc:
        raise ValueError("Decryption failed: authentication tag mismatch") from exc
    return plaintext_bytes.decode()


def get_master_key() -> bytes:
    """Read FLE_MASTER_KEY from environment (32-byte hex string).

    Raises RuntimeError if the variable is unset or not exactly 64 hex chars.
    """
    raw = os.environ.get("FLE_MASTER_KEY", "")
    if not raw:
        raise RuntimeError("FLE_MASTER_KEY env var is not set")
    if len(raw) != 64:
        raise RuntimeError(
            f"FLE_MASTER_KEY must be 64 hex characters (32 bytes); got {len(raw)}"
        )
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError("FLE_MASTER_KEY is not valid hex") from exc


@lru_cache(maxsize=256)
def get_tenant_key(tenant_id: str) -> bytes:
    """Derive and cache a tenant-specific AES key."""
    return derive_tenant_key(tenant_id, get_master_key())

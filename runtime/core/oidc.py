"""OIDC federation — validate tokens from external IdPs alongside built-in auth."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider dataclass
# ---------------------------------------------------------------------------

@dataclass
class OIDCProvider:
    name: str
    issuer: str
    jwks_uri: str
    client_id: str
    audience: str
    tenant_id_claim: str = "org_id"
    role_claim: str = "role"


# ---------------------------------------------------------------------------
# JWKS cache entry — simple TTL wrapper (30 s)
# ---------------------------------------------------------------------------

_JWKS_TTL = 30  # seconds

@dataclass
class _JWKSEntry:
    keys: dict
    fetched_at: float = field(default_factory=time.monotonic)

    def expired(self) -> bool:
        return (time.monotonic() - self.fetched_at) > _JWKS_TTL


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class OIDCRegistry:
    def __init__(self) -> None:
        self._providers: list[OIDCProvider] = []
        self._cache: dict[str, _JWKSEntry] = {}

    def register(self, provider: OIDCProvider) -> None:
        self._providers.append(provider)
        logger.info("[OIDC] registered provider '%s' (issuer=%s)", provider.name, provider.issuer)

    # ------------------------------------------------------------------
    # JWKS fetch with 30-second in-process cache
    # ------------------------------------------------------------------

    def _fetch_jwks(self, jwks_uri: str) -> dict:
        entry = self._cache.get(jwks_uri)
        if entry and not entry.expired():
            return entry.keys
        try:
            req = urllib.request.Request(jwks_uri, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            logger.warning("[OIDC] JWKS fetch failed for %s: %s", jwks_uri, exc)
            # Return stale cache on transient errors rather than hard-failing
            if entry:
                return entry.keys
            raise
        self._cache[jwks_uri] = _JWKSEntry(keys=data)
        return data

    # ------------------------------------------------------------------
    # Token validation — tries every registered provider
    # ------------------------------------------------------------------

    def validate_token(self, token: str) -> Optional[dict[str, Any]]:
        """Return decoded payload dict if token is valid for any provider, else None."""
        try:
            import jwt as pyjwt  # PyJWT
        except ImportError:
            logger.error("[OIDC] PyJWT not installed — cannot validate OIDC tokens")
            return None

        for provider in self._providers:
            try:
                jwks = self._fetch_jwks(provider.jwks_uri)
                # Build a JWKSClient-compatible key set inline
                from jwt.algorithms import RSAAlgorithm, ECAlgorithm  # type: ignore[import]

                # Decode header to find kid
                unverified_header = pyjwt.get_unverified_header(token)
                kid = unverified_header.get("kid")
                alg = unverified_header.get("alg", "RS256")

                # Locate matching key
                public_key = None
                for jwk in jwks.get("keys", []):
                    if kid and jwk.get("kid") != kid:
                        continue
                    kty = jwk.get("kty", "")
                    if kty == "RSA":
                        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
                    elif kty == "EC":
                        public_key = ECAlgorithm.from_jwk(json.dumps(jwk))
                    if public_key:
                        break

                if public_key is None:
                    logger.debug("[OIDC] no matching key for provider '%s' (kid=%s)", provider.name, kid)
                    continue

                payload = pyjwt.decode(
                    token,
                    public_key,
                    algorithms=["RS256", "ES256"],
                    audience=provider.audience,
                    issuer=provider.issuer,
                    options={"verify_exp": True},
                )
                # Normalize to internal claim shape
                return _normalize_payload(payload, provider)

            except pyjwt.ExpiredSignatureError:
                logger.debug("[OIDC] expired token for provider '%s'", provider.name)
            except pyjwt.InvalidTokenError as exc:
                logger.debug("[OIDC] invalid token for provider '%s': %s", provider.name, exc)
            except Exception as exc:
                logger.warning("[OIDC] unexpected error validating against '%s': %s", provider.name, exc)

        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_payload(payload: dict, provider: OIDCProvider) -> dict[str, Any]:
    """Map IdP-specific claims to the internal token schema."""
    tenant_id = payload.get(provider.tenant_id_claim) or payload.get("tenant_id") or ""
    role = payload.get(provider.role_claim) or payload.get("role") or "user"
    return {
        "sub": payload.get("sub", ""),
        "tenant_id": tenant_id,
        "role": role,
        "type": "oidc",
        "provider": provider.name,
        # Pass through email if present (useful for audit logs)
        "email": payload.get("email", ""),
    }


# ---------------------------------------------------------------------------
# Bootstrap registry from environment
# ---------------------------------------------------------------------------

def load_providers_from_env() -> OIDCRegistry:
    """
    Read OIDC_PROVIDERS env var (JSON array of OIDCProvider configs) and
    return a populated OIDCRegistry.  Returns an empty registry — built-in
    auth continues to work — if the var is absent or malformed.
    """
    registry = OIDCRegistry()
    raw = os.environ.get("OIDC_PROVIDERS", "").strip()
    if not raw:
        return registry
    try:
        providers_cfg = json.loads(raw)
        if not isinstance(providers_cfg, list):
            raise ValueError("OIDC_PROVIDERS must be a JSON array")
        for cfg in providers_cfg:
            registry.register(OIDCProvider(
                name=cfg["name"],
                issuer=cfg["issuer"],
                jwks_uri=cfg["jwks_uri"],
                client_id=cfg["client_id"],
                audience=cfg["audience"],
                tenant_id_claim=cfg.get("tenant_id_claim", "org_id"),
                role_claim=cfg.get("role_claim", "role"),
            ))
    except Exception as exc:
        logger.error("[OIDC] failed to parse OIDC_PROVIDERS: %s — OIDC disabled", exc)
    return registry


# ---------------------------------------------------------------------------
# Module-level singleton — initialised once at import time
# ---------------------------------------------------------------------------

_oidc_registry: OIDCRegistry = load_providers_from_env()


# ---------------------------------------------------------------------------
# FastAPI dependency — OIDC or built-in auth
# ---------------------------------------------------------------------------

def _get_oidc_registry() -> OIDCRegistry:
    """Indirection so tests can monkey-patch the registry."""
    return _oidc_registry


async def oidc_or_builtin_auth(request: "Request") -> dict:  # type: ignore[name-defined]
    """
    FastAPI dependency: accepts built-in JWT **or** a token from a registered
    OIDC provider.

    Resolution order:
    1. Try built-in JWT validation (calls require_auth_optional).
    2. If that returns a payload → return it.
    3. Extract Bearer token and try every registered OIDC provider.
    4. If valid → return normalised payload.
    5. Otherwise raise HTTP 401.
    """
    # Lazy import to avoid circular dependency at module import time.
    from fastapi import HTTPException, status
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    # --- built-in path ---
    builtin = await _require_auth_optional(request)
    if builtin is not None:
        return builtin

    # --- OIDC path ---
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header[7:]
    payload = _get_oidc_registry().validate_token(token)
    if payload is not None:
        return payload

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _require_auth_optional(request: "Request") -> Optional[dict]:  # type: ignore[name-defined]
    """
    Built-in JWT validation that returns None instead of raising 401.
    Mirrors the logic in require_auth but is non-fatal.
    """
    try:
        # Import server-local helpers without creating a circular import.
        # server.py inserts its own directory into sys.path, so we resolve
        # via the calling module's globals at runtime.
        import importlib, sys
        # server module may be loaded under different names; find it.
        server_mod = None
        for mod_name, mod in list(sys.modules.items()):
            if hasattr(mod, "_decode_any_token") and hasattr(mod, "_bearer_scheme"):
                server_mod = mod
                break
        if server_mod is None:
            return None

        bearer_scheme = server_mod._bearer_scheme
        decode = server_mod._decode_any_token
        is_revoked = server_mod._is_jti_revoked
        fp_func = server_mod._request_fingerprint
        require_auth_flag = getattr(server_mod, "_REQUIRE_AUTH", True)

        if not require_auth_flag:
            return {"sub": "anonymous", "tenant_id": "", "role": "admin", "type": "builtin"}

        # Manually extract credentials from request (same as HTTPBearer)
        auth_header: str = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token_str = auth_header[7:]
        if not token_str:
            return None

        payload = decode(token_str)
        if payload is None:
            return None
        if is_revoked(payload):
            return None

        # Fingerprint check
        expected_fp = payload.get("fp")
        if isinstance(expected_fp, str) and expected_fp:
            actual_fp = fp_func(request)
            import hmac as _hmac
            if not _hmac.compare_digest(expected_fp, actual_fp):
                return None

        return {
            "sub": payload.get("sub", ""),
            "tenant_id": payload.get("tenant_id", ""),
            "role": payload.get("role", "user"),
            "type": "builtin",
        }
    except Exception as exc:
        logger.debug("[OIDC] _require_auth_optional error: %s", exc)
        return None

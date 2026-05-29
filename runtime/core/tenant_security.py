"""Tenant Isolation Hardening — Enhanced security for multi-tenant deployments

Implements:
  - Tenant ID spoofing prevention
  - Per-tenant rate limiting (100 req/min default)
  - Tenant-scoped audit logging
  - Tenant suspension/blocking
  - Data segregation verification (randomized sampling)
  - Cross-tenant access prevention at all layers
"""

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

try:
    from .tenancy import TenantContext, TenantManager
except ImportError:  # pragma: no cover - compatibility for direct module imports
    from tenancy import TenantContext, TenantManager

logger = logging.getLogger(__name__)

LOG = '[TenantSecurity]'


@dataclass
class TenantSecurityPolicy:
    """Security policy per tenant"""
    max_requests_per_minute: int = 100
    suspended: bool = False
    suspension_reason: Optional[str] = None
    data_verification_enabled: bool = True  # Random sampling verification
    created_at: str = None
    last_verified_at: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class TenantSecurityEnforcer:
    """Enforce tenant isolation and security policies"""

    def __init__(self, tenant_manager: TenantManager, audit_log_fn=None):
        self.tenant_manager = tenant_manager
        self.audit_log = audit_log_fn or (lambda **kwargs: None)
        self.policies: Dict[str, TenantSecurityPolicy] = {}  # tenant_id -> policy
        self.rate_limiters: Dict[str, 'TenantRateLimiter'] = {}
        self.blocked_tenants = set()

    def get_or_create_policy(self, tenant_id: str) -> TenantSecurityPolicy:
        """Get or create default security policy for tenant"""
        if tenant_id not in self.policies:
            self.policies[tenant_id] = TenantSecurityPolicy()
        return self.policies[tenant_id]

    def verify_tenant_access(
        self,
        request_tenant_id: str,
        jwt_tenant_id: str,
        context_tenant_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Verify tenant ID from multiple sources matches (prevent spoofing).

        Args:
            request_tenant_id: Tenant ID from request path/params
            jwt_tenant_id: Tenant ID from JWT claims
            context_tenant_id: Optional context tenant ID

        Returns:
            (allowed: bool, reason: str)
        """
        # All provided tenant IDs must match
        if request_tenant_id != jwt_tenant_id:
            self.audit_log(
                event='tenant_id_mismatch',
                request_tenant_id=request_tenant_id,
                jwt_tenant_id=jwt_tenant_id,
                severity='high',
            )
            return False, 'Tenant ID mismatch between request and JWT'

        if context_tenant_id and context_tenant_id != jwt_tenant_id:
            self.audit_log(
                event='tenant_context_mismatch',
                jwt_tenant_id=jwt_tenant_id,
                context_tenant_id=context_tenant_id,
                severity='high',
            )
            return False, 'Tenant ID mismatch between JWT and context'

        # Check if tenant is suspended
        policy = self.get_or_create_policy(jwt_tenant_id)
        if policy.suspended:
            self.audit_log(
                event='suspended_tenant_access_attempt',
                tenant_id=jwt_tenant_id,
                reason=policy.suspension_reason,
                severity='high',
            )
            return False, f'Tenant suspended: {policy.suspension_reason or "unauthorized"}'

        return True, 'Access verified'

    def check_request_rate_limit(self, tenant_id: str) -> Tuple[bool, Optional[int]]:
        """
        Check if tenant has exceeded rate limit.

        Returns:
            (allowed: bool, seconds_to_retry: Optional[int])
        """
        policy = self.get_or_create_policy(tenant_id)
        if policy.suspended:
            return False, 3600  # Retry in 1 hour for suspended tenant

        if tenant_id not in self.rate_limiters:
            self.rate_limiters[tenant_id] = TenantRateLimiter(
                max_requests_per_minute=policy.max_requests_per_minute
            )

        limiter = self.rate_limiters[tenant_id]
        allowed, retry_after = limiter.try_request()

        if not allowed:
            self.audit_log(
                event='tenant_rate_limit_exceeded',
                tenant_id=tenant_id,
                limit=policy.max_requests_per_minute,
                retry_after_seconds=retry_after,
            )

        return allowed, retry_after

    def suspend_tenant(self, tenant_id: str, reason: str = 'Security policy violation'):
        """Suspend a tenant (blocks all requests)"""
        policy = self.get_or_create_policy(tenant_id)
        policy.suspended = True
        policy.suspension_reason = reason
        self.blocked_tenants.add(tenant_id)

        self.audit_log(
            event='tenant_suspended',
            tenant_id=tenant_id,
            reason=reason,
            severity='critical',
        )

    def unsuspend_tenant(self, tenant_id: str):
        """Unsuspend a tenant"""
        policy = self.get_or_create_policy(tenant_id)
        policy.suspended = False
        policy.suspension_reason = None
        self.blocked_tenants.discard(tenant_id)

        self.audit_log(
            event='tenant_unsuspended',
            tenant_id=tenant_id,
        )

    def verify_data_isolation(
        self,
        tenant_id: str,
        sample_size: int = 10,
    ) -> Dict[str, any]:
        """
        Verify tenant data isolation via randomized sampling.

        Reads random state files and verifies they belong to the tenant.

        Returns:
            {
                'verified': bool,
                'sample_size': int,
                'mismatches': [str],  # Files that failed isolation check
                'timestamp': str,
            }
        """
        policy = self.get_or_create_policy(tenant_id)

        try:
            tenant_state_dir = self.tenant_manager.get_tenant_state_dir(tenant_id)

            # Get list of state files
            state_files = list(tenant_state_dir.glob('*.json'))
            if not state_files:
                return {
                    'verified': True,
                    'sample_size': 0,
                    'mismatches': [],
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'reason': 'No state files to sample',
                }

            # Sample random files
            sample_files = random.sample(
                state_files,
                min(sample_size, len(state_files))
            )

            mismatches = []
            for file_path in sample_files:
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)

                    # Check if data contains tenant_id or is properly scoped
                    if isinstance(data, dict):
                        # If file has _tenant_data, verify our tenant is there
                        if '_tenant_data' in data:
                            if tenant_id not in data['_tenant_data']:
                                mismatches.append(f'{file_path.name}: tenant_id not found in _tenant_data')
                        # Otherwise, assume file is tenant-scoped (in tenant dir)

                except (json.JSONDecodeError, IOError) as e:
                    mismatches.append(f'{file_path.name}: {str(e)}')

            verified = len(mismatches) == 0
            policy.last_verified_at = datetime.now(timezone.utc).isoformat()

            result = {
                'verified': verified,
                'sample_size': len(sample_files),
                'mismatches': mismatches,
                'timestamp': policy.last_verified_at,
            }

            if not verified:
                self.audit_log(
                    event='data_isolation_verification_failed',
                    tenant_id=tenant_id,
                    mismatches=mismatches,
                    severity='critical',
                )

            return result

        except Exception as e:
            self.audit_log(
                event='data_isolation_verification_error',
                tenant_id=tenant_id,
                error=str(e),
                severity='high',
            )
            return {
                'verified': False,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

    def get_tenant_security_status(self, tenant_id: str) -> Dict[str, any]:
        """Get comprehensive security status for tenant"""
        policy = self.get_or_create_policy(tenant_id)
        limiter = self.rate_limiters.get(tenant_id)

        return {
            'tenant_id': tenant_id,
            'suspended': policy.suspended,
            'suspension_reason': policy.suspension_reason,
            'max_requests_per_minute': policy.max_requests_per_minute,
            'rate_limiter_status': limiter.get_status() if limiter else None,
            'created_at': policy.created_at,
            'last_verified_at': policy.last_verified_at,
            'data_verification_enabled': policy.data_verification_enabled,
        }


class TenantRateLimiter:
    """Per-tenant rate limiter (token bucket)"""

    def __init__(self, max_requests_per_minute: int = 100):
        self.max_requests_per_minute = max_requests_per_minute
        self.tokens = float(max_requests_per_minute)
        self.last_refill_time = time.time()
        self.requests_this_minute = 0

    def try_request(self) -> Tuple[bool, Optional[int]]:
        """
        Try to consume a token.

        Returns:
            (allowed: bool, retry_after_seconds: Optional[int])
        """
        now = time.time()
        time_since_refill = now - self.last_refill_time

        # Refill bucket every 60 seconds
        if time_since_refill >= 60:
            self.tokens = float(self.max_requests_per_minute)
            self.last_refill_time = now
            self.requests_this_minute = 0

        if self.tokens >= 1:
            self.tokens -= 1
            self.requests_this_minute += 1
            return True, None
        else:
            # Calculate when next token will be available
            seconds_to_refill = 60 - time_since_refill
            return False, int(seconds_to_refill)

    def get_status(self) -> Dict[str, any]:
        """Get rate limiter status"""
        return {
            'tokens_available': int(self.tokens),
            'max_tokens': self.max_requests_per_minute,
            'requests_this_minute': self.requests_this_minute,
            'fill_percentage': (self.tokens / self.max_requests_per_minute) * 100,
        }


# Global tenant security enforcer
_tenant_security_enforcer: Optional[TenantSecurityEnforcer] = None


def init_tenant_security(
    tenant_manager: TenantManager,
    audit_log_fn=None,
) -> TenantSecurityEnforcer:
    """Initialize global tenant security enforcer"""
    global _tenant_security_enforcer
    _tenant_security_enforcer = TenantSecurityEnforcer(tenant_manager, audit_log_fn)
    return _tenant_security_enforcer


def get_tenant_security_enforcer() -> TenantSecurityEnforcer:
    """Get global tenant security enforcer"""
    if _tenant_security_enforcer is None:
        raise RuntimeError(
            'Tenant security enforcer not initialized. Call init_tenant_security() first.'
        )
    return _tenant_security_enforcer

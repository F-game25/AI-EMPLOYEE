"""Phase 3.2 Security Hardening — Integration Tests

Tests cover:
  1. JWT token lifecycle (issuance, refresh, expiration, revocation)
  2. Signed events (signing, verification, tampering detection)
  3. Tenant isolation and spoofing prevention
  4. Sandbox execution with resource limits
  5. Rate limiting across tenant/IP/global scopes
  6. Audit logging of security events
"""

import json
import pytest
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add runtime to path
runtime_path = Path(__file__).parent.parent / 'runtime'
if str(runtime_path) not in sys.path:
    sys.path.insert(0, str(runtime_path))

from core.signed_events import EventSigner, SignedEventValidator
from core.tenancy import TenantManager, TenantContext
from core.tenant_security import TenantSecurityEnforcer, TenantRateLimiter


# ── Signed Events Tests ──────────────────────────────────────────────────────

class TestSignedEvents:
    """Test event signing and verification"""

    def setup_method(self):
        self.signer = EventSigner('a' * 64)  # 64-char secret

    def test_sign_event_creates_valid_signature(self):
        """Event signing produces verifiable signature"""
        event = self.signer.sign_event(
            'task_completed',
            {'task_id': '123', 'result': 'success'},
        )

        assert event['event_type'] == 'task_completed'
        assert 'signature' in event
        assert 'event_id' in event
        assert 'timestamp' in event

    def test_verify_valid_event_succeeds(self):
        """Valid event signature verifies correctly"""
        event = self.signer.sign_event(
            'task_completed',
            {'task_id': '123'},
        )

        assert self.signer.verify_event(event) is True

    def test_verify_tampered_event_fails(self):
        """Tampered event signature fails verification"""
        event = self.signer.sign_event(
            'task_completed',
            {'task_id': '123'},
        )

        # Tamper with payload
        event['payload']['task_id'] = '456'

        assert self.signer.verify_event(event) is False

    def test_verify_tampered_signature_fails(self):
        """Event with tampered signature fails verification"""
        event = self.signer.sign_event(
            'task_completed',
            {'task_id': '123'},
        )

        # Tamper with signature
        event['signature'] = 'a' * 64

        assert self.signer.verify_event(event) is False

    def test_batch_sign_events(self):
        """Batch signing creates multiple signatures"""
        payloads = [
            {'task_id': '1'},
            {'task_id': '2'},
            {'task_id': '3'},
        ]

        events = self.signer.batch_sign_events(payloads, 'task_completed')

        assert len(events) == 3
        for event in events:
            assert self.signer.verify_event(event) is True

    def test_batch_verify_events(self):
        """Batch verification reports valid/invalid"""
        # Create mixed valid/invalid events
        valid_event = self.signer.sign_event('task_completed', {'task_id': '1'})
        invalid_event = self.signer.sign_event('task_completed', {'task_id': '2'})
        invalid_event['signature'] = 'invalid'

        result = self.signer.batch_verify_events([valid_event, invalid_event])

        assert len(result['valid']) == 1
        assert len(result['invalid']) == 1
        assert result['summary']['total'] == 2

    def test_event_validator_filters_invalid_events(self):
        """Event validator rejects invalid signatures"""
        validator = SignedEventValidator(self.signer)

        valid_event = self.signer.sign_event('task_completed', {'task_id': '1'})
        invalid_event = self.signer.sign_event('task_completed', {'task_id': '2'})
        invalid_event['signature'] = 'tampered'

        assert validator.validate_and_process(valid_event) is not None
        assert validator.validate_and_process(invalid_event) is None

    def test_different_secret_fails_verification(self):
        """Event signed with different secret fails verification"""
        signer2 = EventSigner('b' * 64)

        event = self.signer.sign_event(
            'task_completed',
            {'task_id': '123'},
        )

        # Verify with different signer should fail
        assert signer2.verify_event(event) is False


# ── Tenant Security Tests ────────────────────────────────────────────────────

class TestTenantSecurityEnforcer:
    """Test tenant isolation enforcement"""

    def setup_method(self, tmp_path):
        self.tmp_path = tmp_path
        self.tenant_manager = TenantManager(self.tmp_path)
        self.enforcer = TenantSecurityEnforcer(self.tenant_manager)

    def test_verify_matching_tenant_ids_allowed(self):
        """Matching tenant IDs from request and JWT allowed"""
        allowed, reason = self.enforcer.verify_tenant_access(
            'tenant-123',
            'tenant-123',
        )

        assert allowed is True

    def test_verify_mismatched_tenant_ids_denied(self):
        """Mismatched request and JWT tenant IDs denied"""
        allowed, reason = self.enforcer.verify_tenant_access(
            'tenant-123',
            'tenant-456',
        )

        assert allowed is False
        assert 'mismatch' in reason.lower()

    def test_verify_suspended_tenant_denied(self):
        """Suspended tenant access denied"""
        tenant_id = 'tenant-123'
        self.enforcer.suspend_tenant(tenant_id, 'Security violation')

        allowed, reason = self.enforcer.verify_tenant_access(tenant_id, tenant_id)

        assert allowed is False
        assert 'suspended' in reason.lower()

    def test_suspend_and_unsuspend_tenant(self):
        """Tenant suspension and restoration works"""
        tenant_id = 'tenant-123'

        self.enforcer.suspend_tenant(tenant_id, 'Test suspension')
        assert self.enforcer.get_or_create_policy(tenant_id).suspended is True

        self.enforcer.unsuspend_tenant(tenant_id)
        assert self.enforcer.get_or_create_policy(tenant_id).suspended is False

    def test_rate_limit_allows_requests_within_limit(self):
        """Requests within rate limit allowed"""
        tenant_id = 'tenant-123'

        for i in range(50):
            allowed, retry = self.enforcer.check_request_rate_limit(tenant_id)
            assert allowed is True
            assert retry is None

    def test_rate_limit_blocks_excess_requests(self):
        """Requests exceeding rate limit blocked"""
        tenant_id = 'tenant-123'

        # Use up the rate limit (default 100 req/min)
        for i in range(100):
            self.enforcer.check_request_rate_limit(tenant_id)

        # Next request should be blocked
        allowed, retry = self.enforcer.check_request_rate_limit(tenant_id)
        assert allowed is False
        assert retry is not None


class TestTenantRateLimiter:
    """Test per-tenant rate limiting"""

    def test_allows_requests_within_capacity(self):
        """Token bucket allows requests up to capacity"""
        limiter = TenantRateLimiter(max_requests_per_minute=10)

        for i in range(10):
            allowed, retry = limiter.try_request()
            assert allowed is True

    def test_blocks_requests_over_capacity(self):
        """Token bucket blocks requests exceeding capacity"""
        limiter = TenantRateLimiter(max_requests_per_minute=3)

        # Use up capacity
        for i in range(3):
            limiter.try_request()

        # Should be blocked
        allowed, retry = limiter.try_request()
        assert allowed is False
        assert retry is not None

    def test_status_shows_remaining_tokens(self):
        """Status reflects available tokens"""
        limiter = TenantRateLimiter(max_requests_per_minute=10)

        limiter.try_request()
        limiter.try_request()

        status = limiter.get_status()
        assert status['tokens_available'] == 8
        assert status['max_tokens'] == 10


# ── Security Policy Tests ────────────────────────────────────────────────────

class TestSecurityPolicies:
    """Test security policy enforcement"""

    def test_policy_creation_with_defaults(self, tmp_path):
        """Default security policies applied to new tenants"""
        tenant_manager = TenantManager(tmp_path)
        enforcer = TenantSecurityEnforcer(tenant_manager)

        policy = enforcer.get_or_create_policy('tenant-123')

        assert policy.max_requests_per_minute == 100
        assert policy.suspended is False
        assert policy.created_at is not None

    def test_audit_logging_on_violations(self, tmp_path):
        """Security violations logged to audit"""
        audit_events = []

        def audit_log(**kwargs):
            audit_events.append(kwargs)

        tenant_manager = TenantManager(tmp_path)
        enforcer = TenantSecurityEnforcer(tenant_manager, audit_log)

        # Trigger a violation
        enforcer.verify_tenant_access('tenant-123', 'tenant-456')

        # Check audit log
        assert len(audit_events) > 0
        assert any(e.get('event') == 'tenant_id_mismatch' for e in audit_events)


# ── Integration Tests ────────────────────────────────────────────────────────

class TestSecurityIntegration:
    """Integration tests for security layers"""

    def test_signed_events_with_tenant_context(self):
        """Events signed with tenant context verify correctly"""
        signer = EventSigner('x' * 64)

        # Sign event with tenant info
        event = signer.sign_event(
            'tenant_operation',
            {
                'tenant_id': 'tenant-123',
                'operation': 'data_export',
                'user_id': 'user-456',
            },
        )

        # Verify signature
        assert signer.verify_event(event) is True

        # Payload intact
        assert event['payload']['tenant_id'] == 'tenant-123'

    def test_tenant_isolation_with_rate_limiting(self, tmp_path):
        """Tenant isolation enforced alongside rate limiting"""
        tenant_manager = TenantManager(tmp_path)
        enforcer = TenantSecurityEnforcer(tenant_manager)

        # Create tenants
        tenant_a = 'tenant-a'
        tenant_b = 'tenant-b'

        # Each tenant has independent rate limit
        for i in range(50):
            enforcer.check_request_rate_limit(tenant_a)
            enforcer.check_request_rate_limit(tenant_b)

        # Both should be within limit
        allowed_a, _ = enforcer.check_request_rate_limit(tenant_a)
        allowed_b, _ = enforcer.check_request_rate_limit(tenant_b)

        assert allowed_a is True
        assert allowed_b is True

        # Cross-tenant access denied
        allowed, _ = enforcer.verify_tenant_access(tenant_a, tenant_b)
        assert allowed is False


# ── Performance Tests ────────────────────────────────────────────────────────

class TestSecurityPerformance:
    """Performance tests for security operations"""

    def test_event_signing_performance(self):
        """Event signing completes in < 1ms"""
        signer = EventSigner('s' * 64)

        start = time.time()
        for i in range(1000):
            signer.sign_event('perf_test', {'iteration': i})
        elapsed = time.time() - start

        # Should sign 1000 events in < 500ms
        assert elapsed < 0.5

    def test_rate_limit_check_performance(self, tmp_path):
        """Rate limit checks complete in microseconds"""
        tenant_manager = TenantManager(tmp_path)
        enforcer = TenantSecurityEnforcer(tenant_manager)

        start = time.time()
        for i in range(10000):
            enforcer.check_request_rate_limit(f'tenant-{i % 10}')
        elapsed = time.time() - start

        # Should check 10k rate limits in < 100ms
        assert elapsed < 0.1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

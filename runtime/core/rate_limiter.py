"""Per-tenant rate limiting and quota enforcement."""
import os
import logging
import time
from typing import Optional, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class TenantQuota:
    """Per-tenant rate limit and quota settings."""
    def __init__(
        self,
        requests_per_minute: int = 60,
        agents_per_hour: int = 100,
        api_calls_per_day: int = 10000,
        storage_gb: float = 10.0,
    ):
        self.requests_per_minute = requests_per_minute
        self.agents_per_hour = agents_per_hour
        self.api_calls_per_day = api_calls_per_day
        self.storage_gb = storage_gb


class RateLimiter:
    """Enforce rate limits and quotas per tenant."""

    def __init__(self):
        self.db = None
        self.local_counters = defaultdict(lambda: {
            "requests": defaultdict(list),  # tenant_id -> [timestamps]
            "agents": defaultdict(list),
            "api_calls": defaultdict(int),
        })
        self.quota_tiers = {
            "starter": TenantQuota(requests_per_minute=60, agents_per_hour=50, api_calls_per_day=5000, storage_gb=5.0),
            "business": TenantQuota(requests_per_minute=300, agents_per_hour=500, api_calls_per_day=50000, storage_gb=50.0),
            "enterprise": TenantQuota(requests_per_minute=1000, agents_per_hour=2000, api_calls_per_day=500000, storage_gb=500.0),
        }

    def set_database(self, db):
        """Set database connection."""
        self.db = db

    def get_tenant_quota(self, tenant_id: str) -> TenantQuota:
        """Get quota for a tenant based on subscription tier."""
        try:
            if not self.db:
                return self.quota_tiers["starter"]

            result = self.db.execute(
                "SELECT subscription_tier FROM tenants WHERE tenant_id = %s",
                (tenant_id,),
                tenant_id=tenant_id,
            )

            if result:
                tier = result[0].get("subscription_tier", "starter")
                return self.quota_tiers.get(tier, self.quota_tiers["starter"])
            return self.quota_tiers["starter"]
        except Exception as e:
            logger.error(f"Failed to get tenant quota: {e}")
            return self.quota_tiers["starter"]

    def check_request_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within request rate limit (per minute)."""
        quota = self.get_tenant_quota(tenant_id)
        now = time.time()
        one_minute_ago = now - 60

        # Clean old timestamps
        self.local_counters[tenant_id]["requests"][tenant_id] = [
            ts for ts in self.local_counters[tenant_id]["requests"][tenant_id]
            if ts > one_minute_ago
        ]

        # Check limit
        if len(self.local_counters[tenant_id]["requests"][tenant_id]) >= quota.requests_per_minute:
            logger.warning(f"Tenant {tenant_id} exceeded request rate limit")
            return False

        # Record request
        self.local_counters[tenant_id]["requests"][tenant_id].append(now)
        return True

    def check_agent_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within agent execution limit (per hour)."""
        quota = self.get_tenant_quota(tenant_id)
        now = time.time()
        one_hour_ago = now - 3600

        # Clean old timestamps
        self.local_counters[tenant_id]["agents"][tenant_id] = [
            ts for ts in self.local_counters[tenant_id]["agents"][tenant_id]
            if ts > one_hour_ago
        ]

        # Check limit
        if len(self.local_counters[tenant_id]["agents"][tenant_id]) >= quota.agents_per_hour:
            logger.warning(f"Tenant {tenant_id} exceeded agent execution limit")
            return False

        # Record execution
        self.local_counters[tenant_id]["agents"][tenant_id].append(now)
        return True

    def check_api_call_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within API call limit (per day)."""
        quota = self.get_tenant_quota(tenant_id)
        count = self.local_counters[tenant_id]["api_calls"].get(tenant_id, 0)

        if count >= quota.api_calls_per_day:
            logger.warning(f"Tenant {tenant_id} exceeded API call limit")
            return False

        # Increment counter
        self.local_counters[tenant_id]["api_calls"][tenant_id] = count + 1
        return True

    def get_tenant_usage(self, tenant_id: str) -> Dict[str, int]:
        """Get current usage for a tenant."""
        return {
            "requests_this_minute": len(self.local_counters[tenant_id]["requests"].get(tenant_id, [])),
            "agents_this_hour": len(self.local_counters[tenant_id]["agents"].get(tenant_id, [])),
            "api_calls_today": self.local_counters[tenant_id]["api_calls"].get(tenant_id, 0),
        }

    def reset_daily_counters(self):
        """Reset daily counters (call this once per day)."""
        for tenant_id in self.local_counters:
            self.local_counters[tenant_id]["api_calls"][tenant_id] = 0


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    return RateLimiter()

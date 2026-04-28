"""Per-tenant cost attribution and billing metrics."""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class BillingMetrics:
    """Per-tenant billing snapshot."""
    tenant_id: str
    period_start: str
    period_end: str
    api_calls: int
    agent_executions: int
    database_queries: int
    storage_mb: float
    trace_spans: int
    error_count: int
    estimated_cost_usd: float


class BillingMetricsCollector:
    """Collect and track per-tenant billing metrics."""

    def __init__(self):
        self.db = None
        self.metrics_cache = {}

    def set_database(self, db):
        """Set database connection."""
        self.db = db

    def record_api_call(self, tenant_id: str, endpoint: str, method: str, status_code: int):
        """Record API call for billing."""
        try:
            if not self.db:
                return

            self.db.execute(
                """
                INSERT INTO billing_events (tenant_id, event_type, event_data, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    "api_call",
                    {"endpoint": endpoint, "method": method, "status": status_code},
                    datetime.utcnow(),
                ),
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.error(f"Failed to record API call for billing: {e}")

    def record_agent_execution(self, tenant_id: str, agent_id: str, duration_ms: float, tokens_used: int):
        """Record agent execution for billing."""
        try:
            if not self.db:
                return

            self.db.execute(
                """
                INSERT INTO billing_events (tenant_id, event_type, event_data, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    "agent_execution",
                    {"agent_id": agent_id, "duration_ms": duration_ms, "tokens": tokens_used},
                    datetime.utcnow(),
                ),
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.error(f"Failed to record agent execution for billing: {e}")

    def record_database_query(self, tenant_id: str, table: str, operation: str, duration_ms: float):
        """Record database query for billing."""
        try:
            if not self.db:
                return

            self.db.execute(
                """
                INSERT INTO billing_events (tenant_id, event_type, event_data, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    "database_query",
                    {"table": table, "operation": operation, "duration_ms": duration_ms},
                    datetime.utcnow(),
                ),
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.error(f"Failed to record database query for billing: {e}")

    def get_tenant_metrics(self, tenant_id: str, period_days: int = 30) -> Optional[BillingMetrics]:
        """Get billing metrics for a tenant over a period."""
        try:
            if not self.db:
                return None

            period_start = datetime.utcnow() - timedelta(days=period_days)
            period_end = datetime.utcnow()

            # Count events by type
            api_calls = self._count_events(tenant_id, "api_call", period_start, period_end)
            agent_executions = self._count_events(tenant_id, "agent_execution", period_start, period_end)
            database_queries = self._count_events(tenant_id, "database_query", period_start, period_end)
            error_count = self._count_events(tenant_id, "error", period_start, period_end)

            # Calculate estimated cost
            estimated_cost = self._calculate_cost(api_calls, agent_executions, database_queries)

            return BillingMetrics(
                tenant_id=tenant_id,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
                api_calls=api_calls,
                agent_executions=agent_executions,
                database_queries=database_queries,
                storage_mb=0.0,  # TODO: calculate from database
                trace_spans=0,  # TODO: count from Jaeger
                error_count=error_count,
                estimated_cost_usd=estimated_cost,
            )
        except Exception as e:
            logger.error(f"Failed to get tenant metrics: {e}")
            return None

    def _count_events(self, tenant_id: str, event_type: str, start: datetime, end: datetime) -> int:
        """Count events of a type in a period."""
        try:
            result = self.db.execute(
                """
                SELECT COUNT(*) as count FROM billing_events
                WHERE tenant_id = %s AND event_type = %s AND created_at BETWEEN %s AND %s
                """,
                (tenant_id, event_type, start, end),
                tenant_id=tenant_id,
            )
            return result[0].get("count", 0) if result else 0
        except Exception as e:
            logger.error(f"Failed to count events: {e}")
            return 0

    def _calculate_cost(self, api_calls: int, agent_executions: int, database_queries: int) -> float:
        """Calculate estimated cost based on usage."""
        # Pricing model (in USD)
        api_call_cost = 0.0001  # $0.0001 per API call
        agent_execution_cost = 0.01  # $0.01 per agent execution
        database_query_cost = 0.00001  # $0.00001 per database query

        return (
            api_calls * api_call_cost +
            agent_executions * agent_execution_cost +
            database_queries * database_query_cost
        )

    def get_all_tenant_metrics(self, period_days: int = 30) -> list[BillingMetrics]:
        """Get billing metrics for all tenants."""
        try:
            if not self.db:
                return []

            # Get all tenant IDs
            tenants = self.db.execute(
                "SELECT tenant_id FROM tenants WHERE status = 'active'"
            )

            metrics_list = []
            for tenant in tenants:
                metrics = self.get_tenant_metrics(tenant.get("tenant_id"), period_days)
                if metrics:
                    metrics_list.append(metrics)

            return metrics_list
        except Exception as e:
            logger.error(f"Failed to get all tenant metrics: {e}")
            return []


def get_billing_collector() -> BillingMetricsCollector:
    """Get global billing metrics collector."""
    return BillingMetricsCollector()

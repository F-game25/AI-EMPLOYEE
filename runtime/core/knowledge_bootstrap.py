"""Bootstrap knowledge store with seed data on first deployment."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


SEED_KNOWLEDGE = [
    {
        "id": "kb_system_architecture",
        "title": "System Architecture Overview",
        "content": "AI Employee is a multi-tenant, PostgreSQL-backed system with RBAC (admin/member/viewer), Stripe payment processing, and Jaeger distributed tracing. Frontend: React + Vite. Backend: Node.js Express + FastAPI. All agents are directory-based with BaseAgent pattern. Database is auto-migrated via Alembic.",
        "category": "system",
        "tags": ["architecture", "overview", "system"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_agent_pattern",
        "title": "Building an Agent",
        "content": "All agents follow BaseAgent pattern: subclass BaseAgent, set agent_id and required_fields, implement execute(). Use self._ask_json() for LLM calls. Use self._save_to_db(), self._query_db(), self._update_db() for database access (auto-tenant-isolated). Agents are discovered from runtime/agents/<name>/<name>.py and registered in agent_capabilities.json.",
        "category": "development",
        "tags": ["agents", "development", "baseagent"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_rbac_roles",
        "title": "RBAC Roles and Permissions",
        "content": "Three roles: admin (full access, manage users/billing), member (execute agents, read data), viewer (read-only). Roles are per-tenant. Assign via POST /api/rbac/assign-role. Check permissions with RBACManager.has_permission(). All routes enforce role checks via FastAPI Depends().",
        "category": "security",
        "tags": ["rbac", "roles", "security", "admin"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_stripe_integration",
        "title": "Stripe Payment Processing",
        "content": "Stripe integration is sandbox-first. Create customers via POST /api/billing/customer/create. Create payment intents for one-time charges. Create subscriptions for recurring billing. All methods gracefully degrade if STRIPE_API_KEY missing. Stripe test keys start with pk_test_ and sk_test_. Production keys deferred to Phase 4+.",
        "category": "billing",
        "tags": ["stripe", "payments", "billing", "sandbox"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_jaeger_tracing",
        "title": "Distributed Tracing with Jaeger",
        "content": "Jaeger is deployed in docker-compose (all-in-one). Traces are sent via UDP thrift to localhost:6831. Dashboard available at http://localhost:16686. FastAPI routes and PostgreSQL queries are auto-instrumented. Spans include request/response data, query text, latency. Sample rate 10% default (configurable via JAEGER_SAMPLE_RATE).",
        "category": "observability",
        "tags": ["jaeger", "tracing", "observability", "monitoring"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_multi_tenancy",
        "title": "Multi-Tenant Architecture",
        "content": "System is fully multi-tenant: each tenant has isolated data, RBAC roles, billing metrics. Tenant ID is extracted from JWT token claim and passed through all layers. All queries are automatically filtered by tenant_id via database middleware. Tenant context is request-scoped using contextvars. Each tenant lives in ~/.ai-employee/tenants/{tenant_id}/ on disk.",
        "category": "architecture",
        "tags": ["multi-tenancy", "isolation", "architecture"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_database_queries",
        "title": "Database Access Patterns",
        "content": "Use BaseAgent._save_to_db(table, data), ._query_db(table, where, params), ._update_db(table, data, where, params). All queries auto-inject tenant_id. Use parameterized queries (%s placeholders) to prevent SQL injection. Database is PostgreSQL with psycopg3 connection pooling (10-15 connections). Backups are automatic (daily retention: 30 days).",
        "category": "development",
        "tags": ["database", "queries", "sql", "security"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_authentication",
        "title": "Authentication and Tokens",
        "content": "JWT tokens are issued by POST /api/auth/token (requires JWT_SECRET_KEY). Tokens expire in 24 hours by default. All protected routes require valid JWT in Authorization: Bearer header. Tokens include claims: role, iss, tenant_id, iat, exp. Token refresh endpoint available at POST /api/auth/refresh. Weak secrets are detected and generate warnings.",
        "category": "security",
        "tags": ["authentication", "jwt", "security", "tokens"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_rate_limiting",
        "title": "Rate Limiting and Quotas",
        "content": "Per-tenant quotas enforced: Starter (60 req/min, 50 agents/hr, 5000 calls/day, 5 GB storage), Business (300/500/50000/50), Enterprise (1000/2000/500000/500). Check limits via RateLimiter.check_request_limit(), check_agent_limit(), check_api_call_limit(). Rate limits are per-tenant and subscription-based. Exceeding limits returns 429 Too Many Requests.",
        "category": "billing",
        "tags": ["rate-limiting", "quotas", "billing"],
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "kb_error_tracking",
        "title": "Error Tracking with Sentry",
        "content": "Sentry is configured for production error tracking (optional, requires SENTRY_DSN env var). All unhandled exceptions are captured with stack traces. User context (ID, email) and tenant context are attached to errors. Integration with FastAPI logging. Sentry dashboard shows error trends, affected users, release tracking.",
        "category": "observability",
        "tags": ["sentry", "errors", "observability", "monitoring"],
        "created_at": datetime.utcnow().isoformat(),
    },
]


class KnowledgeBootstrapper:
    """Bootstrap knowledge store with seed data."""

    def __init__(self, state_dir: str = None):
        self.state_dir = Path(state_dir or "state")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_file = self.state_dir / "knowledge_store.json"

    def bootstrap(self) -> int:
        """Initialize knowledge store with seed data."""
        try:
            # Load existing knowledge store if it exists
            existing = self._load_knowledge_store()

            # Add seed entries that don't already exist
            added_count = 0
            for entry in SEED_KNOWLEDGE:
                if not any(k["id"] == entry["id"] for k in existing):
                    existing.append(entry)
                    added_count += 1

            # Save back to file
            self._save_knowledge_store(existing)
            logger.info(f"Bootstrapped knowledge store: {added_count} entries added, {len(existing)} total")
            return added_count

        except Exception as e:
            logger.error(f"Failed to bootstrap knowledge store: {e}")
            return 0

    def _load_knowledge_store(self) -> List[Dict[str, Any]]:
        """Load existing knowledge store from disk."""
        if self.knowledge_file.exists():
            try:
                with open(self.knowledge_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load knowledge store: {e}")
                return []
        return []

    def _save_knowledge_store(self, entries: List[Dict[str, Any]]) -> bool:
        """Save knowledge store to disk."""
        try:
            with open(self.knowledge_file, "w") as f:
                json.dump(entries, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save knowledge store: {e}")
            return False

    def get_seed_data(self) -> List[Dict[str, Any]]:
        """Get seed knowledge entries."""
        return SEED_KNOWLEDGE


def bootstrap_knowledge(state_dir: str = None) -> int:
    """Bootstrap knowledge store on startup."""
    bootstrapper = KnowledgeBootstrapper(state_dir)
    return bootstrapper.bootstrap()

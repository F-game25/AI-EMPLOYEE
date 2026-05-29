"""
Capability manifest system — declarative feature specs with graceful fallback.
Each capability can be: available (installed), enabled, disabled, or broken.
Provides lazy-load + graceful_fallback pattern instead of crash-on-import.
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any


CAPABILITIES_MANIFEST = {
    "embeddings": {
        "status": "available",
        "description": "Vector embeddings & similarity search",
        "required_packages": ["numpy>=1.24.0", "sentence-transformers>=2.7.0"],
        "env_vars": [],
        "init": "core.embeddings:get_embeddings_manager",
        "graceful_fallback": "hash-based 32-dim embeddings",
        "size_mb": 420,
        "external": None
    },
    "tracing": {
        "status": "available",
        "description": "Distributed tracing via Jaeger",
        "required_packages": ["opentelemetry-exporter-jaeger>=1.25.0", "opentelemetry-sdk>=1.25.0"],
        "env_vars": ["JAEGER_AGENT_HOST", "JAEGER_AGENT_PORT"],
        "init": "core.observability.tracing:init_jaeger",
        "graceful_fallback": "no-op tracer",
        "size_mb": 50,
        "external": None
    },
    "billing": {
        "status": "available",
        "description": "Billing & revenue tracking",
        "required_packages": ["stripe>=7.0.0"],
        "env_vars": ["STRIPE_SECRET_KEY"],
        "init": "core.billing:init_stripe",
        "graceful_fallback": "mock billing (no charges)",
        "size_mb": 10,
        "external": None
    },
    "mailchimp": {
        "status": "available",
        "description": "Newsletter integration",
        "required_packages": ["mailchimp-marketing>=3.0.80"],
        "env_vars": ["MAILCHIMP_API_KEY", "MAILCHIMP_LIST_ID"],
        "init": "agents.newsletter_bot.newsletter_bot:init_mailchimp",
        "graceful_fallback": "newsletter disabled (not_configured)",
        "size_mb": 5,
        "external": None
    },
    "postgres": {
        "status": "available",
        "description": "PostgreSQL database backend",
        "required_packages": ["psycopg[binary]>=3.1.0", "sqlalchemy>=2.0.0"],
        "env_vars": ["DATABASE_URL"],
        "init": "core.db:init_postgres",
        "graceful_fallback": "SQLite (local only)",
        "size_mb": 20,
        "external": "postgres"
    },
    "sentry": {
        "status": "available",
        "description": "Error tracking & monitoring",
        "required_packages": ["sentry-sdk>=1.40.0"],
        "env_vars": ["SENTRY_DSN"],
        "init": "core.observability.sentry:init_sentry",
        "graceful_fallback": "no-op error tracking",
        "size_mb": 8,
        "external": None
    },
    "local_llm": {
        "status": "available",
        "description": "Local LLM via Ollama",
        "required_packages": [],
        "env_vars": ["OLLAMA_HOST"],
        "init": "core.llm.ollama:init_ollama",
        "graceful_fallback": "Anthropic API required",
        "size_mb": 7000,
        "external": "ollama"
    }
}


class CapabilityManager:
    """Manage capability status and lazy-loading."""

    def __init__(self, manifest_file: Optional[Path] = None):
        self.manifest_file = manifest_file or (Path.home() / ".ai-employee" / "capabilities.json")
        self._cache = {}
        self._cache_age = 0
        self._cache_ttl_seconds = 60
        self._load_manifest()

    def _load_manifest(self):
        """Load manifest from file, or use defaults."""
        if self.manifest_file.exists():
            with open(self.manifest_file) as f:
                self._manifest = json.load(f)
        else:
            self._manifest = CAPABILITIES_MANIFEST.copy()

    def check_all(self) -> Dict[str, Dict[str, Any]]:
        """Check live status of all capabilities (packages installed? env vars set?)."""
        result = {}
        for cap_name, cap_spec in self._manifest.items():
            result[cap_name] = self._check_capability(cap_name, cap_spec)
        return result

    def _check_capability(self, name: str, spec: Dict) -> Dict[str, Any]:
        """Check if a single capability is available."""
        status = {
            "name": name,
            "status": "broken",
            "description": spec.get("description", ""),
            "installed_packages": [],
            "missing_packages": [],
            "missing_env_vars": [],
            "graceful_fallback": spec.get("graceful_fallback", "unknown")
        }

        # Check packages
        missing = []
        for pkg_spec in spec.get("required_packages", []):
            pkg_name = pkg_spec.split(">=")[0].split("==")[0]
            if not self._is_package_installed(pkg_name):
                missing.append(pkg_spec)
            else:
                status["installed_packages"].append(pkg_name)
        status["missing_packages"] = missing

        # Check env vars
        import os
        missing_env = []
        for var in spec.get("env_vars", []):
            if not os.getenv(var):
                missing_env.append(var)
        status["missing_env_vars"] = missing_env

        # Determine status
        if missing or missing_env:
            status["status"] = "disabled"
        else:
            status["status"] = "enabled"

        return status

    @staticmethod
    def _is_package_installed(package_name: str) -> bool:
        """Check if a Python package is installed."""
        try:
            __import__(package_name.replace("-", "_"))
            return True
        except ImportError:
            return False

    def require(self, capability: str) -> Optional[Any]:
        """
        Require a capability. Returns the initialized module or graceful_fallback value.
        If the capability is not available, returns the fallback and logs an audit entry.
        """
        spec = self._manifest.get(capability)
        if not spec:
            return None

        status = self._check_capability(capability, spec)

        # If available, try to import and initialize
        if status["status"] == "enabled":
            try:
                module_path = spec.get("init", "")
                if ":" in module_path:
                    mod_name, func_name = module_path.rsplit(":", 1)
                    mod = __import__(mod_name, fromlist=[func_name])
                    init_func = getattr(mod, func_name)
                    return init_func()
            except Exception as e:
                # Fallthrough to fallback
                self._log_capability_failure(capability, str(e))

        # Return graceful fallback
        fallback = spec.get("graceful_fallback")
        self._log_capability_disabled(capability, status)
        return fallback

    def enable_capability(self, capability: str) -> bool:
        """Install missing packages for a capability (async, for UI)."""
        spec = self._manifest.get(capability)
        if not spec:
            return False

        packages = spec.get("required_packages", [])
        if not packages:
            return True

        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + packages,
                check=True,
                capture_output=True,
                timeout=300
            )
            return True
        except Exception as e:
            print(f"Failed to install {capability}: {e}")
            return False

    def save_manifest(self):
        """Persist manifest to file."""
        self.manifest_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_file, 'w') as f:
            json.dump(self._manifest, f, indent=2)

    @staticmethod
    def _log_capability_failure(cap: str, error: str):
        """Log capability initialization failure (would write to audit.db)."""
        # TODO: wire into audit.db
        print(f"[AUDIT] Capability '{cap}' initialization failed: {error}")

    @staticmethod
    def _log_capability_disabled(cap: str, status: Dict):
        """Log capability being unavailable and using fallback (would write to audit.db)."""
        # TODO: wire into audit.db
        print(f"[AUDIT] Capability '{cap}' unavailable, using fallback: {status['graceful_fallback']}")


# Global instance (lazy-initialized)
_manager: Optional[CapabilityManager] = None


def get_capability_manager() -> CapabilityManager:
    """Get or create global capability manager."""
    global _manager
    if _manager is None:
        _manager = CapabilityManager()
    return _manager


def require(capability: str) -> Optional[Any]:
    """Convenience function: require a capability."""
    return get_capability_manager().require(capability)


def check_all() -> Dict[str, Dict[str, Any]]:
    """Convenience function: check all capabilities."""
    return get_capability_manager().check_all()


if __name__ == "__main__":
    # Quick test
    mgr = CapabilityManager()
    status = mgr.check_all()
    for cap, info in status.items():
        print(f"{cap:15} {info['status']:10} {info.get('missing_packages', [])}")

"""
AI Employee — Configuration Management (from openclaw-2)
Handles secure loading and Pydantic-based validation of configuration.
"""
import os
import yaml
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecurityConfig(BaseModel):
    """Security configuration."""
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    max_login_attempts: int = 5
    progressive_lockout_seconds: list[int] = [60, 300, 900, 1800]
    min_password_length: int = 12
    require_special_chars: bool = True
    require_numbers: bool = True
    require_uppercase: bool = True
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    cors_origins: list[str] = ["http://localhost:8787", "http://127.0.0.1:8787"]
    max_sessions_per_user: int = 3
    session_timeout_minutes: int = 60


class PrivacyConfig(BaseModel):
    """Privacy configuration."""
    data_dir: str = "./data"
    logs_dir: str = "./logs"
    telemetry_enabled: bool = False
    analytics_enabled: bool = False
    external_api_calls_disabled: bool = False
    log_retention_days: int = 30
    session_data_retention_days: int = 7
    encrypt_data_at_rest: bool = True
    encryption_algorithm: str = "AES-256-GCM"


class AIConfig(BaseModel):
    """AI model configuration."""
    use_local_model: bool = True
    model_path: str = "./models"
    max_tokens: int = 2048
    temperature: float = 0.7
    openai_api_key_env: str = "OPENAI_API_KEY"
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"
    file_enabled: bool = True
    console_enabled: bool = True
    audit_enabled: bool = True
    audit_failed_auth: bool = True
    audit_file_access: bool = True
    audit_api_calls: bool = True


class LimitsConfig(BaseModel):
    """Resource limits configuration."""
    max_file_upload_size_mb: int = 10
    max_concurrent_requests: int = 10
    max_memory_usage_mb: int = 1024
    request_timeout_seconds: int = 30


class Config(BaseSettings):
    """Main application configuration."""
    app_name: str = "AI Employee - Private & Secure"
    app_version: str = "2.0.0"
    environment: str = "production"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8787

    security: SecurityConfig
    privacy: PrivacyConfig
    ai: AIConfig
    logging: LoggingConfig
    limits: LimitsConfig

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from a YAML file with secure defaults.

    Priority:
      1. *config_path* if explicitly given.
      2. ``security.local.yml`` in the current directory (gitignored overrides).
      3. ``security.yml`` shipped in the same directory as this file.

    The ``JWT_SECRET_KEY`` environment variable always overrides the YAML value.

    Raises:
        ValueError: if the JWT secret is still the placeholder default.
    """
    if config_path is None:
        # Look for security.local.yml next to THIS file first, then CWD
        local_beside = Path(__file__).resolve().parent / "security.local.yml"
        local_cwd = Path("security.local.yml")
        bundled = Path(__file__).resolve().parents[2] / "config" / "security.yml"
        if local_beside.exists():
            config_path = str(local_beside)
        elif local_cwd.exists():
            config_path = str(local_cwd)
        elif bundled.exists():
            config_path = str(bundled)
        else:
            # Build a minimal config from environment / safe defaults
            return _config_from_env()

    with open(config_path, 'r') as fh:
        yaml_config = yaml.safe_load(fh)

    flat_config = {
        'app_name': yaml_config.get('app', {}).get('name', 'AI Employee - Private & Secure'),
        'app_version': yaml_config.get('app', {}).get('version', '2.0.0'),
        'environment': yaml_config.get('app', {}).get('environment', 'production'),
        'debug': yaml_config.get('app', {}).get('debug', False),
        'host': yaml_config.get('server', {}).get('host', '127.0.0.1'),
        'port': yaml_config.get('server', {}).get('port', 8787),
        'security': SecurityConfig(**yaml_config.get('security', {})),
        'privacy': PrivacyConfig(**yaml_config.get('privacy', {})),
        'ai': AIConfig(**yaml_config.get('ai', {})),
        'logging': LoggingConfig(**yaml_config.get('logging', {})),
        'limits': LimitsConfig(**yaml_config.get('limits', {})),
    }

    # Environment variable always wins for the JWT secret
    jwt_secret = os.getenv('JWT_SECRET_KEY')
    if jwt_secret:
        flat_config['security'].jwt_secret_key = jwt_secret

    _check_jwt_secret(flat_config['security'].jwt_secret_key)
    return Config(**flat_config)


def _config_from_env() -> Config:
    """Build a Config entirely from environment variables and safe defaults."""
    jwt_secret = os.getenv('JWT_SECRET_KEY', '')
    _check_jwt_secret(jwt_secret)
    return Config(
        security=SecurityConfig(jwt_secret_key=jwt_secret),
        privacy=PrivacyConfig(),
        ai=AIConfig(),
        logging=LoggingConfig(),
        limits=LimitsConfig(),
    )


_PLACEHOLDER = "CHANGE_THIS_IN_SECURITY_LOCAL_YML_OR_SET_JWT_SECRET_KEY_ENV_VAR"


def _check_jwt_secret(secret: str) -> None:
    if not secret or secret == _PLACEHOLDER:
        raise ValueError(
            "Security Error: JWT secret key must be set. "
            "Export JWT_SECRET_KEY or create security.local.yml with a strong secret."
        )


def validate_security_config(config: Config) -> list[str]:
    """
    Validate security configuration and return a list of human-readable warnings.
    """
    warnings = []

    if config.host not in ("127.0.0.1", "localhost"):
        warnings.append(
            f"WARNING: Server is bound to {config.host}. "
            "For maximum security use 127.0.0.1 (localhost only)."
        )

    if config.debug and config.environment == "production":
        warnings.append(
            "WARNING: Debug mode is enabled in production — "
            "this may expose sensitive information."
        )

    if not config.privacy.external_api_calls_disabled:
        warnings.append(
            "INFO: External API calls are enabled. "
            "Set privacy.external_api_calls_disabled=true for maximum privacy."
        )

    if not config.privacy.encrypt_data_at_rest:
        warnings.append(
            "WARNING: Data encryption at rest is disabled. "
            "Enable privacy.encrypt_data_at_rest for better security."
        )

    return warnings

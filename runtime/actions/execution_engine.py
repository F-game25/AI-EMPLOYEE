"""Secure action execution layer with safety, permissions, and observability."""
from __future__ import annotations

import os
import threading
import time
import traceback
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class ActionError(RuntimeError):
    """Base error for action execution failures."""

    def __init__(self, message: str, *, recoverable: bool, context: dict | None = None):
        super().__init__(message)
        self.recoverable = recoverable
        self.context = context or {}


class ActionValidationError(ActionError):
    """Raised when an action payload fails validation."""

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message, recoverable=False, context=context)


class ActionPermissionError(ActionError):
    """Raised when a skill attempts a non-allowed action."""

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message, recoverable=False, context=context)


class ActionRateLimitError(ActionError):
    """Raised when action execution exceeds configured rate limits."""

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message, recoverable=True, context=context)


class ActionTimeoutError(ActionError):
    """Raised when action execution exceeds timeout policy."""

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message, recoverable=True, context=context)


@dataclass
class ActionFailure:
    """Structured failure payload for orchestration and audit."""

    reason: str
    stack_trace: str
    context: dict = field(default_factory=dict)
    category: str = "fatal"

    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "stack_trace": self.stack_trace,
            "context": self.context,
            "category": self.category,
        }


class ActionConfigLoader:
    """Centralized environment-driven config/secret loader."""

    def __init__(self) -> None:
        self.default_timeout_s = int(os.environ.get("ACTION_DEFAULT_TIMEOUT_S", "30"))
        self.default_max_retries = int(os.environ.get("ACTION_DEFAULT_MAX_RETRIES", "2"))
        self.default_backoff_s = float(os.environ.get("ACTION_RETRY_BACKOFF_S", "0.5"))
        self.default_rate_limit_per_min = int(os.environ.get("ACTION_RATE_LIMIT_PER_MIN", "30"))
        self.cache_ttl_s = int(os.environ.get("ACTION_CACHE_TTL_S", "60"))
        self.sandbox_dir = Path(
            os.environ.get("ACTION_SANDBOX_DIR", str(Path.home() / ".ai-employee" / "sandbox"))
        ).resolve()

    def get_secret(self, name: str) -> str:
        value = os.environ.get(name, "")
        if not value:
            raise ActionValidationError(f"Missing required secret env var: {name}", context={"env": name})
        return value


class PermissionPolicy:
    """Deny-by-default skill->action capability policy."""

    def __init__(self, mapping: dict[str, list[str]] | None = None):
        self._mapping = mapping if mapping is not None else self._load_env_mapping()

    def _load_env_mapping(self) -> dict[str, list[str]]:
        raw = os.environ.get("ACTION_PERMISSION_MAP", "").strip()
        if not raw:
            return {}
        mapping: dict[str, list[str]] = {}
        for pair in raw.split(";"):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            skill, raw_actions = pair.split(":", 1)
            actions = [a.strip().lower() for a in raw_actions.split(",") if a.strip()]
            if actions:
                mapping[skill.strip()] = actions
        return mapping

    def is_allowed(self, skill: str, action_kind: str) -> bool:
        allowed = self._mapping.get(skill, [])
        if not allowed:
            return False
        return action_kind.lower() in {a.lower() for a in allowed}


class BaseAction(ABC):
    """Standardized external action contract."""

    action_kind = "generic"

    def __init__(
        self,
        *,
        input_schema: dict[str, type] | None = None,
        timeout_s: int | None = None,
        max_retries: int | None = None,
        retry_backoff_s: float | None = None,
        rate_limit_per_minute: int | None = None,
        idempotent: bool = True,
    ) -> None:
        cfg = ActionConfigLoader()
        self.input_schema = input_schema or {}
        self.timeout_s = timeout_s if timeout_s is not None else cfg.default_timeout_s
        self.max_retries = max_retries if max_retries is not None else cfg.default_max_retries
        self.retry_backoff_s = retry_backoff_s if retry_backoff_s is not None else cfg.default_backoff_s
        self.rate_limit_per_minute = (
            rate_limit_per_minute
            if rate_limit_per_minute is not None
            else cfg.default_rate_limit_per_min
        )
        self.idempotent = idempotent

    def validate(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            raise ActionValidationError("Action payload must be a dict")
        for key, expected_type in self.input_schema.items():
            if key not in payload:
                raise ActionValidationError(f"Missing required input: {key}", context={"field": key})
            if expected_type is object:
                continue
            if not isinstance(payload[key], expected_type):
                raise ActionValidationError(
                    f"Invalid type for {key}: expected {expected_type.__name__}",
                    context={"field": key},
                )

    @abstractmethod
    def execute(self, payload: dict) -> Any:
        """Execute validated action payload."""


class BrowserAction(BaseAction):
    """Browser automation action."""

    action_kind = "browser"

    def __init__(
        self,
        *,
        executor: Callable[[dict], Any],
        input_schema: dict[str, type] | None = None,
        **kwargs: Any,
    ) -> None:
        schema = {"url": str, **(input_schema or {})}
        super().__init__(input_schema=schema, **kwargs)
        self._executor = executor

    def validate(self, payload: dict) -> None:
        super().validate(payload)
        url = str(payload.get("url", ""))
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ActionValidationError("BrowserAction url must be http/https", context={"url": url})

    def execute(self, payload: dict) -> Any:
        return self._executor(payload)


class APIAction(BaseAction):
    """External API action with optional batching support."""

    action_kind = "api"

    def __init__(
        self,
        *,
        executor: Callable[[dict], Any],
        batch_executor: Callable[[list[dict]], Any] | None = None,
        input_schema: dict[str, type] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(input_schema=input_schema or {}, **kwargs)
        self._executor = executor
        self._batch_executor = batch_executor

    def execute(self, payload: dict) -> Any:
        batch = payload.get("batch")
        if isinstance(batch, list) and self._batch_executor is not None:
            return self._batch_executor(batch)
        return self._executor(payload)


class FileSystemAction(BaseAction):
    """Filesystem action constrained to a sandbox directory."""

    action_kind = "filesystem"

    def __init__(
        self,
        *,
        executor: Callable[[dict], Any],
        sandbox_dir: Path | None = None,
        input_schema: dict[str, type] | None = None,
        **kwargs: Any,
    ) -> None:
        cfg = ActionConfigLoader()
        self._sandbox_dir = (sandbox_dir or cfg.sandbox_dir).resolve()
        schema = {"path": str, **(input_schema or {})}
        super().__init__(input_schema=schema, **kwargs)
        self._executor = executor

    def _resolve(self, path_value: str) -> Path:
        p = Path(path_value)
        if not p.is_absolute():
            p = self._sandbox_dir / p
        return p.resolve()

    def validate(self, payload: dict) -> None:
        super().validate(payload)
        resolved = self._resolve(str(payload.get("path", "")))
        self._sandbox_dir.mkdir(parents=True, exist_ok=True)
        if not str(resolved).startswith(str(self._sandbox_dir)):
            raise ActionValidationError(
                "FileSystemAction path escapes sandbox",
                context={"path": str(resolved), "sandbox": str(self._sandbox_dir)},
            )

    def execute(self, payload: dict) -> Any:
        patched = dict(payload)
        patched["path"] = str(self._resolve(str(payload.get("path", ""))))
        return self._executor(patched)


@dataclass
class ActionMetrics:
    """In-memory counters for action reliability and performance."""

    total: int = 0
    success: int = 0
    failures: int = 0
    recoverable_failures: int = 0
    fatal_failures: int = 0
    total_latency_s: float = 0.0
    cache_hits: int = 0
    retries: int = 0
    timeouts: int = 0

    def snapshot(self) -> dict:
        avg = self.total_latency_s / max(self.total, 1)
        return {
            "total": self.total,
            "success": self.success,
            "failures": self.failures,
            "recoverable_failures": self.recoverable_failures,
            "fatal_failures": self.fatal_failures,
            "success_rate": round(self.success / max(self.total, 1), 4),
            "avg_latency_s": round(avg, 4),
            "cache_hits": self.cache_hits,
            "retries": self.retries,
            "timeouts": self.timeouts,
        }


class SecureExecutionEngine:
    """Safe executor for real-world actions."""

    def __init__(
        self,
        *,
        permission_policy: PermissionPolicy | None = None,
        config: ActionConfigLoader | None = None,
    ) -> None:
        self._config = config or ActionConfigLoader()
        self._policy = permission_policy or PermissionPolicy()
        self._actions: dict[str, BaseAction] = {}
        self._metrics = ActionMetrics()
        self._lock = threading.Lock()
        self._rate_windows: dict[str, list[float]] = {}
        self._idempotency_cache: dict[str, dict] = {}
        self._result_cache: dict[str, tuple[float, dict]] = {}
        self._lazy_resources: dict[str, tuple[Callable[[], Any], Any]] = {}

    def register_action(self, name: str, action: BaseAction) -> None:
        self._actions[name] = action

    def register_lazy_resource(self, name: str, loader: Callable[[], Any]) -> None:
        self._lazy_resources[name] = (loader, None)

    def get_lazy_resource(self, name: str) -> Any:
        if name not in self._lazy_resources:
            raise KeyError(name)
        loader, value = self._lazy_resources[name]
        if value is None:
            value = loader()
            self._lazy_resources[name] = (loader, value)
        return value

    def _check_rate_limit(self, action_name: str, limit_per_min: int) -> None:
        now = time.time()
        with self._lock:
            window = self._rate_windows.setdefault(action_name, [])
            cutoff = now - 60.0
            window[:] = [t for t in window if t >= cutoff]
            if len(window) >= max(limit_per_min, 1):
                raise ActionRateLimitError(
                    f"Rate limit exceeded for action '{action_name}'",
                    context={"action": action_name, "limit_per_minute": limit_per_min},
                )
            window.append(now)

    def _cache_key(self, action_name: str, payload: dict, idempotency_key: str | None) -> str:
        stable_items = sorted((str(k), repr(v)) for k, v in payload.items())
        stable_payload = "|".join(f"{k}={v}" for k, v in stable_items)
        return f"{action_name}::{idempotency_key or ''}::{stable_payload}"

    def metrics(self) -> dict:
        return self._metrics.snapshot()

    def _format_failure(self, exc: Exception, context: dict) -> ActionFailure:
        if isinstance(exc, ActionError):
            category = "recoverable" if exc.recoverable else "fatal"
            merged = dict(context)
            merged.update(exc.context)
            return ActionFailure(
                reason=str(exc),
                stack_trace=traceback.format_exc(),
                context=merged,
                category=category,
            )
        return ActionFailure(
            reason=str(exc),
            stack_trace=traceback.format_exc(),
            context=context,
            category="fatal",
        )

    def execute(
        self,
        *,
        action_name: str,
        payload: dict,
        skill: str,
        idempotency_key: str | None = None,
    ) -> dict:
        start = time.time()
        self._metrics.total += 1

        action = self._actions.get(action_name)
        if action is None:
            failure = ActionFailure(
                reason=f"Unknown action: {action_name}",
                stack_trace="",
                context={"action": action_name},
                category="fatal",
            )
            self._metrics.failures += 1
            self._metrics.fatal_failures += 1
            self._metrics.total_latency_s += max(0.0, time.time() - start)
            return {"status": "error", "failure": failure.to_dict()}

        if not self._policy.is_allowed(skill, action.action_kind):
            failure = ActionFailure(
                reason=f"Permission denied for skill '{skill}' to run {action.action_kind}",
                stack_trace="",
                context={"skill": skill, "action_kind": action.action_kind, "action": action_name},
                category="fatal",
            )
            self._metrics.failures += 1
            self._metrics.fatal_failures += 1
            self._metrics.total_latency_s += max(0.0, time.time() - start)
            return {"status": "error", "failure": failure.to_dict()}

        cache_key = self._cache_key(action_name, payload, idempotency_key)
        if idempotency_key and action.idempotent and cache_key in self._idempotency_cache:
            self._metrics.cache_hits += 1
            self._metrics.success += 1
            self._metrics.total_latency_s += max(0.0, time.time() - start)
            return {"status": "executed", "result": self._idempotency_cache[cache_key], "cached": True}

        cached = self._result_cache.get(cache_key)
        if cached and (time.time() - cached[0]) <= self._config.cache_ttl_s:
            self._metrics.cache_hits += 1
            self._metrics.success += 1
            self._metrics.total_latency_s += max(0.0, time.time() - start)
            return {"status": "executed", "result": cached[1], "cached": True}

        failure_payload: dict | None = None
        for attempt in range(1, max(action.max_retries, 1) + 1):
            try:
                action.validate(payload)
                self._check_rate_limit(action_name, action.rate_limit_per_minute)

                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(action.execute, payload)
                    try:
                        result = fut.result(timeout=max(action.timeout_s, 1))
                    except FutureTimeoutError as exc:
                        self._metrics.timeouts += 1
                        raise ActionTimeoutError(
                            f"Action '{action_name}' timed out after {action.timeout_s}s",
                            context={"action": action_name, "timeout_s": action.timeout_s},
                        ) from exc

                if idempotency_key and action.idempotent:
                    self._idempotency_cache[cache_key] = result
                self._result_cache[cache_key] = (time.time(), result)
                self._metrics.success += 1
                self._metrics.total_latency_s += max(0.0, time.time() - start)
                return {"status": "executed", "result": result, "attempts": attempt}
            except Exception as exc:
                failure = self._format_failure(
                    exc,
                    context={
                        "action": action_name,
                        "skill": skill,
                        "attempt": attempt,
                    },
                )
                failure_payload = failure.to_dict()
                is_recoverable = failure.category == "recoverable"
                if is_recoverable:
                    self._metrics.recoverable_failures += 1
                else:
                    self._metrics.fatal_failures += 1
                if attempt < max(action.max_retries, 1) and is_recoverable:
                    self._metrics.retries += 1
                    backoff = action.retry_backoff_s * (2 ** (attempt - 1))
                    time.sleep(min(backoff, 30.0))
                    continue
                break

        self._metrics.failures += 1
        self._metrics.total_latency_s += max(0.0, time.time() - start)
        return {"status": "error", "failure": failure_payload or {}}

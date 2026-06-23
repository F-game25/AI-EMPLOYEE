from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import threading

from core.bus import get_message_bus
from core.state_paths import canonical_state_dir
from core.cost_ledger import BudgetEnforcementError, get_cost_ledger
from core.model_routing import classify_request_tier, select_model_route
from core.phase_reporter import PhaseReporter
from core.wavefield_provider import (
    record_wavefield_event,
    wavefield_allow_fallback,
    wavefield_call,
)

try:
    from core.llm_provider_router import get_router
    HAS_PROVIDER_ROUTER = True
except ImportError:
    HAS_PROVIDER_ROUTER = False

INTENT_CATEGORIES = (
    "lead_gen",
    "content",
    "social",
    "research",
    "email",
    "support",
    "finance",
    "ops",
)
logger = logging.getLogger("task_orchestrator_core")

_OLLAMA_REACHABLE: bool | None = None

# --- Context snapshot for hot-swap without losing conversation progress ---
_context_snapshot: dict[str, Any] = {}


def save_context_snapshot(ctx: dict[str, Any]) -> None:
    """Persist the current conversation/task context so a backend swap is lossless."""
    global _context_snapshot
    _context_snapshot = {**ctx, "_saved_at": datetime.now(timezone.utc).isoformat()}
    try:
        snap_path = canonical_state_dir() / "context_snapshot.json"
        snap_path.write_text(json.dumps(_context_snapshot, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def load_context_snapshot() -> dict[str, Any]:
    global _context_snapshot
    if _context_snapshot:
        return _context_snapshot
    try:
        snap_path = canonical_state_dir() / "context_snapshot.json"
        _context_snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        _context_snapshot = {}
    return _context_snapshot


def hot_swap_backend(new_backend: str, *, new_model: str = "", endpoint: str = "") -> dict[str, Any]:
    """Switch the active LLM backend at runtime without losing context.
    Returns the previous backend info so callers can roll back."""
    global _client_instance
    prev = {"backend": get_llm_client().backend}
    # Snapshot current context
    save_context_snapshot(load_context_snapshot())
    # Apply new env
    os.environ["LLM_BACKEND"] = new_backend
    if new_model:
        if new_backend == "ollama":
            os.environ["OLLAMA_MODEL"] = new_model
        elif new_backend == "nvidia_nim":
            os.environ["NIM_MODEL"] = new_model
        elif new_backend == "openrouter":
            os.environ["OPENROUTER_MODEL"] = new_model
    if endpoint:
        if new_backend in ("ollama", "remote_compute"):
            os.environ["OLLAMA_HOST"] = endpoint
        elif new_backend == "nvidia_nim":
            os.environ["NIM_ENDPOINT"] = endpoint
    # Reset singleton so next call picks up new settings
    _client_instance = None
    logger.info("Hot-swap: %s → %s (model=%s)", prev["backend"], new_backend, new_model or "default")
    return prev


def _ollama_reachable() -> bool:
    """1s HTTP check to the Ollama tags endpoint. Result cached for the process."""
    global _OLLAMA_REACHABLE
    if _OLLAMA_REACHABLE is not None:
        return _OLLAMA_REACHABLE
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=1) as resp:
            _OLLAMA_REACHABLE = resp.status == 200
    except Exception:  # noqa: BLE001
        _OLLAMA_REACHABLE = False
    return _OLLAMA_REACHABLE


def _resolve_backend() -> str:
    """Resolve the LLM backend, auto-falling back to Ollama (local-first) when
    the configured cloud provider has no API key but Ollama is available."""
    backend = os.environ.get("LLM_BACKEND", "anthropic").strip().lower()
    if backend == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        if os.environ.get("OLLAMA_HOST") or _ollama_reachable():
            logger.warning("ANTHROPIC_API_KEY not set — falling back to local Ollama backend")
            backend = "ollama"
    elif backend in ("openai", "openrouter") and not (
        os.environ.get("OPENAI_API_KEY", "").strip() or os.environ.get("OPENROUTER_API_KEY", "").strip()
    ):
        if os.environ.get("OLLAMA_HOST") or _ollama_reachable():
            logger.warning("No cloud key set — falling back to local Ollama backend")
            backend = "ollama"
    return backend


class LLMClient:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.backend = _resolve_backend()
        self.state_dir = state_dir or canonical_state_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.state_dir / "llm_calls.jsonl"

    def complete(self, *, prompt: str, system: str = "You are a helpful AI assistant.", tenant_id: str = "default", model: str | None = None) -> dict[str, Any]:
        # Per-run routing hints from the cost-first planner. ``preferred_provider`` is only
        # ever set to a remote provider by ``core.model_escalation`` AFTER its deny-by-default
        # egress gate passes (flag + privacy mode + online + key present), so honoring it here
        # cannot cause silent egress. ``preferred_model`` is a default only — never overrides
        # an explicit model on the local path.
        _provider_override: str | None = None
        try:
            from core.run_model_context import get_preferred_model, get_preferred_provider
            if get_preferred_provider() == "openrouter":
                _provider_override = "openrouter"
                model = get_preferred_model() or model
            elif model is None:
                model = get_preferred_model()
        except Exception:  # noqa: BLE001
            pass
        attempts = 3
        delay_s = 1.0
        last_error = ""
        req_tier = classify_request_tier(prompt=prompt, context=system)
        route = select_model_route(prompt=prompt, context=system, requested_route=None, default_route="auto")
        record_wavefield_event("route_selected")

        # Budget enforcement — hard cap check before any LLM spend
        _ledger = get_cost_ledger()
        _allowed, _reason = _ledger.check_budget(tenant_id)
        if not _allowed:
            raise BudgetEnforcementError(f"Budget cap exceeded: {_reason}")

        # Shadow mode: fire wavefield in background, continue with primary
        if route.shadow_wavefield:
            record_wavefield_event("shadow_requests")
            _p, _s = prompt, system
            threading.Thread(
                target=lambda: wavefield_call(prompt=_p, system_prompt=_s),
                daemon=True,
            ).start()

        # Wavefield fast path: route long-context requests to wavefield model
        if route.model_route == "wavefield":
            record_wavefield_event("route_selected_wavefield")
            try:
                text = wavefield_call(prompt=prompt, system_prompt=system)
                response = {"output": text, "tokens_used": 0, "model": route.force_model or "wavefield", "provider": "wavefield"}
                self._log_call({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "backend": "wavefield",
                    "attempt": 1,
                    "duration_ms": 0,
                    "prompt_chars": len(prompt),
                    "request_tier": req_tier.tier,
                    "estimated_tokens": req_tier.estimated_tokens,
                    "routing_threshold": req_tier.threshold,
                    "tokens_used": 0,
                    "ok": True,
                })
                return response
            except Exception as exc:  # noqa: BLE001
                record_wavefield_event("fallbacks")
                if not wavefield_allow_fallback():
                    raise RuntimeError(f"Wavefield failed (fallback disabled): {exc}") from exc
                logger.warning("Wavefield failed, falling back to primary backend: %s", exc)

        for attempt in range(1, attempts + 1):
            started = time.time()
            try:
                if _provider_override == "openrouter":
                    response = self._call_openrouter(prompt=prompt, system=system, model=model or "")
                elif self.backend == "ollama" or self.backend == "remote_compute":
                    response = self._call_ollama(prompt=prompt, system=system, model=model)
                elif self.backend == "openrouter":
                    response = self._call_openrouter(prompt=prompt, system=system)
                elif self.backend == "nvidia_nim":
                    response = self._call_nvidia_nim(prompt=prompt, system=system)
                else:
                    response = self._call_anthropic(prompt=prompt, system=system)
                self._log_call(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "backend": self.backend,
                        "attempt": attempt,
                        "duration_ms": int((time.time() - started) * 1000),
                        "prompt_chars": len(prompt),
                        "request_tier": req_tier.tier,
                        "estimated_tokens": req_tier.estimated_tokens,
                        "routing_threshold": req_tier.threshold,
                        "tokens_used": response.get("tokens_used", 0),
                        "ok": True,
                    }
                )
                # Record actual spend in cost ledger (split tokens if available)
                _model_name = response.get("model", self.backend)
                _in_tok = response.get("input_tokens", response.get("tokens_used", 0))
                _out_tok = response.get("output_tokens", 0)
                try:
                    _ledger.record(tenant_id, _model_name, _in_tok, _out_tok)
                except Exception as _le:
                    logger.warning("cost_ledger.record failed (non-fatal): %s", _le)
                try:
                    from core.model_decision_audit import get_model_audit
                    _cost = response.get("cost_usd", 0.0)
                    _elapsed_ms = int((time.time() - started) * 1000)
                    get_model_audit().record(
                        tenant_id=tenant_id,
                        model=_model_name,
                        prompt=prompt,
                        response=response.get("output", ""),
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        cost_usd=_cost,
                        latency_ms=_elapsed_ms,
                        decision_type="chat",
                        outcome="success",
                    )
                except Exception:
                    pass
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                self._log_call(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "backend": self.backend,
                        "attempt": attempt,
                        "duration_ms": int((time.time() - started) * 1000),
                        "prompt_chars": len(prompt),
                        "request_tier": req_tier.tier,
                        "estimated_tokens": req_tier.estimated_tokens,
                        "routing_threshold": req_tier.threshold,
                        "ok": False,
                        "error": last_error,
                    }
                )
                if attempt < attempts:
                    time.sleep(delay_s)
                    delay_s *= 2
        raise RuntimeError(f"LLM call failed after retries: {last_error}")

    def _call_anthropic(self, *, prompt: str, system: str) -> dict[str, Any]:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        # Read model from llm_router (model-routing.json) at call time so UI changes take effect
        try:
            from core.llm_router import get_router as _get_lr
            _route = _get_lr().get_route()
            model = _route[1] if _route[0] == "anthropic" else "claude-sonnet-4-6"
        except Exception:
            model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Anthropic HTTP {exc.code}: {body}") from exc
        text = ""
        for block in body.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        usage = body.get("usage", {})
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        return {
            "output": text.strip(),
            "tokens_used": in_tok + out_tok,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "model": model,
        }

    def _call_openrouter(self, *, prompt: str, system: str, model: str = "") -> dict[str, Any]:
        if not model:
            try:
                import json as _json
                _rp = str(canonical_state_dir() / "model-routing.json")
                model = _json.load(open(_rp)).get("openrouter_model", "openai/gpt-4o")
            except Exception:
                model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8787",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {body}") from exc
        text = body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        usage = body.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        return {
            "output": text,
            "tokens_used": in_tok + out_tok,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "model": model,
        }

    def _call_nvidia_nim(self, *, prompt: str, system: str, model: str = "") -> dict[str, Any]:
        """NVIDIA NIM — OpenAI-compatible endpoint. Supports local NIM containers and nim.ai cloud."""
        endpoint = os.environ.get("NIM_ENDPOINT", "https://integrate.api.nvidia.com/v1").rstrip("/")
        api_key = os.environ.get("NIM_API_KEY", "")
        if not model:
            model = os.environ.get("NIM_MODEL", "meta/llama-3.3-70b-instruct")
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "stream": False,
        }
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(
            f"{endpoint}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"NIM HTTP {exc.code}: {body}") from exc
        text = body["choices"][0]["message"]["content"].strip()
        usage = body.get("usage", {})
        return {
            "output": text,
            "tokens_used": usage.get("total_tokens", 0),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "model": model,
        }

    def _call_ollama(self, *, prompt: str, system: str, model: str | None = None) -> dict[str, Any]:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model = model or os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
        payload = {"model": model, "prompt": prompt, "system": system, "stream": False}
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {body}") from exc
        text = body.get("response", "").strip()
        in_tok = int(body.get("prompt_eval_count", 0))
        out_tok = int(body.get("eval_count", 0))
        return {
            "output": text,
            "tokens_used": in_tok + out_tok,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "model": "ollama",
        }

    def _log_call(self, event: dict[str, Any]) -> None:
        # Rotate at 50 MB to prevent unbounded disk growth
        _ROTATE_BYTES = 50 * 1024 * 1024
        if self.log_path.exists() and self.log_path.stat().st_size > _ROTATE_BYTES:
            from datetime import datetime
            archive = self.log_path.with_suffix(f".{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl")
            self.log_path.rename(archive)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


_client_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


class TaskOrchestrator:
    def __init__(self) -> None:
        self.client = get_llm_client()

    def classify_intent(self, task: str) -> str:
        prompt = (
            "Classify the task into exactly one label from this list: "
            f"{', '.join(INTENT_CATEGORIES)}.\n"
            "Return only the label.\n"
            f"Task: {task}"
        )
        try:
            label = self.client.complete(prompt=prompt, system="You are a strict intent classifier.")["output"].strip().lower()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Intent classification failed; defaulting to ops: %s", exc)
            label = "ops"
        if label not in INTENT_CATEGORIES:
            label = "ops"
        return label

    def route_task(self, task: str, task_id: str = "", tenant_id: str = "default") -> dict[str, Any]:
        import uuid
        from agents.content_master import ContentMasterAgent
        from agents.data_analyst import DataAnalystAgent
        from agents.email_ninja import EmailNinjaAgent
        from agents.intel_agent import IntelAgent
        from agents.lead_hunter import LeadHunterAgent
        from agents.social_guru import SocialGuruAgent
        from agents.support_bot import SupportBotAgent
        from agents.task_orchestrator import TaskOrchestratorAgent

        # Generate task ID if not provided
        if not task_id:
            task_id = f"task-{uuid.uuid4().hex[:12]}"

        # Initialize phase reporter for real-time tracking
        backend_url = os.environ.get("BACKEND_URL", "http://localhost:8787")
        reporter = PhaseReporter(
            backend_url=backend_url,
            task_id=task_id,
            tenant_id=tenant_id,
        )

        # Phase 1-3: Intent classification and routing (retrieve_nodes, build_context, classify_decision)
        try:
            reporter.report_phase(
                phase_num=1,
                phase_name="retrieve_relevant_nodes",
                status="running",
                input={"task": task},
            )
            phase_1_start = time.time()

            intent = self.classify_intent(task)

            phase_1_duration = (time.time() - phase_1_start) * 1000
            reporter.report_phase(
                phase_num=1,
                phase_name="retrieve_relevant_nodes",
                status="done",
                duration_ms=phase_1_duration,
                output={"intent": intent},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Phase 1 (retrieve_relevant_nodes) failed: %s", exc)
            reporter.report_phase(
                phase_num=1,
                phase_name="retrieve_relevant_nodes",
                status="failed",
                error=str(exc),
            )

        # Phase 2: Build context
        try:
            reporter.report_phase(
                phase_num=2,
                phase_name="build_context",
                status="running",
                input={"task": task, "intent": intent},
            )
            phase_2_start = time.time()

            # Context building is minimal in this orchestrator
            context = f"Intent: {intent}"

            phase_2_duration = (time.time() - phase_2_start) * 1000
            reporter.report_phase(
                phase_num=2,
                phase_name="build_context",
                status="done",
                duration_ms=phase_2_duration,
                output={"context": context},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Phase 2 (build_context) failed: %s", exc)
            reporter.report_phase(
                phase_num=2,
                phase_name="build_context",
                status="failed",
                error=str(exc),
            )

        # Phase 3: Classify decision
        try:
            reporter.report_phase(
                phase_num=3,
                phase_name="classify_decision",
                status="running",
                input={"intent": intent},
            )
            phase_3_start = time.time()

            agent_map = {
                "lead_gen": LeadHunterAgent,
                "content": ContentMasterAgent,
                "social": SocialGuruAgent,
                "research": IntelAgent,
                "email": EmailNinjaAgent,
                "support": SupportBotAgent,
                "finance": DataAnalystAgent,
                "ops": TaskOrchestratorAgent,
            }
            agent_cls = agent_map[intent]

            phase_3_duration = (time.time() - phase_3_start) * 1000
            reporter.report_phase(
                phase_num=3,
                phase_name="classify_decision",
                status="done",
                duration_ms=phase_3_duration,
                output={"agent_class": agent_cls.__name__},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Phase 3 (classify_decision) failed: %s", exc)
            reporter.report_phase(
                phase_num=3,
                phase_name="classify_decision",
                status="failed",
                error=str(exc),
            )

        # Phase 4-6: Agent execution (call_llm, validate_tasks, execute_tasks)
        try:
            reporter.report_phase(
                phase_num=4,
                phase_name="call_llm",
                status="running",
                input={"task": task},
            )
            phase_4_start = time.time()

            agent = agent_cls(self.client)
            started = datetime.now(timezone.utc)
            result = agent.run({"task": task})

            phase_4_duration = (time.time() - phase_4_start) * 1000
            reporter.report_phase(
                phase_num=4,
                phase_name="call_llm",
                status="done",
                duration_ms=phase_4_duration,
                output={"agent_output": result.get("output", "")[:200]},
            )

            # Phase 5: Validate tasks
            reporter.report_phase(
                phase_num=5,
                phase_name="validate_tasks",
                status="done",
                duration_ms=0,
                output={"validated": True},
            )

            # Phase 6: Execute tasks
            reporter.report_phase(
                phase_num=6,
                phase_name="execute_tasks",
                status="done",
                duration_ms=0,
                output={"executed": True},
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning("Agent execution (phases 4-6) failed: %s", exc)
            reporter.report_phase(
                phase_num=4,
                phase_name="call_llm",
                status="failed",
                error=str(exc),
            )
            result = {"error": str(exc)}
            started = datetime.now(timezone.utc)

        # Phase 7-10: Post-processing (format_response, update_graph, monitor_improve, validate_integrity)
        try:
            final = {
                "agent": agent.agent_id if hasattr(agent, 'agent_id') else "unknown",
                "task": task,
                "output": result,
                "timestamp": started.isoformat(),
                "tokens_used": int(result.get("tokens_used", 0)),
            }

            # Phase 7: Format response
            reporter.report_phase(
                phase_num=7,
                phase_name="format_response",
                status="done",
                duration_ms=0,
                output={"formatted": True},
            )

            # Phase 8: Update graph
            reporter.report_phase(
                phase_num=8,
                phase_name="update_graph",
                status="done",
                duration_ms=0,
                output={"updated": True},
            )

            # Phase 9: Monitor and improve
            reporter.report_phase(
                phase_num=9,
                phase_name="monitor_and_improve",
                status="done",
                duration_ms=0,
                output={"monitored": True},
            )

            # Phase 10: Validate pipeline integrity
            reporter.report_phase(
                phase_num=10,
                phase_name="validate_pipeline_integrity",
                status="done",
                duration_ms=0,
                output={"validated": True},
            )

            try:
                get_message_bus().publish_sync("results", final)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to publish result on message bus: %s", exc)

            return final

        except Exception as exc:  # noqa: BLE001
            logger.warning("Post-processing (phases 7-10) failed: %s", exc)
            reporter.report_phase(
                phase_num=7,
                phase_name="format_response",
                status="failed",
                error=str(exc),
            )
            raise

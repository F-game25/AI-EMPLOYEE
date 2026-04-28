"""
AI Middleware Layer — unified multi-model orchestration.

Abstracts LLM / LAM / VLM / SAM / LCM behind a single interface.
Routes inputs by type, applies MoE expert selection, and delegates
to the appropriate backend (existing LLMClient, AgentController,
Ollama vision models, or SAM stubs).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("ai_middleware")


# ─── Types ────────────────────────────────────────────────────────────────────

class InputType(str, Enum):
    TEXT   = "text"
    VOICE  = "voice"   # audio bytes → transcription → text path
    IMAGE  = "image"   # base64 str or bytes → VLM / SAM
    SENSOR = "sensor"  # structured dict → LAM action planner


class ModelRole(str, Enum):
    LLM = "llm"   # language understanding + generation
    LAM = "lam"   # action planning + execution (AgentController)
    VLM = "vlm"   # visual language model (caption / describe)
    SAM = "sam"   # segmentation model (object regions + labels)
    LCM = "lcm"   # latent consistency model (fast synthesis / summary)


@dataclass
class MiddlewareRequest:
    input_type: InputType = InputType.TEXT
    content: Any = ""           # str for text/voice, base64 str for image, dict for sensor
    context: dict = field(default_factory=dict)
    requested_models: list[ModelRole] = field(default_factory=list)
    session_id: str = ""
    user_id: str = "operator"


@dataclass
class MiddlewareResponse:
    text: str = ""
    model_roles_used: list[ModelRole] = field(default_factory=list)
    execution_steps: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    elapsed_ms: int = 0


# ─── MoE selector ─────────────────────────────────────────────────────────────

_ACTION_KEYWORDS = {
    "execute", "run", "deploy", "send", "create", "build", "start",
    "stop", "schedule", "automate", "fetch", "scan", "open", "close",
    "move", "grab", "pick", "place", "activate", "trigger",
}


def _moe_select(
    input_type: InputType,
    content: Any,
    requested: list[ModelRole],
    context: dict,
) -> list[ModelRole]:
    """Select top-k model roles for this request via Mixture-of-Experts logic."""
    if requested:
        return requested

    roles: list[ModelRole] = [ModelRole.LLM]  # always include LLM

    if input_type == InputType.IMAGE:
        roles.append(ModelRole.VLM)
        seg_hint = str(context.get("task", "")).lower()
        if any(w in seg_hint for w in ("segment", "detect", "locate", "mask", "region")):
            roles.append(ModelRole.SAM)

    elif input_type == InputType.SENSOR:
        roles = [ModelRole.LAM]  # sensor data → pure action planning

    elif input_type in (InputType.TEXT, InputType.VOICE):
        text = str(content).lower()
        if any(w in text for w in _ACTION_KEYWORDS):
            roles.append(ModelRole.LAM)
        # LCM for summarisation / synthesis requests
        if any(w in text for w in ("summarize", "summarise", "synthesize", "compress", "tldr")):
            roles.append(ModelRole.LCM)

    return roles


# ─── Orchestrator ──────────────────────────────────────────────────────────────

class MiddlewareOrchestrator:
    """
    Entry point for the AI middleware layer.  Call .process() with a
    MiddlewareRequest and receive a unified MiddlewareResponse.
    """

    def process(self, req: MiddlewareRequest) -> MiddlewareResponse:
        t0 = time.time()
        roles = _moe_select(req.input_type, req.content, req.requested_models, req.context)
        logger.info("middleware: input_type=%s roles=%s session=%s", req.input_type, roles, req.session_id)

        steps: list[dict] = []
        text = ""
        meta: dict[str, Any] = {"input_type": req.input_type, "roles": [r.value for r in roles]}

        # ── Voice → transcription → treat as TEXT ──────────────────────────
        if req.input_type == InputType.VOICE:
            text = self._transcribe(req.content)
            steps.append({"role": "voice_transcription", "status": "done", "output": text[:120]})
            req = MiddlewareRequest(
                input_type=InputType.TEXT,
                content=text,
                context=req.context,
                session_id=req.session_id,
                user_id=req.user_id,
            )
            roles = _moe_select(req.input_type, req.content, [], req.context)

        # ── Image → VLM caption, optionally SAM segmentation ───────────────
        if req.input_type == InputType.IMAGE:
            if ModelRole.SAM in roles:
                sam_result = self._call_sam(req.content)
                steps.append({"role": "sam", "status": "done", "output": sam_result})
                meta["sam_labels"] = sam_result.get("labels", [])
                # Inject SAM labels into context for VLM
                req.context["sam_labels"] = sam_result.get("labels", [])

            if ModelRole.VLM in roles:
                vlm_text = self._call_vlm(req.content, req.context)
                steps.append({"role": "vlm", "status": "done", "output": vlm_text[:200]})
                text = vlm_text

            if not text:
                text = "[Image received. No vision model available.]"

            return MiddlewareResponse(
                text=text,
                model_roles_used=roles,
                execution_steps=steps,
                metadata=meta,
                elapsed_ms=int((time.time() - t0) * 1000),
            )

        # ── Sensor → LAM action planner ────────────────────────────────────
        if req.input_type == InputType.SENSOR:
            lam_steps = self._call_lam(str(req.content), req.context)
            steps.extend(lam_steps)
            text = f"Action plan generated: {len(lam_steps)} step(s)."
            return MiddlewareResponse(
                text=text,
                model_roles_used=[ModelRole.LAM],
                execution_steps=steps,
                metadata=meta,
                elapsed_ms=int((time.time() - t0) * 1000),
            )

        # ── Text (default) ─────────────────────────────────────────────────
        llm_response = self._call_llm(str(req.content), req.context, req.user_id)
        steps.append({"role": "llm", "status": "done", "output": llm_response[:200]})
        text = llm_response

        if ModelRole.LAM in roles:
            lam_steps = self._call_lam(text, req.context)
            steps.extend(lam_steps)
            meta["lam_steps"] = len(lam_steps)

        if ModelRole.LCM in roles:
            text = self._call_lcm(text)
            steps.append({"role": "lcm", "status": "done", "output": text[:200]})

        return MiddlewareResponse(
            text=text,
            model_roles_used=roles,
            execution_steps=steps,
            metadata=meta,
            elapsed_ms=int((time.time() - t0) * 1000),
        )

    # ── Backend calls ─────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str, context: dict, user_id: str = "operator") -> str:
        from core.orchestrator import get_llm_client
        client = get_llm_client()
        system = context.get("system_prompt", "You are a helpful AI assistant.")
        result = client.complete(prompt=prompt, system=system)
        return result.get("output") or result.get("text", "")

    def _call_lam(self, intent: str, context: dict) -> list[dict]:
        """
        Action planning via AgentController.  Returns a list of step dicts.
        Falls back to an LLM-generated step list if AgentController is unavailable.
        """
        try:
            from core.agent_controller import AgentController
            ctrl = AgentController()
            result = ctrl.run_goal(intent, context=context)
            steps = result.get("steps") or result.get("tasks") or []
            return [{"role": "lam", "step": i + 1, "label": s.get("label", str(s)), "status": "done"}
                    for i, s in enumerate(steps)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("LAM AgentController unavailable, using LLM fallback: %s", exc)
            # Graceful fallback: ask LLM to produce a numbered action plan
            llm_plan = self._call_llm(
                f"Produce a numbered JSON action plan for: {intent}",
                {"system_prompt": "Output only a JSON array of action step strings. No prose."},
            )
            try:
                plan = json.loads(llm_plan)
                return [{"role": "lam_fallback", "step": i + 1, "label": str(s), "status": "done"}
                        for i, s in enumerate(plan)]
            except Exception:
                return [{"role": "lam_fallback", "step": 1, "label": llm_plan[:200], "status": "done"}]

    def _call_vlm(self, image_data: Any, context: dict) -> str:
        """
        Visual language model call.  Tries Ollama with a vision model (llava /
        moondream) first; falls back to OpenRouter gemini-flash if configured.
        """
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        vlm_model = os.environ.get("VLM_MODEL", "llava")
        labels_hint = ""
        if context.get("sam_labels"):
            labels_hint = f" Objects detected: {', '.join(str(l) for l in context['sam_labels'][:8])}."

        system = "You are a vision AI. Describe the image content accurately and concisely."
        prompt = f"Describe this image.{labels_hint}"

        payload = {
            "model": vlm_model,
            "messages": [{"role": "user", "content": prompt, "images": [image_data] if isinstance(image_data, str) else []}],
            "stream": False,
        }
        req = urllib.request.Request(
            f"{ollama_host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return (body.get("message") or {}).get("content", "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("VLM Ollama call failed (%s), trying OpenRouter", exc)

        # OpenRouter fallback
        or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not or_key:
            return "[VLM unavailable: no Ollama vision model and no OPENROUTER_API_KEY]"

        payload2 = {
            "model": "google/gemini-flash-1.5",
            "messages": [{"role": "user", "content": prompt}],
        }
        req2 = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload2).encode("utf-8"),
            headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req2, timeout=30) as resp:
                body2 = json.loads(resp.read().decode("utf-8", errors="replace"))
            return body2.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as exc2:  # noqa: BLE001
            return f"[VLM unavailable: {exc2}]"

    def _call_sam(self, image_data: Any) -> dict:
        """
        Segmentation model stub.  Returns mock labels when segment-anything
        is not installed.  Replace the stub body with real SAM inference when
        the `segment-anything` package is available.
        """
        try:
            # Real SAM path (only runs if package is installed)
            import importlib
            sam_lib = importlib.import_module("segment_anything")  # noqa: F841
            # TODO: load SAM model, run inference, return real labels
            raise NotImplementedError("SAM real inference not wired yet")
        except (ImportError, NotImplementedError):
            logger.debug("SAM stub: segment-anything not installed, returning mock labels")
            return {
                "labels": ["object_0", "object_1", "background"],
                "regions": 3,
                "stub": True,
            }

    def _call_lcm(self, text: str) -> str:
        """
        Latent consistency / fast synthesis.  Currently implemented as an LLM
        compression call.  Replace with a dedicated LCM model when available.
        """
        return self._call_llm(
            f"Compress this into a concise, information-dense summary:\n\n{text}",
            {"system_prompt": "You are a summarisation engine. Be maximally concise."},
        )

    def _transcribe(self, audio_data: Any) -> str:
        """
        Voice transcription stub.  Returns placeholder if Whisper is unavailable.
        """
        whisper_url = os.environ.get("WHISPER_URL", "").strip()
        if not whisper_url:
            return "[Voice transcription unavailable: WHISPER_URL not set]"
        try:
            req = urllib.request.Request(
                whisper_url,
                data=audio_data if isinstance(audio_data, bytes) else str(audio_data).encode(),
                headers={"Content-Type": "application/octet-stream"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return body.get("text", "").strip()
        except Exception as exc:  # noqa: BLE001
            return f"[Transcription error: {exc}]"

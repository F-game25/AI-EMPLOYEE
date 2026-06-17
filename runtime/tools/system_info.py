"""System-info tools — honest, deterministic, read-only probes of the host.

These exist so the teammate can ANSWER system questions ("what time is it on my
PC?", "what CPU do I have?", "which folder are we in?") by measuring the real
machine instead of explaining how the user could check manually.

Every tool returns real, measured values from the OS — never fabricated. When a
value genuinely cannot be read (e.g. no NVIDIA GPU present), the field is marked
unavailable with a reason rather than guessed.

Self-contained on purpose: no import of a hardware_profiler module (a parallel
effort owns that) — these tools only use the stdlib + an optional ``nvidia-smi``
probe, so they never crash and have no cross-module dependency.

Registered into ``tools.registry`` (both the module-level dict registry and the
class-based ``ToolRegistry`` singleton) at the bottom of this file.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

from .registry import register_tool

logger = logging.getLogger("tools.system_info")

# nvidia-smi probe bounds — keep the call cheap and never hang a turn.
_NVIDIA_SMI_TIMEOUT_S = 4


# ── system_local_time ─────────────────────────────────────────────────────────

def system_local_time(**_: Any) -> dict:
    """Current local OS time.

    Returns::

        {iso, hhmm, timezone, epoch}

    Values are read from the OS clock at call time — real, never cached.
    """
    now = datetime.now().astimezone()
    tzname = now.tzname() or ""
    if not tzname:
        # Fall back to the platform's configured zone abbreviation.
        tzname = datetime.now(timezone.utc).astimezone().tzname() or "local"
    return {
        "status": "ok",
        "iso": now.isoformat(),
        "hhmm": now.strftime("%H:%M"),
        "timezone": tzname,
        "epoch": now.timestamp(),
    }


# ── system_hardware ───────────────────────────────────────────────────────────

def system_hardware(**_: Any) -> dict:
    """Real CPU / RAM / GPU snapshot from the host (read-only).

    Returns a dict with ``cpu``, ``ram`` and ``gpu`` sections. Any section that
    cannot be measured is marked ``{"available": False, "reason": ...}`` — never
    guessed.
    """
    return {
        "status": "ok",
        "cpu": _cpu_info(),
        "ram": _ram_info(),
        "gpu": _gpu_info(),
    }


def _cpu_info() -> dict:
    cores_logical = os.cpu_count()
    model = platform.processor() or ""
    cores_physical = None
    # /proc/cpuinfo gives a precise model name + physical-core count on Linux.
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if not model:
            m = re.search(r"^model name\s*:\s*(.+)$", text, re.MULTILINE)
            if m:
                model = m.group(1).strip()
        core_ids = set(re.findall(r"^core id\s*:\s*(\d+)$", text, re.MULTILINE))
        phys_ids = set(re.findall(r"^physical id\s*:\s*(\d+)$", text, re.MULTILINE))
        if core_ids and phys_ids:
            cores_physical = len(core_ids) * len(phys_ids)
        elif core_ids:
            cores_physical = len(core_ids)
    except Exception:  # noqa: BLE001 — best-effort; logical count still returned
        pass
    if not model:
        model = platform.machine() or "unknown"
    return {
        "available": True,
        "model": model,
        "arch": platform.machine() or "",
        "cores_logical": cores_logical,
        "cores_physical": cores_physical,
    }


def _ram_info() -> dict:
    total = available = None
    # Linux: parse /proc/meminfo (kB → bytes). Most accurate, no deps.
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            mem = fh.read()
        mt = re.search(r"^MemTotal:\s*(\d+)\s*kB", mem, re.MULTILINE)
        ma = re.search(r"^MemAvailable:\s*(\d+)\s*kB", mem, re.MULTILINE)
        if mt:
            total = int(mt.group(1)) * 1024
        if ma:
            available = int(ma.group(1)) * 1024
    except Exception:  # noqa: BLE001
        pass
    # Portable fallback via sysconf where /proc is absent (non-Linux).
    if total is None:
        try:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError, AttributeError):
            pass
    if total is None:
        return {"available": False, "reason": "memory info not readable on this OS"}
    out: dict[str, Any] = {
        "available": True,
        "total_bytes": total,
        "total_gb": round(total / (1024 ** 3), 2),
    }
    if available is not None:
        out["available_bytes"] = available
        out["available_gb"] = round(available / (1024 ** 3), 2)
    return out


def _gpu_info() -> dict:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"available": False, "reason": "gpu unavailable (no nvidia-smi)"}
    try:
        proc = subprocess.run(
            [smi, "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=_NVIDIA_SMI_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — probe must never crash a turn
        return {"available": False, "reason": f"nvidia-smi failed: {exc}"}
    if proc.returncode != 0:
        return {"available": False,
                "reason": f"nvidia-smi exit {proc.returncode}: "
                          f"{(proc.stderr or '').strip()[:200]}"}
    gpus: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name, total_mib, free_mib = parts[0], parts[1], parts[2]
        gpus.append({
            "name": name,
            "vram_total_mb": _int_or_none(total_mib),
            "vram_free_mb": _int_or_none(free_mib),
        })
    if not gpus:
        return {"available": False, "reason": "nvidia-smi returned no GPUs"}
    return {"available": True, "count": len(gpus), "gpus": gpus}


def _int_or_none(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# ── system_cwd ────────────────────────────────────────────────────────────────

def system_cwd(**_: Any) -> dict:
    """Current working directory of the running process (real path)."""
    cwd = os.getcwd()
    return {
        "status": "ok",
        "cwd": cwd,
        "name": os.path.basename(cwd.rstrip(os.sep)) or cwd,
    }


# ── Registration ──────────────────────────────────────────────────────────────
# Module-level dict registry (call(input_data) -> dict).

def _wrap(fn):
    """Adapt a keyword-style tool to the dict-in/dict-out registry contract."""
    def _call(input_data: dict[str, Any]) -> dict[str, Any]:
        return fn(**(input_data or {}))
    return _call


register_tool(
    name="system_local_time",
    description="Current local OS time (iso, hh:mm, timezone). Real OS clock — no fabrication.",
    call=_wrap(system_local_time),
    input_schema={"type": "object", "properties": {}},
    output_schema={
        "type": "object",
        "properties": {
            "iso": {"type": "string"},
            "hhmm": {"type": "string"},
            "timezone": {"type": "string"},
            "epoch": {"type": "number"},
        },
    },
    tags=["system", "time", "read-only"],
)

register_tool(
    name="system_hardware",
    description="Real CPU model/cores, RAM total/available and GPU name/VRAM (nvidia-smi if present).",
    call=_wrap(system_hardware),
    input_schema={"type": "object", "properties": {}},
    output_schema={
        "type": "object",
        "properties": {
            "cpu": {"type": "object"},
            "ram": {"type": "object"},
            "gpu": {"type": "object"},
        },
    },
    tags=["system", "hardware", "read-only"],
)

register_tool(
    name="system_cwd",
    description="Current working directory of the running process.",
    call=_wrap(system_cwd),
    input_schema={"type": "object", "properties": {}},
    output_schema={
        "type": "object",
        "properties": {"cwd": {"type": "string"}, "name": {"type": "string"}},
    },
    tags=["system", "filesystem", "read-only"],
)


def register_system_tools(registry) -> None:
    """Register the three system-info tools on a class-based ``ToolRegistry``.

    Risk 0 — read-only probes. Idempotent: safe to call more than once.
    """
    registry.register("system_local_time", system_local_time, 0,
                      "Current local OS time (iso/hh:mm/timezone)")
    registry.register("system_hardware", system_hardware, 0,
                      "Real CPU/RAM/GPU snapshot of the host")
    registry.register("system_cwd", system_cwd, 0,
                      "Current working directory of the process")

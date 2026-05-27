"""
ASCEND AI — System Monitor
Polls CPU, RAM, GPU, and temperature every 2 seconds.
Falls back gracefully when GPUtil is unavailable.
"""

import asyncio

import psutil

try:
    import GPUtil

    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

_cache: dict = {}


async def poll_forever():
    """Background loop — updates cached stats every 2 seconds."""
    while True:
        _cache["stats"] = _read_stats()
        await asyncio.sleep(2)


def _read_stats() -> dict:
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()

    temp = 0.0
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            first = next(iter(temps.values()))
            temp = first[0].current if first else 0.0
    except Exception:
        pass

    gpu = 0.0
    if GPU_AVAILABLE:
        try:
            gpus = GPUtil.getGPUs()
            gpu = gpus[0].load * 100 if gpus else 0.0
        except Exception:
            pass

    return {
        "cpu_percent": cpu,
        "ram_used_gb": round(ram.used / 1e9, 1),
        "ram_total_gb": round(ram.total / 1e9, 1),
        "gpu_percent": round(gpu, 1),
        "temp_celsius": round(temp, 1),
    }


def get_stats() -> dict:
    """Return the latest cached stats or read them on the fly."""
    return _cache.get("stats", _read_stats())

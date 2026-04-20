"""ASCEND AI — System Router"""

import time

import psutil
from fastapi import APIRouter

from services.error_collector import get_errors
from services.system_monitor import get_stats

router = APIRouter()


@router.get("/system/stats")
def stats():
    return get_stats()


@router.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@router.get("/system/health")
def system_health():
    """Real system health check with diagnostics."""
    cpu = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime = time.time() - psutil.boot_time()
    errors = get_errors(limit=10)

    warnings = []
    if cpu > 85:
        warnings.append(f"High CPU usage: {cpu:.1f}%")
    if ram.percent > 85:
        warnings.append(f"High memory usage: {ram.percent:.1f}%")
    if disk.free / (1024 ** 3) < 2:
        warnings.append(f"Low disk space: {disk.free / (1024 ** 3):.1f} GB free")

    # Score: start at 100, deduct per warning and error
    score = max(0, 100 - len(warnings) * 15 - len(errors) * 2)

    return {
        "cpu_usage": cpu,
        "memory_usage": ram.percent,
        "memory_used_mb": ram.used // (1024 ** 2),
        "memory_total_mb": ram.total // (1024 ** 2),
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "uptime_seconds": round(uptime),
        "error_count": len(errors),
        "warnings": warnings,
        "health_score": score,
        "ts": time.time(),
    }


_HIGH_PRIORITY_NICE = -5  # Reduce niceness (increase priority) by 5 levels


@router.post("/system/boost")
def boost_priority():
    """Boost system priority — sets the process to high niceness where permitted."""
    try:
        import os
        proc = psutil.Process(os.getpid())
        proc.nice(_HIGH_PRIORITY_NICE)
        return {"success": True, "message": "Priority boosted"}
    except (psutil.AccessDenied, PermissionError):
        return {"success": False, "message": "Insufficient permissions to boost priority"}

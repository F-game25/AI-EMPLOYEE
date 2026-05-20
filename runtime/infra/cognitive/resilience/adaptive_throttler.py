import asyncio
import logging
import psutil
from typing import Optional
from .schema import DegradationLevel

logger = logging.getLogger(__name__)


class AdaptiveThrottler:
    def __init__(self, poll_interval_s: float = 5.0):
        self.poll_interval_s = poll_interval_s
        self.cpu_percent = 0.0
        self.mem_percent = 0.0
        self.degradation_level = DegradationLevel.NONE
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(self.poll_interval_s)
            self._poll_system_load()

    def _poll_system_load(self) -> None:
        try:
            self.cpu_percent = psutil.cpu_percent(interval=0.1)
            self.mem_percent = psutil.virtual_memory().percent

            if self.cpu_percent >= 95 or self.mem_percent >= 95:
                self.degradation_level = DegradationLevel.SEVERE
            elif self.cpu_percent >= 85 or self.mem_percent >= 85:
                self.degradation_level = DegradationLevel.MODERATE
            elif self.cpu_percent >= 70 or self.mem_percent >= 70:
                self.degradation_level = DegradationLevel.LIGHT
            else:
                self.degradation_level = DegradationLevel.NONE

            logger.debug(
                "System load: CPU=%.1f%%, Memory=%.1f%%, Degradation=%s",
                self.cpu_percent,
                self.mem_percent,
                self.degradation_level,
            )
        except Exception as e:
            logger.warning("Failed to poll system load: %s", e)

    def should_throttle(self, tier_name: str) -> bool:
        if self.degradation_level == DegradationLevel.NONE:
            return False
        if self.degradation_level == DegradationLevel.LIGHT and tier_name == "p3":
            return True
        if self.degradation_level == DegradationLevel.MODERATE and tier_name in ["p2", "p3"]:
            return True
        if self.degradation_level == DegradationLevel.SEVERE and tier_name in ["p1", "p2", "p3"]:
            return True
        if self.degradation_level == DegradationLevel.CRITICAL:
            return tier_name != "p0"

        return False

    def get_status(self) -> dict:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "mem_percent": round(self.mem_percent, 1),
            "degradation_level": self.degradation_level.value,
        }

    def stop(self) -> None:
        self._running = False


_instance: Optional[AdaptiveThrottler] = None


def get_adaptive_throttler() -> AdaptiveThrottler:
    global _instance
    if _instance is None:
        _instance = AdaptiveThrottler()
    return _instance

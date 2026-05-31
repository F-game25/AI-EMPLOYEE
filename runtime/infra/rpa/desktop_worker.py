"""DesktopWorker — pyautogui + subprocess desktop control."""
from __future__ import annotations
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pyautogui
    _PYAUTOGUI_OK = True
    pyautogui.FAILSAFE = True       # move mouse to corner to abort
    pyautogui.PAUSE = 0.05
except ImportError:
    _PYAUTOGUI_OK = False


class DesktopWorker:
    """Thin wrapper around pyautogui for desktop automation."""

    @property
    def available(self) -> bool:
        return _PYAUTOGUI_OK

    def type_text(self, text: str, interval: float = 0.02) -> bool:
        if not _PYAUTOGUI_OK:
            return False
        pyautogui.typewrite(text, interval=interval)
        return True

    def hotkey(self, *keys: str) -> bool:
        if not _PYAUTOGUI_OK:
            return False
        pyautogui.hotkey(*keys)
        return True

    def click(self, x: int, y: int, button: str = "left") -> bool:
        if not _PYAUTOGUI_OK:
            return False
        pyautogui.click(x, y, button=button)
        return True

    def screenshot(self) -> Optional[bytes]:
        if not _PYAUTOGUI_OK:
            return None
        try:
            from PIL import Image
            import io
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.warning("Desktop screenshot failed: %s", e)
            return None

    def find_window(self, title_fragment: str) -> Optional[dict]:
        """Return window info dict via wmctrl (Linux) or None."""
        try:
            out = subprocess.check_output(["wmctrl", "-l"], text=True, timeout=5)
            for line in out.splitlines():
                if title_fragment.lower() in line.lower():
                    parts = line.split(None, 3)
                    return {"win_id": parts[0], "title": parts[3] if len(parts) > 3 else ""}
        except Exception:
            pass
        return None

    def focus_window(self, win_id: str) -> bool:
        try:
            subprocess.run(["wmctrl", "-ia", win_id], timeout=5, check=True)
            return True
        except Exception:
            return False

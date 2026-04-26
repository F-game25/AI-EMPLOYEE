"""ASCEND AI — Settings Router"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_settings: dict = {
    "general": {"auto_start_agents": False, "log_level": "info"},
    "mode_permissions": {"forge": True, "money": True, "blacklight": True},
    "api_keys": {},
    "appearance": {"font_size": "normal", "animation_intensity": "full"},
    "backup": {},
}

_defaults = dict(_settings)


class SettingsUpdate(BaseModel):
    settings: dict


@router.get("/settings")
def get_settings():
    safe = {k: v for k, v in _settings.items() if k != "api_keys"}
    safe["api_keys"] = {k: "••••••" for k in _settings.get("api_keys", {})}
    return safe


@router.post("/settings")
def update_settings(req: SettingsUpdate):
    _settings.update(req.settings)
    return {"success": True}


@router.post("/settings/reset")
def reset_settings():
    _settings.clear()
    _settings.update(_defaults)
    return {"success": True}

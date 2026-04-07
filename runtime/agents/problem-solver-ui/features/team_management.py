"""Team Management — multi-user support with role-based permissions."""
import json
import secrets
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/team", tags=["team"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "team.json"

ROLES = {
    "owner": {"label": "Owner", "permissions": ["*"]},
    "admin": {"label": "Admin", "permissions": ["read", "write", "manage_agents", "manage_team"]},
    "manager": {"label": "Manager", "permissions": ["read", "write", "manage_agents"]},
    "member": {"label": "Member", "permissions": ["read", "write"]},
    "viewer": {"label": "Viewer", "permissions": ["read"]},
}


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"members": [], "invitations": [], "activity": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/members")
def list_members():
    data = _load()
    return JSONResponse([{k: v for k, v in m.items() if k != "password_hash"} for m in data["members"]])


@router.post("/members/invite")
async def invite_member(payload: dict):
    data = _load()
    email = payload.get("email", "").strip().lower()
    if not email:
        return JSONResponse({"error": "email required"}, status_code=400)
    if any(m.get("email") == email for m in data["members"]):
        return JSONResponse({"error": "member already exists"}, status_code=409)
    invitation = {
        "id": str(uuid.uuid4())[:8],
        "email": email,
        "role": payload.get("role", "member"),
        "token": secrets.token_urlsafe(24),
        "invited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "pending",
    }
    data["invitations"].append(invitation)
    _save(data)
    return JSONResponse({
        "ok": True,
        "invitation_id": invitation["id"],
        "token": invitation["token"],
    })


@router.post("/members/accept")
async def accept_invitation(payload: dict):
    data = _load()
    token = payload.get("token", "")
    invitation = next(
        (i for i in data["invitations"] if i.get("token") == token and i.get("status") == "pending"),
        None,
    )
    if not invitation:
        return JSONResponse({"error": "invalid or expired invitation"}, status_code=400)
    member = {
        "id": str(uuid.uuid4())[:8],
        "email": invitation["email"],
        "name": payload.get("name", invitation["email"].split("@")[0]),
        "role": invitation["role"],
        "avatar": "",
        "joined_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_active": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "active",
    }
    data["members"].append(member)
    invitation["status"] = "accepted"
    _save(data)
    return JSONResponse({"ok": True, "member": member})


@router.patch("/members/{member_id}")
async def update_member(member_id: str, payload: dict):
    data = _load()
    for m in data["members"]:
        if m["id"] == member_id:
            m.update({k: v for k, v in payload.items() if k not in ("id", "password_hash")})
            _save(data)
            return JSONResponse({k: v for k, v in m.items() if k != "password_hash"})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/members/{member_id}")
async def remove_member(member_id: str):
    data = _load()
    data["members"] = [m for m in data["members"] if m["id"] != member_id]
    _save(data)
    return JSONResponse({"ok": True})


@router.get("/roles")
def list_roles():
    return JSONResponse(ROLES)


@router.get("/activity")
def get_activity():
    return JSONResponse(_load()["activity"][-50:])

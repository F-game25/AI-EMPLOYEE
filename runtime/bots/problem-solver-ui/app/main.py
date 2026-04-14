from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.middleware.auth import create_token, verify_login, verify_token
from app.routes import agents, guardrails, integrations, memory, metrics, scheduler, skills, tasks
from app.schemas import LoginRequest, LoginResponse
from app.state import store
from app.websocket import router as ws_router

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[3]
LOCAL_FRONTEND_DIR = APP_DIR.parent / "frontend"
REPO_FRONTEND_DIR = REPO_ROOT / "frontend"


def _resolve_frontend_dir() -> Path:
    if (LOCAL_FRONTEND_DIR / "package.json").exists():
        return LOCAL_FRONTEND_DIR
    return REPO_FRONTEND_DIR


def _resolve_static_dir() -> Path:
    default_static = APP_DIR.parent / "frontend" / "dist"
    if default_static.exists():
        return default_static
    fallback_static = REPO_FRONTEND_DIR / "dist"
    return fallback_static


def _ensure_frontend_build(static_dir: Path) -> None:
    if (static_dir / "index.html").exists():
        return

    frontend_dir = _resolve_frontend_dir()
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        print(f"[ui-startup] frontend package not found at {frontend_dir}", flush=True)
        return

    print(f"[ui-startup] dist missing, rebuilding frontend in {frontend_dir}", flush=True)
    try:
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
        subprocess.run(["npm", "run", "build"], cwd=frontend_dir, check=True)
    except Exception as exc:  # pragma: no cover - defensive startup diagnostics
        print(f"[ui-startup] frontend build failed: {exc}", flush=True)


STATIC_DIR = str(_resolve_static_dir())
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="AI Employee Dashboard API", version="1.0.0")

_cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:8787,http://localhost:8787",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def log_route_failures(request: Request, call_next):
    response = await call_next(request)
    if response.status_code >= 400:
        print(f"[route-failure] {request.method} {request.url.path} -> {response.status_code}", flush=True)
    return response


@app.on_event("startup")
async def startup_bus_subscriptions() -> None:
    _ensure_frontend_build(Path(STATIC_DIR))
    for ch in ("tasks", "results", "notifications", "logs"):
        await store.bus.subscribe(ch)


@app.get("/")
async def serve_ui():
    if not os.path.isdir(STATIC_DIR) or not os.path.exists(INDEX_FILE):
        print("STATIC_DIR:", STATIC_DIR, flush=True)
        try:
            print("FILES:", os.listdir(STATIC_DIR), flush=True)
        except Exception as exc:  # pragma: no cover - diagnostics only
            print(f"FILES: <unavailable> ({exc})", flush=True)
        raise HTTPException(status_code=503, detail="Frontend build not found")
    return FileResponse(INDEX_FILE)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    if not verify_login(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token, expires_at = create_token(req.username, expires_hours=24)
    return LoginResponse(access_token=token, expires_at=expires_at)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path == "/" or request.url.path.startswith("/static"):
        print(f"[static-error] {request.url.path}: {exc.detail}", flush=True)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(tasks.router, dependencies=[Depends(verify_token)])
app.include_router(agents.router, dependencies=[Depends(verify_token)])
app.include_router(metrics.router, dependencies=[Depends(verify_token)])
app.include_router(scheduler.router, dependencies=[Depends(verify_token)])
app.include_router(integrations.router, dependencies=[Depends(verify_token)])
app.include_router(skills.router, dependencies=[Depends(verify_token)])
app.include_router(memory.router, dependencies=[Depends(verify_token)])
app.include_router(guardrails.router, dependencies=[Depends(verify_token)])
app.include_router(ws_router)

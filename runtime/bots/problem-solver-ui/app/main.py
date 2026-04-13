from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.auth import create_token, verify_login, verify_token
from app.routes import agents, guardrails, integrations, memory, metrics, scheduler, skills, tasks
from app.schemas import GenericMessage, LoginRequest, LoginResponse
from app.state import store
from app.websocket import router as ws_router

app = FastAPI(title="AI Employee Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_bus_subscriptions() -> None:
    for ch in ("tasks", "results", "notifications", "logs"):
        await store.bus.subscribe(ch)


@app.get("/health", response_model=GenericMessage)
def health() -> GenericMessage:
    return GenericMessage(message="ok")


@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    if not verify_login(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token, expires_at = create_token(req.username, expires_hours=24)
    return LoginResponse(access_token=token, expires_at=expires_at)


app.include_router(tasks.router, dependencies=[Depends(verify_token)])
app.include_router(agents.router, dependencies=[Depends(verify_token)])
app.include_router(metrics.router, dependencies=[Depends(verify_token)])
app.include_router(scheduler.router, dependencies=[Depends(verify_token)])
app.include_router(integrations.router, dependencies=[Depends(verify_token)])
app.include_router(skills.router, dependencies=[Depends(verify_token)])
app.include_router(memory.router, dependencies=[Depends(verify_token)])
app.include_router(guardrails.router, dependencies=[Depends(verify_token)])
app.include_router(ws_router)

@echo off
REM ──────────────────────────────────────────────────────────────────
REM  ASCEND AI — One-command launcher (Windows)
REM  Installs deps, builds frontend, starts backend on port 8787,
REM  then opens the browser.
REM ──────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend
set FRONTEND_DIR=%SCRIPT_DIR%frontend
if "%ASCEND_PORT%"=="" set ASCEND_PORT=8787
set PORT=%ASCEND_PORT%

echo.
echo   ╔═══════════════════════════════════════╗
echo   ║         A S C E N D   A I             ║
echo   ║   Autonomous Business Assistant       ║
echo   ╚═══════════════════════════════════════╝
echo.

REM ── 1. Python dependencies ─────────────────────────────────────────
echo [ASCEND] Installing Python dependencies...
pip install -q -r "%SCRIPT_DIR%requirements.txt" 2>nul

REM ── 2. Build frontend (if source exists) ───────────────────────────
if exist "%FRONTEND_DIR%\package.json" (
    echo [ASCEND] Building frontend...
    cd /d "%FRONTEND_DIR%"
    call npm install --silent 2>nul
    call npm run build 2>nul

    if exist "%FRONTEND_DIR%\dist" (
        if exist "%BACKEND_DIR%\static" rmdir /s /q "%BACKEND_DIR%\static"
        xcopy /e /i /q "%FRONTEND_DIR%\dist" "%BACKEND_DIR%\static" >nul
        echo [ASCEND] Frontend build copied to backend\static\
    )
    cd /d "%SCRIPT_DIR%"
) else (
    echo [ASCEND] No frontend source found — serving API only.
)

REM ── 3. Launch backend ──────────────────────────────────────────────
echo [ASCEND] Starting backend on port %PORT%...
cd /d "%BACKEND_DIR%"

REM Open browser after a short delay
start /b cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:%PORT%"

python -m uvicorn main:app --host 0.0.0.0 --port %PORT% --reload

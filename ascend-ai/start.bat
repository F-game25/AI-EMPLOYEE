@echo off
REM ──────────────────────────────────────────────────────────────────
REM  ASCEND AI — One-command launcher (Windows)
REM ──────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
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
cd /d "%SCRIPT_DIR%backend"
pip install -r ..\requirements.txt -q
cd /d "%SCRIPT_DIR%"

REM ── 2. Build frontend (if source exists) ───────────────────────────
if exist "%SCRIPT_DIR%frontend\package.json" (
    echo [ASCEND] Building frontend...
    cd /d "%SCRIPT_DIR%frontend"
    if not exist node_modules npm install
    npm run build
    cd /d "%SCRIPT_DIR%"
)

REM ── 3. Launch backend ──────────────────────────────────────────────
echo [ASCEND] Starting backend on port %PORT%...
start /B python "%SCRIPT_DIR%backend\main.py"
timeout /t 6 /nobreak > nul
start http://localhost:%PORT%
echo ASCEND AI running. Close window to stop.
pause

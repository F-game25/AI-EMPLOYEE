@echo off
REM AI Employee — Windows Launcher
REM
REM Option A (RECOMMENDED): Docker Desktop — no Python/Node install needed
REM   docker-start.bat
REM
REM Option B: Native — requires Node.js 20+, Python 3.11+, Git Bash or WSL
REM   This script tries Docker first, then Git Bash/WSL, then native Node.
setlocal enabledelayedexpansion

set REPO_ROOT=%~dp0
cd /d "%REPO_ROOT%"
set UI_PORT=8787
set UI_URL=http://localhost:%UI_PORT%

echo.
echo  ======================================================
echo.
echo      A I   E M P L O Y E E
echo      Autonomous AI Workforce Platform
echo      v0.1  --  github.com/F-game25/AI-EMPLOYEE
echo.
echo  ======================================================
echo.

REM ── Option A: Docker (recommended, zero deps) ───────────────────────────────
where docker >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  docker info >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    echo [Docker] Docker detected. Starting with Docker Compose...
    call :start_docker
    goto :open_browser
  ) else (
    echo [WARN] Docker found but not running. Start Docker Desktop and retry, or continue with native mode.
  )
)

REM ── Option B: Git Bash ──────────────────────────────────────────────────────
if exist "C:\Program Files\Git\bin\bash.exe" (
  echo [Git Bash] Starting via Git Bash...
  start "AI Employee" "C:\Program Files\Git\bin\bash.exe" --login -c "cd '%REPO_ROOT:\=/%' && bash start.sh"
  goto :open_browser
)
if exist "C:\Program Files (x86)\Git\bin\bash.exe" (
  echo [Git Bash] Starting via Git Bash (x86)...
  start "AI Employee" "C:\Program Files (x86)\Git\bin\bash.exe" --login -c "cd '%REPO_ROOT:\=/%' && bash start.sh"
  goto :open_browser
)

REM ── Option C: WSL ───────────────────────────────────────────────────────────
where wsl >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  echo [WSL] Starting via WSL...
  for /f "delims=" %%i in ('wsl wslpath -a "%REPO_ROOT%"') do set WSL_PATH=%%i
  start "AI Employee" wsl bash -c "cd '!WSL_PATH!' && bash start.sh"
  goto :open_browser
)

REM ── Option D: Pure native Node + Python ─────────────────────────────────────
echo [Native] No Docker/Git Bash/WSL found. Attempting native startup...
call :start_native
goto :open_browser

REM ═══════════════════════════════════════════════════════════════════════════
:start_docker
  set ENV_FILE=%USERPROFILE%\.ai-employee\.env
  if not exist "%USERPROFILE%\.ai-employee" mkdir "%USERPROFILE%\.ai-employee"
  if not exist "%ENV_FILE%" (
    echo [Docker] Creating default .env at %ENV_FILE%
    echo JWT_SECRET_KEY=> "%ENV_FILE%"
    for /f %%i in ('python -c "import secrets; print(secrets.token_hex(32))" 2^>nul') do (
      echo JWT_SECRET_KEY=%%i> "%ENV_FILE%"
    )
    echo ANTHROPIC_API_KEY=>> "%ENV_FILE%"
    echo OPENROUTER_API_KEY=>> "%ENV_FILE%"
    echo LLM_BACKEND=anthropic>> "%ENV_FILE%"
  )
  copy "%ENV_FILE%" ".env.local" >nul 2>&1
  docker compose -f docker-compose.dev.yml up --build -d
  if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker Compose failed. Check docker-compose.dev.yml exists.
    pause
    exit /b 1
  )
  goto :eof

:start_native
  where node >nul 2>&1 || (echo [ERROR] Node.js not found. Get it at https://nodejs.org && pause && exit /b 1)
  where python >nul 2>&1 || where python3 >nul 2>&1 || (echo [ERROR] Python 3.11+ not found. Get it at https://python.org && pause && exit /b 1)

  set AI_HOME=%USERPROFILE%\.ai-employee
  if not exist "%AI_HOME%" mkdir "%AI_HOME%"
  if not exist "%AI_HOME%\state" mkdir "%AI_HOME%\state"
  if not exist "%AI_HOME%\logs" mkdir "%AI_HOME%\logs"
  if not exist "%AI_HOME%\run" mkdir "%AI_HOME%\run"

  set ENV_FILE=%AI_HOME%\.env
  if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
      set "line=%%A"
      if not "!line:~0,1!"=="#" if not "%%A"=="" set "%%A=%%B"
    )
  )

  if "%JWT_SECRET_KEY%"=="" (
    for /f %%i in ('python -c "import secrets; print(secrets.token_hex(32))" 2^>nul') do set JWT_SECRET_KEY=%%i
    echo JWT_SECRET_KEY=!JWT_SECRET_KEY!>> "%ENV_FILE%"
  )

  if not exist "backend\node_modules" (
    echo [Native] Installing Node.js dependencies...
    cd backend && npm install --omit=dev && cd ..
  )

  if not exist "frontend\dist\index.html" (
    echo [Native] Building frontend...
    cd frontend && npm install && npm run build && cd ..
  )

  if exist "runtime\agents\problem-solver-ui\requirements.txt" (
    echo [Native] Installing Python dependencies...
    python -m pip install -q -r runtime\agents\problem-solver-ui\requirements.txt 2>nul || python3 -m pip install -q -r runtime\agents\problem-solver-ui\requirements.txt
  )

  set PYTHON_PORT=18790
  set PYTHONPATH=%REPO_ROOT%;%REPO_ROOT%\runtime
  echo [Native] Starting Python AI backend on :%PYTHON_PORT%...
  start "AI Employee - Python Backend" /min python -m uvicorn "runtime.agents.problem-solver-ui.server:app" --host 127.0.0.1 --port %PYTHON_PORT% --log-level warning

  echo [Native] Waiting for Python backend (15s max)...
  set /a TRIES=0
  :wait_py
    timeout /t 1 /nobreak >nul
    set /a TRIES+=1
    curl -sf http://127.0.0.1:%PYTHON_PORT%/health >nul 2>&1 && goto py_ready
    if !TRIES! lss 15 goto wait_py
    echo [WARN] Python backend slow — chat will fall back to stubs until ready.
  :py_ready

  set PORT=%UI_PORT%
  set NODE_ENV=production
  echo [Native] Starting Node.js server...
  start "AI Employee - Node Server" node backend\server.js
  goto :eof

REM ═══════════════════════════════════════════════════════════════════════════
:open_browser
  echo.
  echo  Waiting for server to start...
  timeout /t 6 /nobreak >nul
  echo  Opening %UI_URL% in your browser...
  start "" "%UI_URL%"
  echo.
  echo  AI Employee is running.
  echo  Dashboard: %UI_URL%
  echo  To stop:   run stop.bat  (or close the terminal windows above)
  echo.
  pause >nul
  endlocal

@echo off
REM AI Employee — Windows Launcher
REM Starts the AI Employee system and opens the UI in your browser.
setlocal

set AI_HOME=%USERPROFILE%\.ai-employee
set UI_PORT=8787
set UI_URL=http://127.0.0.1:%UI_PORT%

echo.
echo  ======================================================
echo    AI Employee — Starting...
echo  ======================================================
echo.

REM Check installation
if not exist "%AI_HOME%\start.sh" (
    echo ERROR: AI Employee is not installed.
    echo Run install.bat first.
    pause
    exit /b 1
)

REM ── Try Git Bash ────────────────────────────────────────────────────────────
set GIT_BASH=""
if exist "C:\Program Files\Git\bin\bash.exe" (
    set GIT_BASH="C:\Program Files\Git\bin\bash.exe"
    goto :run_gitbash
)
if exist "C:\Program Files (x86)\Git\bin\bash.exe" (
    set GIT_BASH="C:\Program Files (x86)\Git\bin\bash.exe"
    goto :run_gitbash
)

REM ── Try WSL ─────────────────────────────────────────────────────────────────
where wsl >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Starting via WSL...
    start "AI Employee" wsl bash -c "cd ~ && ~/.ai-employee/start.sh"
    goto :open_browser
)

REM ── Try bash in PATH ────────────────────────────────────────────────────────
where bash >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Starting via bash...
    start "AI Employee" bash -c "~/.ai-employee/start.sh"
    goto :open_browser
)

echo ERROR: No Bash environment found.
echo Install Git for Windows: https://git-scm.com/download/win
pause
exit /b 1

:run_gitbash
echo Starting via Git Bash...
start "AI Employee" %GIT_BASH% --login -c "~/.ai-employee/start.sh"
goto :open_browser

:open_browser
echo Waiting for UI to start...
timeout /t 8 /nobreak >nul

REM Open UI in default browser
echo Opening AI Employee UI: %UI_URL%
start "" "%UI_URL%"

echo.
echo AI Employee is running in the background.
echo To stop: close the AI Employee terminal window.
echo.
pause >nul
endlocal

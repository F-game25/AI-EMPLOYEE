@echo off
REM run.bat — Windows launcher for AI-Employee
REM Double-click to start the bootstrap server and open browser

setlocal enabledelayedexpansion
set PORT=8787
set URL=http://localhost:%PORT%

cd /d "%~dp0"

REM Start bootstrap server
echo.
echo ╔════════════════════════════════════════════╗
echo ║  🤖 AI-Employee Starting                   ║
echo ║  Opening browser: %URL%
echo ║  Close this window when finished            ║
echo ╚════════════════════════════════════════════╝
echo.

REM Start node in background
start "AI-Employee Bootstrap Server" cmd /k node bootstrap.js

REM Wait a moment and open browser
timeout /t 2 /nobreak
start %URL%

REM Keep this window open
pause

@echo off
REM AI Employee — Windows Stop Script
setlocal

echo.
echo  Stopping AI Employee...
echo.

REM Stop Docker if running
where docker >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  docker info >nul 2>&1
  if %ERRORLEVEL% EQU 0 (
    docker compose -f docker-compose.dev.yml down 2>nul
    echo  [Docker] Containers stopped.
  )
)

REM Kill native Node + Python processes
taskkill /f /fi "WINDOWTITLE eq AI Employee*" >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8787 " ^| findstr "LISTENING"') do (
  taskkill /f /pid %%P >nul 2>&1
  echo  [Native] Killed Node server (PID %%P)
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":18790 " ^| findstr "LISTENING"') do (
  taskkill /f /pid %%P >nul 2>&1
  echo  [Native] Killed Python backend (PID %%P)
)

echo.
echo  AI Employee stopped.
echo.
pause >nul
endlocal

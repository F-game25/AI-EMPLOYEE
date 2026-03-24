@echo off
REM AI Employee — Windows Quick Installer
REM One-click: downloads and runs install-windows.ps1
REM Double-click this file to install AI Employee on Windows

setlocal

echo.
echo  ======================================================
echo    AI Employee — Windows One-Click Installer
echo  ======================================================
echo.

REM ── Check PowerShell ──────────────────────────────────────────────────────────
where powershell >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PowerShell is required but not found.
    echo This is unusual - PowerShell ships with Windows 7+.
    echo Please install PowerShell: https://aka.ms/install-powershell
    pause
    exit /b 1
)

REM ── Create temp directory ─────────────────────────────────────────────────────
set TEMP_DIR=%TEMP%\ai-employee-install-%RANDOM%
mkdir "%TEMP_DIR%" 2>nul

REM ── Download installer ────────────────────────────────────────────────────────
echo Downloading installer...
powershell -ExecutionPolicy Bypass -Command ^
    "try { (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/windows/install-windows.ps1', '%TEMP_DIR%\install-windows.ps1'); Write-Host 'Download OK' } catch { Write-Host ('Download failed: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Could not download installer.
    echo Please check your internet connection and try again.
    echo Or download manually from:
    echo   https://github.com/F-game25/AI-EMPLOYEE/tree/windows
    echo.
    pause
    exit /b 1
)

REM ── Run installer ─────────────────────────────────────────────────────────────
echo Running installer...
echo.
powershell -ExecutionPolicy Bypass -File "%TEMP_DIR%\install-windows.ps1"

REM ── Cleanup ───────────────────────────────────────────────────────────────────
rmdir /s /q "%TEMP_DIR%" 2>nul

echo.
echo Done. Press any key to exit.
pause >nul
endlocal

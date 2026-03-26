@echo off
REM AI Employee — Windows Installer
REM Runs the PowerShell-based native Windows installer.
setlocal

echo.
echo  ======================================================
echo    AI Employee — Windows Installer v4.0
echo  ======================================================
echo.

REM ── Run PowerShell installer if it exists locally ─────────────────────────────
if exist "%~dp0install-windows.ps1" (
    echo Found: install-windows.ps1
    echo Running native Windows installer...
    echo.
    powershell -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1"
    goto :done
)

REM ── PowerShell installer not found locally — download it ─────────────────────
echo install-windows.ps1 not found. Downloading from GitHub...
set TEMP_DIR=%TEMP%\ai-employee-install-%RANDOM%
mkdir "%TEMP_DIR%" 2>nul

powershell -ExecutionPolicy Bypass -Command ^
    "try { (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/install-windows.ps1', '%TEMP_DIR%\install-windows.ps1'); Write-Host 'Download OK' -ForegroundColor Green } catch { Write-Host ('Download failed: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Could not download install-windows.ps1.
    echo Please check your internet connection, or download manually from:
    echo   https://github.com/F-game25/AI-EMPLOYEE/tree/main
    echo.
    pause
    exit /b 1
)

powershell -ExecutionPolicy Bypass -File "%TEMP_DIR%\install-windows.ps1"
rmdir /s /q "%TEMP_DIR%" 2>nul

:done
echo.
echo Installation finished. Press any key to exit.
pause >nul
endlocal

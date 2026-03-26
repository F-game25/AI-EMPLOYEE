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

REM ── Nothing found ─────────────────────────────────────────────────────────
echo ERROR: No Bash environment found.
echo.
echo To run AI Employee on Windows, install one of:
echo   1. Git for Windows (recommended): https://git-scm.com/download/win
echo      Then re-run this installer.
echo.
echo   2. Windows Subsystem for Linux (WSL):
echo      Run in PowerShell (Admin): wsl --install
echo      Then restart and re-run this installer.
echo.
echo   3. Or use install-windows.ps1 (native PowerShell, no Git Bash needed):
echo      Right-click install-windows.ps1 > "Run with PowerShell"
echo      Or: powershell -ExecutionPolicy Bypass -File install-windows.ps1
pause
exit /b 1

:run_gitbash
echo Found: Git Bash at %GIT_BASH%
echo Running installer...
echo.
%GIT_BASH% --login -c "cd '%~dp0' && bash install.sh"
goto :done

:done
echo.
echo Installation finished. Press any key to exit.
pause >nul
endlocal

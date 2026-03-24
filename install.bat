@echo off
REM AI Employee — Windows Installer
REM Detects Git Bash or WSL and runs the Bash installer.
setlocal

echo.
echo  ======================================================
echo    AI Employee — Windows Installer
echo  ======================================================
echo.

REM ── Try Git Bash (most common on Windows) ──────────────────────────────────
set GIT_BASH=""
if exist "C:\Program Files\Git\bin\bash.exe" (
    set GIT_BASH="C:\Program Files\Git\bin\bash.exe"
    goto :run_gitbash
)
if exist "C:\Program Files (x86)\Git\bin\bash.exe" (
    set GIT_BASH="C:\Program Files (x86)\Git\bin\bash.exe"
    goto :run_gitbash
)

REM ── Try WSL ────────────────────────────────────────────────────────────────
where wsl >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found: Windows Subsystem for Linux (WSL)
    echo Running installer in WSL...
    echo.
    wsl bash -c "cd $(wslpath '%~dp0') && bash install.sh"
    goto :done
)

REM ── Git Bash not in default location — check PATH ─────────────────────────
where bash >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found: bash in PATH
    echo Running installer...
    echo.
    bash install.sh
    goto :done
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
echo   3. Or use install.ps1 (PowerShell):
echo      Right-click install.ps1 > "Run with PowerShell"
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

#Requires -Version 5.1
<#
.SYNOPSIS
    AI Employee — PowerShell Launcher (Windows)
.DESCRIPTION
    Starts the AI Employee system, auto-installs Python if needed, and opens the UI.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File start.ps1
#>

$ErrorActionPreference = 'Continue'
$AI_HOME = Join-Path $env:USERPROFILE ".ai-employee"
$UI_PORT = 8787
$UI_URL  = "http://127.0.0.1:$UI_PORT"

Write-Host ""
Write-Host "  ======================================================" -ForegroundColor Cyan
Write-Host "    AI Employee — Starting (PowerShell launcher)" -ForegroundColor Cyan
Write-Host "  ======================================================" -ForegroundColor Cyan
Write-Host ""

# ── Check installation ──────────────────────────────────────────────────────
if (-not (Test-Path "$AI_HOME\start.sh")) {
    Write-Host "ERROR: AI Employee is not installed." -ForegroundColor Red
    Write-Host "Run install.bat or install.ps1 first." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# ── Check Python ────────────────────────────────────────────────────────────
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") {
            $python = $cmd
            Write-Host "  Python: $ver" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Host "Python 3 not found." -ForegroundColor Yellow
    Write-Host "Installing Python via winget..." -ForegroundColor Cyan
    try {
        winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
        $python = "python"
        Write-Host "  Python installed." -ForegroundColor Green
    } catch {
        Write-Host "Could not auto-install Python." -ForegroundColor Red
        Write-Host "Download it from: https://www.python.org/downloads/" -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── Install fastapi/uvicorn if missing ──────────────────────────────────────
Write-Host "  Checking Python dependencies..." -ForegroundColor Cyan
try {
    & $python -c "import fastapi, uvicorn" 2>$null
    Write-Host "  Dependencies OK." -ForegroundColor Green
} catch {
    Write-Host "  Installing fastapi and uvicorn..." -ForegroundColor Cyan
    & $python -m pip install --user -q fastapi "uvicorn[standard]"
    Write-Host "  Dependencies installed." -ForegroundColor Green
}

# ── Resolve start.sh runner ─────────────────────────────────────────────────
$bash = $null

# Check Git Bash
foreach ($path in @(
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe"
)) {
    if (Test-Path $path) { $bash = $path; break }
}

# Check WSL
if (-not $bash) {
    try {
        $null = Get-Command wsl -ErrorAction Stop
        $bash = "wsl"
    } catch {}
}

# Check bash in PATH
if (-not $bash) {
    try {
        $null = Get-Command bash -ErrorAction Stop
        $bash = "bash"
    } catch {}
}

if (-not $bash) {
    # Fallback: run Python server directly without the full bash environment
    Write-Host ""
    Write-Host "  No Bash found. Starting UI server directly with Python..." -ForegroundColor Yellow
    $serverPath = "$AI_HOME\agents\problem-solver-ui\server.py"
    if (Test-Path $serverPath) {
        $env:AI_HOME = $AI_HOME
        Start-Process -FilePath $python -ArgumentList $serverPath -WindowStyle Normal
        Start-Sleep -Seconds 5
        Write-Host "  Opening UI at $UI_URL" -ForegroundColor Green
        Start-Process $UI_URL
        Write-Host ""
        Write-Host "  AI Employee UI is running." -ForegroundColor Green
        Write-Host "  To stop: close the Python server window." -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 0
    } else {
        Write-Host "ERROR: AI Employee not found at $AI_HOME" -ForegroundColor Red
        Write-Host "Run install.bat first." -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── Start via Bash ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Starting AI Employee via: $bash" -ForegroundColor Cyan
Write-Host ""

if ($bash -eq "wsl") {
    $startCmd = "~/.ai-employee/start.sh"
    Start-Process -FilePath "wsl" -ArgumentList "bash", "-c", $startCmd -WindowStyle Normal
} else {
    $startCmd = "~/.ai-employee/start.sh"
    Start-Process -FilePath $bash -ArgumentList "--login", "-c", $startCmd -WindowStyle Normal
}

# ── Wait and open browser ───────────────────────────────────────────────────
Write-Host "  Waiting for UI (up to 30s)..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri $UI_URL -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}

if ($ready) {
    Write-Host "  UI is ready!" -ForegroundColor Green
} else {
    Write-Host "  UI not responding yet — opening anyway." -ForegroundColor Yellow
}

Write-Host "  Opening $UI_URL" -ForegroundColor Cyan
Start-Process $UI_URL

Write-Host ""
Write-Host "  AI Employee is running." -ForegroundColor Green
Write-Host "  Close the AI Employee terminal window to stop all services." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to exit this launcher"

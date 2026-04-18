#Requires -Version 5.1
<#
.SYNOPSIS
    AI Employee — Windows Startup Script
.DESCRIPTION
    Starts all 33 AI Employee agents natively on Windows using Python directly.
    No WSL or Git Bash required.
.NOTES
    UI Port:        8787 (override with $env:PROBLEM_SOLVER_UI_PORT)
    Dashboard Port: 3000
    Gateway Port:   18789
    Agent manifest: 31 background agents + problem-solver-ui = 32 Python services started
                    (ai-router is a shared module, not a standalone service; total bot count is 33)

    ⚠  WINDOWS SUPPORT STATUS: This script has not yet been fully tested on
       real Windows hardware.  Mac/Linux users are better served by start.sh
       which is production-validated.  If you encounter issues on Windows
       please open a GitHub issue with your PowerShell version and the error output.
#>

$ErrorActionPreference = 'Continue'

# ─── Colour helpers ────────────────────────────────────────────────────────────
function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║        AI Employee — Starting (Windows)          ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step($msg) { Write-Host "▶  $msg" -ForegroundColor White }
function Write-OK($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-Skip($msg) { Write-Host "  [SKIP] $msg" -ForegroundColor DarkGray }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [ERR]  $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host "         $msg" -ForegroundColor DarkCyan }

# ─── Configuration ─────────────────────────────────────────────────────────────
$AI_HOME       = if ($env:AI_HOME) { $env:AI_HOME } else { Join-Path $env:USERPROFILE '.ai-employee' }
$UI_PORT       = if ($env:PROBLEM_SOLVER_UI_PORT) { $env:PROBLEM_SOLVER_UI_PORT } else { '8787' }
$DASHBOARD_PORT = '3000'
$GATEWAY_PORT  = '18789'

# ─── Helper: load a .env file into the current process ─────────────────────────
function Load-EnvFile($path) {
    if (Test-Path $path) {
        Get-Content $path |
            Where-Object { $_ -match '^\s*[^#\s]' -and $_ -match '=' } |
            ForEach-Object {
                $parts = $_ -split '=', 2
                $key   = $parts[0].Trim()
                $val   = $parts[1].Trim().Trim('"').Trim("'")
                [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
            }
    }
}

# ─── Helper: start a bot process ───────────────────────────────────────────────
function Start-Bot {
    param(
        [string]$botName,
        [string]$pyFile,
        [string]$envFile
    )

    $botDir = Join-Path $AI_HOME "agents\$botName"
    $pyPath = Join-Path $botDir $pyFile

    if (-not (Test-Path $pyPath)) {
        Write-Skip "$botName  (not installed)"
        return $null
    }

    Load-EnvFile $envFile

    $logFile = Join-Path $AI_HOME "logs\$botName.log"
    $errLog  = Join-Path $AI_HOME "logs\$botName-err.log"
    $pidFile = Join-Path $AI_HOME "run\$botName.pid"

    try {
        $proc = Start-Process `
            -FilePath $script:python `
            -ArgumentList "`"$pyPath`"" `
            -WorkingDirectory $botDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $logFile `
            -RedirectStandardError  $errLog `
            -PassThru

        if ($proc -and $proc.Id) {
            $proc.Id | Out-File $pidFile -Encoding ASCII -Force
            Write-OK "$botName  (pid $($proc.Id))"
            return $proc
        }
    }
    catch {
        # Fallback: -WindowStyle Hidden is incompatible with redirection on some hosts
        try {
            $proc = Start-Process `
                -FilePath $script:python `
                -ArgumentList "`"$pyPath`"" `
                -WorkingDirectory $botDir `
                -NoNewWindow `
                -RedirectStandardOutput $logFile `
                -RedirectStandardError  $errLog `
                -PassThru

            if ($proc -and $proc.Id) {
                $proc.Id | Out-File $pidFile -Encoding ASCII -Force
                Write-OK "$botName  (pid $($proc.Id))"
                return $proc
            }
        }
        catch {
            Write-Err "$botName  failed to start: $_"
            return $null
        }
    }

    Write-Err "$botName  process did not launch"
    return $null
}

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

Write-Banner

# ─── 1. Check installation ─────────────────────────────────────────────────────
Write-Step "Checking installation…"

if (-not (Test-Path $AI_HOME)) {
    Write-Err "AI Employee home not found: $AI_HOME"
    Write-Host ""
    Write-Host "  Please run the installer first:" -ForegroundColor Yellow
    Write-Host "    PowerShell -ExecutionPolicy Bypass -File install-windows.ps1" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-OK "AI_HOME = $AI_HOME"

# Locate Python
$script:python = $null
foreach ($candidate in @('python', 'python3', 'py')) {
    $ver = & $candidate --version 2>&1 -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -eq 0 -and "$ver" -match 'Python 3') {
        $script:python = $candidate
        Write-OK "Python  = $candidate  ($("$ver".Trim()))"
        break
    }
}

if (-not $script:python) {
    Write-Err "Python 3 not found on PATH."
    Write-Host ""
    Write-Host "  Install Python 3 from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Then re-run this script, or run:" -ForegroundColor Yellow
    Write-Host "    PowerShell -ExecutionPolicy Bypass -File install-windows.ps1" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# ─── 2. Load global .env ───────────────────────────────────────────────────────
Write-Step "Loading environment…"
$globalEnv = Join-Path $AI_HOME '.env'
if (Test-Path $globalEnv) {
    Load-EnvFile $globalEnv
    Write-OK "Loaded $globalEnv"
} else {
    Write-Skip ".env not found (optional)"
}

# Re-read UI port in case it was set in .env
$UI_PORT = if ($env:PROBLEM_SOLVER_UI_PORT) { $env:PROBLEM_SOLVER_UI_PORT } elseif ($env:UI_PORT) { $env:UI_PORT } else { $UI_PORT }

# ─── 3. Create required directories ───────────────────────────────────────────
Write-Step "Creating directories…"
foreach ($dir in @("$AI_HOME\logs", "$AI_HOME\run")) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Write-OK $dir
}

# Collect all process objects for cleanup on exit
$allProcs = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()

# ─── 4. Initialise AI Employee internal engine ─────────────────────────────────
Write-Step "Initialising AI Employee internal engine…"
# The internal engine is fully embedded — no external gateway binary is started.
Write-OK "AI Employee internal engine ready"

# ─── 5. Start static dashboard ─────────────────────────────────────────────────
Write-Step "Starting static dashboard (port $DASHBOARD_PORT)…"

$uiDir     = Join-Path $AI_HOME 'ui'
$dashLog   = Join-Path $AI_HOME 'logs\dashboard.log'
$dashErr   = Join-Path $AI_HOME 'logs\dashboard-err.log'
$dashPid   = Join-Path $AI_HOME 'run\dashboard.pid'

if (Test-Path $uiDir) {
    try {
        $dashProc = Start-Process `
            -FilePath $script:python `
            -ArgumentList "-m http.server $DASHBOARD_PORT --bind 127.0.0.1" `
            -WorkingDirectory $uiDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $dashLog `
            -RedirectStandardError  $dashErr `
            -PassThru

        if ($dashProc -and $dashProc.Id) {
            $dashProc.Id | Out-File $dashPid -Encoding ASCII -Force
            $allProcs.Add($dashProc)
            Write-OK "Dashboard  http://127.0.0.1:$DASHBOARD_PORT  (pid $($dashProc.Id))"
        }
    }
    catch {
        Write-Warn "Dashboard failed to start: $_"
    }
} else {
    Write-Skip "ui/ directory not found — dashboard skipped"
}

# ─── 6. Start Problem Solver UI (CRITICAL — opens in browser) ─────────────────
Write-Step "Starting Problem Solver UI (port $UI_PORT)…"

$psuName   = 'problem-solver-ui'
$psuDir    = Join-Path $AI_HOME "agents\$psuName"
$psuScript = Join-Path $psuDir 'server.py'
$psuEnv    = Join-Path $AI_HOME "config\$psuName.env"
$psuLog    = Join-Path $AI_HOME "logs\$psuName.log"
$psuErr    = Join-Path $AI_HOME "logs\$psuName-err.log"
$psuPid    = Join-Path $AI_HOME "run\$psuName.pid"

if (Test-Path $psuScript) {
    Load-EnvFile $psuEnv
    [System.Environment]::SetEnvironmentVariable('AI_HOME', $AI_HOME, 'Process')

    try {
        $psuProc = Start-Process `
            -FilePath $script:python `
            -ArgumentList "`"$psuScript`"" `
            -WorkingDirectory $psuDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $psuLog `
            -RedirectStandardError  $psuErr `
            -PassThru

        if ($psuProc -and $psuProc.Id) {
            $psuProc.Id | Out-File $psuPid -Encoding ASCII -Force
            $allProcs.Add($psuProc)
            Write-OK "$psuName  http://127.0.0.1:$UI_PORT  (pid $($psuProc.Id))"
        }
    }
    catch {
        # Fallback without -WindowStyle Hidden
        try {
            $psuProc = Start-Process `
                -FilePath $script:python `
                -ArgumentList "`"$psuScript`"" `
                -WorkingDirectory $psuDir `
                -NoNewWindow `
                -RedirectStandardOutput $psuLog `
                -RedirectStandardError  $psuErr `
                -PassThru

            if ($psuProc -and $psuProc.Id) {
                $psuProc.Id | Out-File $psuPid -Encoding ASCII -Force
                $allProcs.Add($psuProc)
                Write-OK "$psuName  http://127.0.0.1:$UI_PORT  (pid $($psuProc.Id)) [fallback]"
            }
        }
        catch {
            Write-Err "$psuName failed to start: $_"
        }
    }
} else {
    Write-Skip "$psuName not installed"
}

# ─── 7. Pause before other agents ────────────────────────────────────────────────
Write-Host ""
Write-Step "Waiting 2 s before starting remaining agents…"
Start-Sleep -Seconds 2

# ─── 8. Bot manifest (name → python file) ─────────────────────────────────────
# Determine whether to start status-reporter. Treat interval <= 0 as disabled.
$statusReporterIntervalRaw = $env:STATUS_REPORT_INTERVAL_SECONDS
$statusReporterEnabled = $true
if ($statusReporterIntervalRaw) {
    $parsedInterval = 0
    if ([int]::TryParse($statusReporterIntervalRaw, [ref]$parsedInterval)) {
        if ($parsedInterval -le 0) {
            $statusReporterEnabled = $false
        }
    }
}

$agents = [ordered]@{}
$agents['problem-solver']        = 'problem_solver.py'
$agents['polymarket-trader']     = 'trader.py'
if ($statusReporterEnabled) {
    $agents['status-reporter']    = 'status_reporter.py'
}
$agents['scheduler-runner']      = 'scheduler.py'
$agents['discovery']             = 'discovery.py'
$agents['skills-manager']        = 'skills_manager.py'
$agents['mirofish-researcher']   = 'researcher.py'
$agents['ollama-agent']          = 'ollama_agent.py'
$agents['claude-agent']          = 'claude_agent.py'
$agents['web-researcher']        = 'web_researcher.py'
$agents['social-media-manager']  = 'social_media_manager.py'
$agents['lead-generator']        = 'lead_generator.py'
$agents['recruiter']             = 'recruiter.py'
$agents['ecom-agent']            = 'ecom_agent.py'
$agents['creator-agency']        = 'creator_agency.py'
$agents['signal-community']      = 'signal_community.py'
$agents['appointment-setter']    = 'appointment_setter.py'
$agents['newsletter-bot']        = 'newsletter_bot.py'
$agents['chatbot-builder']       = 'chatbot_builder.py'
$agents['faceless-video']        = 'faceless_video.py'
$agents['print-on-demand']       = 'print_on_demand.py'
$agents['course-creator']        = 'course_creator.py'
$agents['arbitrage-bot']         = 'arbitrage_bot.py'
$agents['task-orchestrator']     = 'task_orchestrator.py'
$agents['company-builder']       = 'company_builder.py'
$agents['memecoin-creator']      = 'memecoin_creator.py'
$agents['hr-manager']            = 'hr_manager.py'
$agents['finance-wizard']        = 'finance_wizard.py'
$agents['brand-strategist']      = 'brand_strategist.py'
$agents['growth-hacker']         = 'growth_hacker.py'
$agents['project-manager']       = 'project_manager.py'
Write-Step "Starting $($agents.Count) background agents…"
Write-Host ""

$startedCount = 0

foreach ($entry in $agents.GetEnumerator()) {
    $name    = $entry.Key
    $pyFile  = $entry.Value
    $envFile = Join-Path $AI_HOME "config\$name.env"

    $proc = Start-Bot -botName $name -pyFile $pyFile -envFile $envFile
    if ($proc) {
        $allProcs.Add($proc)
        $startedCount++
    }
}

# ─── 9. Wait for UI to be ready ───────────────────────────────────────────────
Write-Host ""
Write-Step "Waiting for UI at http://127.0.0.1:$UI_PORT …"

$uiReady  = $false
$deadline = 30

for ($i = 0; $i -lt $deadline; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$UI_PORT" `
                                  -UseBasicParsing `
                                  -TimeoutSec 2 `
                                  -ErrorAction Stop
        if ($resp.StatusCode -lt 500) {
            $uiReady = $true
            break
        }
    }
    catch { }
    Start-Sleep -Seconds 1
    Write-Host "  …$($i + 1)/$deadline" -NoNewline -ForegroundColor DarkGray
    Write-Host "`r" -NoNewline
}

if ($uiReady) {
    Write-OK "UI is ready!"
} else {
    Write-Warn "UI did not respond within $deadline s — opening browser anyway"
}

# ─── 10. Open browser ──────────────────────────────────────────────────────────
Start-Process "http://127.0.0.1:$UI_PORT"

# ─── 11. Status summary ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ┌──────────────────────────────────────────────────┐" -ForegroundColor Cyan
Write-Host "  │            AI Employee is Running                │" -ForegroundColor Cyan
Write-Host "  ├──────────────────────────────────────────────────┤" -ForegroundColor Cyan
Write-Host ("  │  Bots started : {0,-33}│" -f $startedCount) -ForegroundColor Cyan
Write-Host ("  │  UI           : http://127.0.0.1:{0,-16}│" -f $UI_PORT) -ForegroundColor Cyan
Write-Host ("  │  Dashboard    : http://127.0.0.1:{0,-16}│" -f $DASHBOARD_PORT) -ForegroundColor Cyan
Write-Host ("  │  Gateway      : port {0,-28}│" -f $GATEWAY_PORT) -ForegroundColor Cyan
Write-Host "  ├──────────────────────────────────────────────────┤" -ForegroundColor Cyan
Write-Host "  │  Logs  : %USERPROFILE%\.ai-employee\logs\        │" -ForegroundColor DarkCyan
Write-Host "  │  Stop  : run  Stop AI Employee.bat  on Desktop   │" -ForegroundColor DarkCyan
Write-Host "  │  WhatsApp: configure in dashboard > Settings         │" -ForegroundColor DarkCyan
Write-Host "  └──────────────────────────────────────────────────┘" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop all AI Employee services" -ForegroundColor Yellow
Write-Host ""

# ─── 12. Keep-alive + cleanup on Ctrl+C ───────────────────────────────────────
try {
    while ($true) {
        Start-Sleep -Seconds 5

        # Reload any new PIDs dropped into run/ by agents themselves
        $pidFiles = Get-ChildItem -Path (Join-Path $AI_HOME 'run') -Filter '*.pid' -ErrorAction SilentlyContinue
        foreach ($pf in $pidFiles) {
            $pidVal = (Get-Content $pf.FullName -ErrorAction SilentlyContinue) -as [int]
            if ($pidVal -and $pidVal -gt 0) {
                $existing = $allProcs | Where-Object { $_.Id -eq $pidVal }
                if (-not $existing) {
                    $liveProc = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
                    if ($liveProc) { $allProcs.Add($liveProc) }
                }
            }
        }
    }
}
finally {
    Write-Host ""
    Write-Host "  Stopping AI Employee services…" -ForegroundColor Yellow

    # Kill all tracked processes
    foreach ($proc in $allProcs) {
        if ($proc -and -not $proc.HasExited) {
            try { $proc.Kill() } catch { }
            Write-Info "Stopped pid $($proc.Id)"
        }
    }

    # Also read any remaining PID files and kill those
    $pidFiles = Get-ChildItem -Path (Join-Path $AI_HOME 'run') -Filter '*.pid' -ErrorAction SilentlyContinue
    foreach ($pf in $pidFiles) {
        $pidVal = (Get-Content $pf.FullName -ErrorAction SilentlyContinue) -as [int]
        if ($pidVal -and $pidVal -gt 0) {
            $liveProc = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
            if ($liveProc) {
                try { $liveProc.Kill() } catch { }
                Write-Info "Stopped pid $pidVal  ($($pf.BaseName))"
            }
        }
        Remove-Item $pf.FullName -Force -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Write-OK "All services stopped. Goodbye!"
    Write-Host ""
}

#Requires -Version 5.1
<#
.SYNOPSIS
    AI EMPLOYEE v4.0 - Windows Native Installer
.DESCRIPTION
    One-click installer for AI Employee on Windows (no WSL or Git Bash required).
    Installs Python, Git, OpenClaw, Ollama (optional), all 33 bots, and configures
    everything for immediate use.
.NOTES
    Run as a normal user (not Administrator).
    Execution policy must allow running scripts:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#>

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
$AI_VERSION   = '4.0'
$AI_HOME      = Join-Path $env:USERPROFILE '.ai-employee'
$GITHUB_OWNER = 'F-game25'
$GITHUB_REPO  = 'AI-EMPLOYEE'
$GITHUB_BRANCH = 'main'
$BASE_URL     = "https://raw.githubusercontent.com/$GITHUB_OWNER/$GITHUB_REPO/$GITHUB_BRANCH/runtime"

# ─────────────────────────────────────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
function Write-Banner {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║      AI EMPLOYEE - v$AI_VERSION INSTALLER (Windows)               ║" -ForegroundColor Cyan
    Write-Host "║           Native PowerShell  ·  No WSL Required              ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "▶  $Message" -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Message)
    Write-Host "  ✔  $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  ⚠  $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "  ✘  $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "     $Message" -ForegroundColor White
}

function Test-CommandExists {
    param([string]$Command)
    $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

function Invoke-Download {
    param(
        [string]$Url,
        [string]$Destination
    )
    try {
        $dir = Split-Path $Destination -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        (New-Object System.Net.WebClient).DownloadFile($Url, $Destination)
        return $true
    } catch {
        Write-Warn "Download failed: $Url  ($_)"
        return $false
    }
}

function Invoke-DownloadText {
    param([string]$Url)
    try {
        (New-Object System.Net.WebClient).DownloadString($Url)
    } catch {
        $null
    }
}

function Get-SecureInput {
    param([string]$Prompt)
    $ss = Read-Host $Prompt -AsSecureString
    if ($ss.Length -eq 0) { return '' }
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
    try { [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function New-RandomToken {
    $rng   = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    [Convert]::ToBase64String($bytes) -replace '[^a-zA-Z0-9]', '' | ForEach-Object { $_.Substring(0, [Math]::Min(48, $_.Length)) }
}

function Add-UserPath {
    param([string]$NewPath)
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($current -notlike "*$NewPath*") {
        [Environment]::SetEnvironmentVariable('Path', "$current;$NewPath", 'User')
        $env:PATH += ";$NewPath"
        Write-OK "Added to user PATH: $NewPath"
    } else {
        Write-OK "$NewPath already in PATH"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 – BANNER
# ─────────────────────────────────────────────────────────────────────────────
Write-Banner

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 – REQUIREMENT CHECKS
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Checking requirements..."

# 2a. Must NOT run as Administrator
$currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if ($currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Err "Please run this installer as a NORMAL user, not as Administrator."
    Write-Info "Right-click PowerShell → 'Run as user' (not 'Run as administrator')."
    exit 1
}
Write-OK "Running as normal user: $env:USERNAME"

# 2b. Check Python 3.8+ (minimum); installs 3.12 if absent
$pythonOk = $false
foreach ($cmd in @('python', 'python3', 'py')) {
    if (Test-CommandExists $cmd) {
        $ver = & $cmd --version 2>&1
        if ($ver -match '(\d+)\.(\d+)') {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 8) {
                $PYTHON = $cmd
                $pythonOk = $true
                Write-OK "Python found: $ver"
                break
            }
        }
    }
}
if (-not $pythonOk) {
    Write-Warn "Python 3.8+ not found. Installing via winget..."
    try {
        winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
        # Refresh PATH
        $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
        $PYTHON = 'python'
        Write-OK "Python installed. You may need to restart your shell if commands below fail."
    } catch {
        Write-Err "Could not install Python automatically. Please install from https://python.org and re-run."
        exit 1
    }
} else {
    $PYTHON = if (Test-CommandExists 'python') { 'python' } else { 'py' }
}

# 2c. Check Git (optional)
if (-not (Test-CommandExists 'git')) {
    Write-Warn "Git not found. Installing via winget..."
    try {
        winget install --id Git.Git --silent --accept-source-agreements --accept-package-agreements
        $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
        Write-OK "Git installed."
    } catch {
        Write-Warn "Git installation failed. Continuing without Git – files will be downloaded directly."
    }
} else {
    Write-OK "Git found: $(git --version)"
}

# 2d. Invoke-WebRequest is always present in PowerShell 5.1+ – confirm
Write-OK "Invoke-WebRequest available (built-in)"

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 – INSTALL OPENCLAW
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Installing OpenClaw (WhatsApp gateway)..."

$openClawOk = $false
if (Test-CommandExists 'openclaw') {
    Write-OK "OpenClaw already installed."
    $openClawOk = $true
} else {
    # Try winget first
    try {
        $result = winget install --id OpenClaw.OpenClaw --silent --accept-source-agreements --accept-package-agreements 2>&1
        $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
        if (Test-CommandExists 'openclaw') {
            Write-OK "OpenClaw installed via winget."
            $openClawOk = $true
        }
    } catch { }

    if (-not $openClawOk) {
        Write-Warn "winget install failed. Trying remote install script..."
        try {
            $installScript = Invoke-DownloadText 'https://openclaw.ai/install.ps1'
            if ($installScript) {
                $tmpScript = Join-Path $env:TEMP 'openclaw-install.ps1'
                Set-Content -Path $tmpScript -Value $installScript -Encoding UTF8
                & powershell -ExecutionPolicy Bypass -File $tmpScript
                $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                            [Environment]::GetEnvironmentVariable('Path', 'User')
                if (Test-CommandExists 'openclaw') {
                    Write-OK "OpenClaw installed via remote script."
                    $openClawOk = $true
                }
            }
        } catch {
            Write-Warn "Remote OpenClaw install failed: $_"
        }
    }

    if (-not $openClawOk) {
        Write-Warn "OpenClaw could not be installed automatically."
        Write-Info "Visit https://openclaw.ai to install manually, then re-run if needed."
    }
}

# Add OpenClaw bin to PATH if not already there
$openClawBin = Join-Path $env:LOCALAPPDATA 'OpenClaw\bin'
if (Test-Path $openClawBin) { Add-UserPath $openClawBin }

# Create OpenClaw PS completion stub
$openClawCompDir  = Join-Path $env:USERPROFILE '.openclaw\completions'
$openClawCompFile = Join-Path $openClawCompDir 'openclaw.ps1'
if (-not (Test-Path $openClawCompDir)) {
    New-Item -ItemType Directory -Path $openClawCompDir -Force | Out-Null
}
if (-not (Test-Path $openClawCompFile)) {
    Set-Content -Path $openClawCompFile -Value '# OpenClaw PowerShell completions' -Encoding UTF8
    Write-OK "Created OpenClaw completion stub."
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 4 – CONFIGURATION WIZARD
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Configuration wizard..."
Write-Info "(Press ENTER to accept defaults / leave optional fields blank)"
Write-Host ""

# WhatsApp phone
while ($true) {
    $WHATSAPP_PHONE = Read-Host "  WhatsApp phone number (E.164 format, e.g. +31612345678)"
    if ($WHATSAPP_PHONE -match '^\+\d{1,15}$') { break }
    Write-Warn "  Invalid format. Must start with + followed by 7-15 digits."
}

# Ollama
$useOllama = Read-Host "  Use Ollama (local LLM)? [Y/n]"
$USE_OLLAMA = ($useOllama -ne 'n' -and $useOllama -ne 'N')
$OLLAMA_MODEL = ''
if ($USE_OLLAMA) {
    $OLLAMA_MODEL = Read-Host "  Ollama model name [default: llama3]"
    if ([string]::IsNullOrWhiteSpace($OLLAMA_MODEL)) { $OLLAMA_MODEL = 'llama3' }
}

# API keys (optional, sensitive ones use secure input)
$ANTHROPIC_KEY   = Get-SecureInput "  Anthropic API key (optional, hidden)"
$OPENAI_KEY      = Get-SecureInput "  OpenAI API key (optional, hidden)"
$ALPHA_INSIDER_KEY = Read-Host "  Alpha Insider API key (optional)"
$TAVILY_KEY      = Read-Host "  Tavily API key (optional)"
$NEWSAPI_KEY     = Read-Host "  NewsAPI key (optional)"
$TELEGRAM_TOKEN  = Read-Host "  Telegram Bot Token (optional)"
$DISCORD_WEBHOOK = Read-Host "  Discord Webhook URL (optional)"

# SMTP
$SMTP_HOST = Read-Host "  SMTP host (optional)"
$SMTP_USER = Read-Host "  SMTP user (optional)"
$SMTP_PASS = ''
if (-not [string]::IsNullOrWhiteSpace($SMTP_HOST)) {
    $SMTP_PASS = Get-SecureInput "  SMTP password (optional, hidden)"
}

$ELEVENLABS_KEY = Get-SecureInput "  ElevenLabs API key (optional, hidden)"

# Hourly status
$statusChoice = Read-Host "  Enable hourly status updates? [Y/n]"
$HOURLY_STATUS = ($statusChoice -ne 'n' -and $statusChoice -ne 'N')

# Ports
$dashPortStr = Read-Host "  Dashboard port [default: 3000]"
$DASHBOARD_PORT = if ($dashPortStr -match '^\d+$') { [int]$dashPortStr } else { 3000 }

$uiPortStr = Read-Host "  Problem Solver UI port [default: 8787]"
$UI_PORT = if ($uiPortStr -match '^\d+$') { [int]$uiPortStr } else { 8787 }

# Workers
$workersStr = Read-Host "  Number of worker bots [1-20, default: 20]"
$NUM_WORKERS = if ($workersStr -match '^\d+$' -and [int]$workersStr -ge 1 -and [int]$workersStr -le 20) {
    [int]$workersStr
} else { 20 }

# Generate secure random token
$AI_SECRET_TOKEN = New-RandomToken
Write-OK "Generated random secret token."

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 5 – INSTALL OLLAMA (if chosen)
# ─────────────────────────────────────────────────────────────────────────────
if ($USE_OLLAMA) {
    Write-Step "Installing Ollama..."
    if (Test-CommandExists 'ollama') {
        Write-OK "Ollama already installed."
    } else {
        $ollamaViaWinget = $false
        try {
            winget install --id Ollama.Ollama --silent --accept-source-agreements --accept-package-agreements
            $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                        [Environment]::GetEnvironmentVariable('Path', 'User')
            if (Test-CommandExists 'ollama') {
                Write-OK "Ollama installed via winget."
                $ollamaViaWinget = $true
            }
        } catch { }

        if (-not $ollamaViaWinget) {
            Write-Warn "winget install failed for Ollama. Trying direct download..."
            $ollamaInstaller = Join-Path $env:TEMP 'OllamaSetup.exe'
            $downloaded = Invoke-Download 'https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe' $ollamaInstaller
            if ($downloaded -and (Test-Path $ollamaInstaller)) {
                try {
                    Start-Process -FilePath $ollamaInstaller -ArgumentList '/S' -Wait
                    $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                                [Environment]::GetEnvironmentVariable('Path', 'User')
                    Write-OK "Ollama installed via direct download."
                } catch {
                    Write-Warn "Ollama installer failed: $_"
                }
            } else {
                Write-Warn "Could not download Ollama. Install manually from https://ollama.ai"
            }
        }
    }
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 6 – SETUP DIRECTORIES
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Creating directory structure in $AI_HOME ..."

$AI_DIRS = @(
    'workspace', 'credentials', 'downloads', 'logs', 'ui',
    'backups', 'bin', 'run', 'bots', 'config', 'state', 'improvements'
)
foreach ($d in $AI_DIRS) {
    $path = Join-Path $AI_HOME $d
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}
Write-OK "Directories created."

# Restrict credentials directory ACL
$credDir = Join-Path $AI_HOME 'credentials'
try {
    $acl = Get-Acl $credDir
    $acl.SetAccessRuleProtection($true, $false)       # disable inheritance
    $acl.Access | ForEach-Object { $acl.RemoveAccessRule($_) | Out-Null }
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $env:USERNAME, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'
    )
    $acl.AddAccessRule($rule)
    Set-Acl -Path $credDir -AclObject $acl
    Write-OK "Credentials directory locked to current user."
} catch {
    Write-Warn "Could not set ACL on credentials dir: $_"
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 7 – DOWNLOAD RUNTIME FILES FROM GITHUB
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Downloading runtime files from GitHub ($GITHUB_BRANCH branch)..."

# Mapping: bot-folder-name => python-file-name
$BOT_FILES = [ordered]@{
    'problem-solver'        = 'problem_solver.py'
    'problem-solver-ui'     = 'server.py'
    'polymarket-trader'     = 'trader.py'
    'status-reporter'       = 'status_reporter.py'
    'scheduler-runner'      = 'scheduler.py'
    'discovery'             = 'discovery.py'
    'skills-manager'        = 'skills_manager.py'
    'mirofish-researcher'   = 'researcher.py'
    'ai-router'             = 'ai_router.py'
    'ollama-agent'          = 'ollama_agent.py'
    'claude-agent'          = 'claude_agent.py'
    'web-researcher'        = 'web_researcher.py'
    'social-media-manager'  = 'social_media_manager.py'
    'lead-generator'        = 'lead_generator.py'
    'recruiter'             = 'recruiter.py'
    'ecom-agent'            = 'ecom_agent.py'
    'creator-agency'        = 'creator_agency.py'
    'signal-community'      = 'signal_community.py'
    'appointment-setter'    = 'appointment_setter.py'
    'newsletter-bot'        = 'newsletter_bot.py'
    'chatbot-builder'       = 'chatbot_builder.py'
    'faceless-video'        = 'faceless_video.py'
    'print-on-demand'       = 'print_on_demand.py'
    'course-creator'        = 'course_creator.py'
    'arbitrage-bot'         = 'arbitrage_bot.py'
    'task-orchestrator'     = 'task_orchestrator.py'
    'company-builder'       = 'company_builder.py'
    'memecoin-creator'      = 'memecoin_creator.py'
    'hr-manager'            = 'hr_manager.py'
    'finance-wizard'        = 'finance_wizard.py'
    'brand-strategist'      = 'brand_strategist.py'
    'growth-hacker'         = 'growth_hacker.py'
    'project-manager'       = 'project_manager.py'
}
$BOTS = $BOT_FILES.Keys

# Download start-windows.ps1 launcher (the script that actually starts all bots)
$startScriptUrl  = "https://raw.githubusercontent.com/$GITHUB_OWNER/$GITHUB_REPO/main/start-windows.ps1"
$startScriptDest = Join-Path $AI_HOME 'start-windows.ps1'
$ok = Invoke-Download $startScriptUrl $startScriptDest
if (-not $ok) {
    # Create a minimal launcher so the desktop shortcut works even if download fails
    $fallbackLauncher = @"
# AI Employee Windows Launcher (auto-generated fallback)
`$AI_HOME = "`$env:USERPROFILE\.ai-employee"
`$env:AI_HOME = `$AI_HOME
Get-Content "`$AI_HOME\.env" | ForEach-Object {
    if (`$_ -match '^([^#=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable(`$Matches[1].Trim(), `$Matches[2].Trim(), 'Process')
    }
}
Write-Host 'Starting AI Employee...' -ForegroundColor Cyan
Push-Location `$AI_HOME
`$python = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'py' }
`$uiScript = Join-Path `$AI_HOME 'bots\problem-solver-ui\server.py'
Start-Process `$python -ArgumentList `"`$uiScript`" -WindowStyle Hidden
Start-Sleep 5
Start-Process 'http://127.0.0.1:8787'
Read-Host 'Press Enter to exit'
"@
    Set-Content -Path $startScriptDest -Value $fallbackLauncher -Encoding UTF8
    Write-Warn "start-windows.ps1 not downloaded – created minimal fallback launcher."
}

# Download bot files using correct per-bot filenames
$downloadCount = 0
$failCount = 0
foreach ($bot in $BOTS) {
    $pyFile = $BOT_FILES[$bot]
    $botDir = Join-Path $AI_HOME "bots\$bot"
    if (-not (Test-Path $botDir)) {
        New-Item -ItemType Directory -Path $botDir -Force | Out-Null
    }

    # Main bot Python script (with correct filename)
    $botUrl  = "$BASE_URL/bots/$bot/$pyFile"
    $botDest = Join-Path $botDir $pyFile
    if (Invoke-Download $botUrl $botDest) { $downloadCount++ } else { $failCount++ }

    # requirements.txt (optional)
    $reqUrl  = "$BASE_URL/bots/$bot/requirements.txt"
    $reqDest = Join-Path $botDir 'requirements.txt'
    Invoke-Download $reqUrl $reqDest | Out-Null

    # Config .env file
    $cfgUrl  = "$BASE_URL/config/$bot.env"
    $cfgDest = Join-Path $AI_HOME "config\$bot.env"
    Invoke-Download $cfgUrl $cfgDest | Out-Null
}

# Also download shared config files
$configFiles = @(
    'openclaw.template.json', 'schedules.json', 'polymarket_estimates.json',
    'skills_library.json', 'custom_agents.json', 'agent_capabilities.json',
    'task_plans.json'
)
foreach ($cf in $configFiles) {
    $cfUrl   = "$BASE_URL/config/$cf"
    $cfDest  = Join-Path $AI_HOME "config\$cf"
    Invoke-Download $cfUrl $cfDest | Out-Null
}

Write-OK "Bot files: $downloadCount downloaded, $failCount not found (placeholders created)."

# Ensure every bot directory has at least a placeholder Python script
foreach ($bot in $BOTS) {
    $pyFile  = $BOT_FILES[$bot]
    $pyDest  = Join-Path $AI_HOME "bots\$bot\$pyFile"
    if (-not (Test-Path $pyDest)) {
        $placeholder = @"
# $bot ($pyFile) - placeholder
# The actual bot code will be downloaded when you run the installer connected to GitHub.
import time, os
AI_HOME = os.environ.get('AI_HOME', os.path.expanduser('~/.ai-employee'))
print(f'$bot: waiting for real code. AI_HOME={AI_HOME}')
while True:
    time.sleep(60)
"@
        Set-Content -Path $pyDest -Value $placeholder -Encoding UTF8
    }
}

# Skip bin/ai-employee (Linux shell script – not usable on Windows)
Write-OK "Skipped bin/ai-employee (Linux shell script – use start-windows.ps1 instead)."

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 8 – INSTALL PYTHON DEPENDENCIES
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Installing Python dependencies..."

$corePkgs = @('fastapi', 'uvicorn[standard]', 'requests', 'anthropic', 'python-dotenv', 'httpx')
try {
    & $PYTHON -m pip install --upgrade pip --quiet
    & $PYTHON -m pip install --user @corePkgs --quiet
    Write-OK "Core packages installed."
} catch {
    Write-Warn "pip install failed for core packages: $_"
}

foreach ($bot in $BOTS) {
    $reqFile = Join-Path $AI_HOME "bots\$bot\requirements.txt"
    if (Test-Path $reqFile) {
        try {
            & $PYTHON -m pip install --user -r $reqFile --quiet -ErrorAction SilentlyContinue | Out-Null
        } catch { }
    }
}
Write-OK "Bot dependencies installed."

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 9 – GENERATE CONFIGURATION FILES
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Writing configuration files..."

# 9a. OpenClaw config.json
$openClawConfig = @"
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "host": "127.0.0.1"
  },
  "whatsapp": {
    "phone": "$WHATSAPP_PHONE",
    "session": "ai-employee"
  },
  "security": {
    "token": "$AI_SECRET_TOKEN"
  }
}
"@
Set-Content -Path (Join-Path $AI_HOME 'config.json') -Value $openClawConfig -Encoding UTF8
Write-OK "config.json written."

# 9b. Main .env file
$hourlyVal  = if ($HOURLY_STATUS) { 'true' } else { 'false' }
$ollamaVal  = if ($USE_OLLAMA) { 'true' } else { 'false' }

$envContent = @"
# AI Employee Environment Configuration
# Generated by install-windows.ps1 on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

# Core
AI_HOME=$AI_HOME
AI_SECRET_TOKEN=$AI_SECRET_TOKEN
WHATSAPP_PHONE=$WHATSAPP_PHONE
DASHBOARD_PORT=$DASHBOARD_PORT
UI_PORT=$UI_PORT
NUM_WORKERS=$NUM_WORKERS
HOURLY_STATUS=$hourlyVal

# LLM
USE_OLLAMA=$ollamaVal
OLLAMA_MODEL=$OLLAMA_MODEL
OLLAMA_HOST=http://localhost:11434

# API Keys
ANTHROPIC_API_KEY=$ANTHROPIC_KEY
OPENAI_API_KEY=$OPENAI_KEY
ALPHA_INSIDER_API_KEY=$ALPHA_INSIDER_KEY
TAVILY_API_KEY=$TAVILY_KEY
NEWSAPI_KEY=$NEWSAPI_KEY
ELEVENLABS_API_KEY=$ELEVENLABS_KEY

# Messaging
TELEGRAM_BOT_TOKEN=$TELEGRAM_TOKEN
DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK

# Email (SMTP)
SMTP_HOST=$SMTP_HOST
SMTP_USER=$SMTP_USER
SMTP_PASS=$SMTP_PASS

# OpenClaw Gateway
OPENCLAW_TOKEN=$AI_SECRET_TOKEN
OPENCLAW_PORT=18789
OPENCLAW_HOST=127.0.0.1
"@
Set-Content -Path (Join-Path $AI_HOME '.env') -Value $envContent -Encoding UTF8
Write-OK ".env written."

# 9c. Problem-solver-ui config
$uiEnv = @"
PROBLEM_SOLVER_UI_PORT=$UI_PORT
PROBLEM_SOLVER_UI_HOST=127.0.0.1
SECRET_TOKEN=$AI_SECRET_TOKEN
AI_HOME=$AI_HOME
"@
Set-Content -Path (Join-Path $AI_HOME 'config\problem-solver-ui.env') -Value $uiEnv -Encoding UTF8

# 9d. Status-reporter config
$intervalSecs = if ($HOURLY_STATUS) { 3600 } else { 0 }
$statusEnv = @"
WHATSAPP_PHONE=$WHATSAPP_PHONE
STATUS_REPORT_INTERVAL_SECONDS=$intervalSecs
OPENCLAW_GATEWAY_TOKEN=$AI_SECRET_TOKEN
OPENCLAW_PORT=18789
"@
Set-Content -Path (Join-Path $AI_HOME 'config\status-reporter.env') -Value $statusEnv -Encoding UTF8

Write-OK "Service config files written."

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 10 – STATIC DASHBOARD UI
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Creating dashboard UI..."

# Build bot cards HTML before here-string to avoid complex inline expressions
$botCardsHtml = ($BOTS | ForEach-Object {
    "    <div class='bot-item'><div class='dot'></div>$_</div>"
}) -join "`n"

$htmlContent = @"
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Employee v$AI_VERSION Dashboard</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',Arial,sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}
    header{background:linear-gradient(135deg,#1a2744,#0d1b35);padding:24px 32px;display:flex;align-items:center;gap:16px;border-bottom:1px solid #21262d}
    header h1{font-size:1.6rem;font-weight:700;color:#58a6ff}
    header span{background:#238636;color:#fff;font-size:.75rem;padding:3px 10px;border-radius:12px;font-weight:600}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;padding:24px 32px}
    .card{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:20px}
    .card h2{font-size:.85rem;color:#8b949e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
    .stat{font-size:2rem;font-weight:700;color:#58a6ff}
    .status-dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#3fb950;margin-right:6px;animation:pulse 2s infinite}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    .bot-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;padding:0 32px 32px}
    .bot-item{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px 14px;display:flex;align-items:center;gap:8px;font-size:.85rem}
    .bot-item .dot{width:8px;height:8px;border-radius:50%;background:#3fb950;flex-shrink:0}
    footer{text-align:center;padding:20px;color:#484f58;font-size:.8rem;border-top:1px solid #21262d}
    a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}
  </style>
</head>
<body>
  <header>
    <h1>🤖 AI Employee</h1>
    <span>v$AI_VERSION</span>
    <span style="background:#1f6feb;margin-left:8px">Windows</span>
  </header>
  <div class="grid">
    <div class="card">
      <h2>Status</h2>
      <div style="font-size:1.1rem"><span class="status-dot"></span>Running</div>
    </div>
    <div class="card">
      <h2>Active Bots</h2>
      <div class="stat">$($BOTS.Count)</div>
    </div>
    <div class="card">
      <h2>Problem Solver UI</h2>
      <div><a href="http://127.0.0.1:$UI_PORT" target="_blank">http://127.0.0.1:$UI_PORT</a></div>
    </div>
    <div class="card">
      <h2>WhatsApp</h2>
      <div style="font-size:.95rem;color:#58a6ff">$WHATSAPP_PHONE</div>
    </div>
  </div>
  <h3 style="padding:0 32px 12px;color:#8b949e;font-size:.85rem;text-transform:uppercase;letter-spacing:.06em">Bot Fleet</h3>
  <div class="bot-list">
$botCardsHtml
  </div>
  <footer>AI Employee v$AI_VERSION &nbsp;·&nbsp; <a href="https://github.com/$GITHUB_OWNER/$GITHUB_REPO" target="_blank">GitHub</a></footer>
</body>
</html>
"@
Set-Content -Path (Join-Path $AI_HOME 'ui\index.html') -Value $htmlContent -Encoding UTF8
Write-OK "Dashboard UI written to $AI_HOME\ui\index.html"

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 11 – DESKTOP SHORTCUTS
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Creating Desktop shortcuts..."

$desktop = [Environment]::GetFolderPath('Desktop')

# Start shortcut (.bat)
$startBat = @"
@echo off
powershell -ExecutionPolicy Bypass -WindowStyle Normal -File "%USERPROFILE%\.ai-employee\start-windows.ps1"
"@
Set-Content -Path (Join-Path $desktop 'Start AI Employee.bat') -Value $startBat -Encoding ASCII
Write-OK "Created 'Start AI Employee.bat' on Desktop."

# Stop shortcut (.bat) – kills AI Employee processes using saved PID files
$stopBat = @"
@echo off
echo Stopping AI Employee...
powershell -ExecutionPolicy Bypass -Command "& { `$AI_HOME = Join-Path `$env:USERPROFILE '.ai-employee'; `$runDir = Join-Path `$AI_HOME 'run'; if (Test-Path `$runDir) { Get-ChildItem `$runDir -Filter '*.pid' | ForEach-Object { `$pid = Get-Content `$_.FullName -Raw; try { Stop-Process -Id `$pid -Force -ErrorAction Stop; Write-Host 'Stopped process' `$pid } catch { Write-Host 'PID' `$pid 'already stopped' }; Remove-Item `$_.FullName } } }"
echo AI Employee stopped.
pause
"@
Set-Content -Path (Join-Path $desktop 'Stop AI Employee.bat') -Value $stopBat -Encoding ASCII
Write-OK "Created 'Stop AI Employee.bat' on Desktop."

# Create a .url Internet shortcut for the dashboard (proper URL shortcut format)
try {
    $urlShortcutContent = "[InternetShortcut]`r`nURL=http://localhost:$DASHBOARD_PORT`r`nIconIndex=0`r`n"
    Set-Content -Path (Join-Path $desktop 'AI Employee Dashboard.url') -Value $urlShortcutContent -Encoding ASCII
    Write-OK "Created 'AI Employee Dashboard.url' on Desktop."
} catch {
    Write-Warn "Could not create dashboard URL shortcut: $_"
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 12 – ADD BIN TO USER PATH
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Updating user PATH..."
Add-UserPath (Join-Path $AI_HOME 'bin')

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 13 – PULL OLLAMA MODEL (if applicable)
# ─────────────────────────────────────────────────────────────────────────────
if ($USE_OLLAMA -and (Test-CommandExists 'ollama') -and -not [string]::IsNullOrWhiteSpace($OLLAMA_MODEL)) {
    Write-Step "Pulling Ollama model '$OLLAMA_MODEL' (this may take a while)..."
    try {
        & ollama pull $OLLAMA_MODEL
        Write-OK "Model '$OLLAMA_MODEL' ready."
    } catch {
        Write-Warn "Could not pull model automatically. Run 'ollama pull $OLLAMA_MODEL' later."
    }
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 14 – DONE
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              ✔  INSTALLATION COMPLETE                       ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Configured settings:" -ForegroundColor Cyan
Write-Host "    WhatsApp phone  : $WHATSAPP_PHONE"
Write-Host "    Dashboard port  : $DASHBOARD_PORT"
Write-Host "    UI port         : $UI_PORT"
Write-Host "    Workers         : $NUM_WORKERS"
Write-Host "    Ollama           : $(if ($USE_OLLAMA) { $OLLAMA_MODEL } else { 'disabled' })"
Write-Host "    Install path    : $AI_HOME"
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    1.  Double-click  'Start AI Employee'  on your Desktop"
Write-Host "    2.  Link WhatsApp: run  openclaw channels login"
Write-Host "    3.  Scan the QR code shown in the terminal"
Write-Host "    4.  Send  'Hello!'  to yourself on WhatsApp to verify"
Write-Host ""
Write-Host "  URLs:" -ForegroundColor Cyan
Write-Host "    Dashboard  →  http://localhost:$DASHBOARD_PORT"
Write-Host "    UI         →  http://127.0.0.1:$UI_PORT"
Write-Host ""
Write-Host "  Tip: If scripts are blocked, run once as admin:" -ForegroundColor Yellow
Write-Host "       Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned"
Write-Host ""

# ============================================================
# start_antigravity.ps1
# M4ST × Antigravity — Windows 11 Startup Script
# Version: 6.0 | April 2026
# ============================================================
# Usage: Right-click → Run with PowerShell
#        Or: .\start_antigravity.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "M4ST × Antigravity — Startup"

Write-Host ""
Write-Host "  ███╗   ███╗██╗  ██╗███████╗████████╗" -ForegroundColor Cyan
Write-Host "  ████╗ ████║██║  ██║██╔════╝╚══██╔══╝" -ForegroundColor Cyan
Write-Host "  ██╔████╔██║███████║███████╗   ██║   " -ForegroundColor Cyan
Write-Host "  ██║╚██╔╝██║╚════██║╚════██║   ██║   " -ForegroundColor Cyan
Write-Host "  ██║ ╚═╝ ██║     ██║███████║   ██║   " -ForegroundColor Cyan
Write-Host "  ╚═╝     ╚═╝     ╚═╝╚══════╝   ╚═╝   " -ForegroundColor Cyan
Write-Host ""
Write-Host "  × ANTIGRAVITY MIGRATION v6.0" -ForegroundColor DarkCyan
Write-Host "  × $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
Write-Host ""

# ── CONFIG ──────────────────────────────────────────────────────
$ANTIGRAVITY_DIR = "$env:USERPROFILE\.antigravity"
$MCP_DIR = "$ANTIGRAVITY_DIR\mcps"
$VENV_DIR = "$ANTIGRAVITY_DIR\venv"
$LOG_DIR = "$ANTIGRAVITY_DIR\logs"
$LLAMA_SERVER = "llama-server"  # Must be in PATH or full path

# ── STEP 1: VERIFY DIRS ──────────────────────────────────────────
Write-Host "[1/7] Checking directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $ANTIGRAVITY_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $MCP_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.m4st\memory" | Out-Null
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.m4st\screenshots" | Out-Null
Write-Host "  OK" -ForegroundColor Green

# ── STEP 2: LOAD ENV VARS ────────────────────────────────────────
Write-Host "[2/7] Loading API keys..." -ForegroundColor Yellow
$envFile = "$ANTIGRAVITY_DIR\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.+)$") {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
    Write-Host "  Loaded from $envFile" -ForegroundColor Green
} else {
    Write-Host "  WARNING: .env not found at $envFile" -ForegroundColor Red
    Write-Host "  Create it with your API keys. See .env.example" -ForegroundColor DarkGray
}

# ── STEP 3: PYTHON VENV ──────────────────────────────────────────
Write-Host "[3/7] Python virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
    Write-Host "  Creating venv..." -ForegroundColor DarkGray
    python -m venv $VENV_DIR
    & "$VENV_DIR\Scripts\pip" install --quiet mcp httpx playwright pyautogui pyperclip pygetwindow pillow chromadb scrapling
    & "$VENV_DIR\Scripts\playwright" install chromium
    Write-Host "  Venv created + deps installed" -ForegroundColor Green
} else {
    Write-Host "  Venv exists OK" -ForegroundColor Green
}
$PYTHON = "$VENV_DIR\Scripts\python.exe"

# ── STEP 4: LOCAL LLM (Qwen3-VL for Vision) ─────────────────────
Write-Host "[4/7] Starting local LLM (Qwen3-VL vision)..." -ForegroundColor Yellow
$VISION_MODEL_PATH = "$env:USERPROFILE\.m4st\models\qwen3-vl-7b.gguf"
if (Test-Path $VISION_MODEL_PATH) {
    $llamaArgs = @(
        "--model", $VISION_MODEL_PATH,
        "--port", "8080",
        "--ctx-size", "4096",
        "--n-gpu-layers", "28",    # RTX 2060 Super 8GB — adjust if needed
        "--threads", "8",
        "--mmproj", "$env:USERPROFILE\.m4st\models\qwen3-vl-7b-mmproj.gguf"
    )
    Start-Process -FilePath $LLAMA_SERVER -ArgumentList $llamaArgs `
        -RedirectStandardOutput "$LOG_DIR\vision.log" `
        -RedirectStandardError "$LOG_DIR\vision_err.log" `
        -WindowStyle Hidden
    Write-Host "  Qwen3-VL started on :8080" -ForegroundColor Green
} else {
    Write-Host "  SKIP: Model not found at $VISION_MODEL_PATH" -ForegroundColor DarkGray
    Write-Host "  Vision will use cloud fallback" -ForegroundColor DarkGray
}

# ── STEP 5: MCP SERVERS ──────────────────────────────────────────
Write-Host "[5/7] MCP servers — will be started by Antigravity on demand" -ForegroundColor Yellow
Write-Host "  Registered: mcp_system | mcp_memory | mcp_vision | mcp_browser | mcp_web" -ForegroundColor Green
Write-Host "  Config: $ANTIGRAVITY_DIR\opencode.jsonc" -ForegroundColor DarkGray

# ── STEP 6: VERIFY ANTIGRAVITY CONFIG ───────────────────────────
Write-Host "[6/7] Verifying Antigravity config..." -ForegroundColor Yellow
$configDst = "$ANTIGRAVITY_DIR\opencode.jsonc"
$soulDst = "$ANTIGRAVITY_DIR\SOUL.md"
if (Test-Path $configDst) {
    Write-Host "  opencode.jsonc OK" -ForegroundColor Green
} else {
    Write-Host "  MISSING: Copy config/opencode.jsonc → $configDst" -ForegroundColor Red
}
if (Test-Path $soulDst) {
    Write-Host "  SOUL.md OK" -ForegroundColor Green
} else {
    Write-Host "  MISSING: Copy SOUL.md → $soulDst" -ForegroundColor Red
}

# ── STEP 7: LAUNCH ANTIGRAVITY ───────────────────────────────────
Write-Host "[7/7] Launching Antigravity..." -ForegroundColor Yellow

# Try common Antigravity install paths
$antigravityPaths = @(
    "$env:LOCALAPPDATA\Programs\antigravity\Antigravity.exe",
    "$env:LOCALAPPDATA\antigravity\Antigravity.exe",
    "C:\Program Files\Antigravity\Antigravity.exe",
    "antigravity"   # If in PATH
)

$launched = $false
foreach ($path in $antigravityPaths) {
    if (Test-Path $path -ErrorAction SilentlyContinue) {
        Start-Process $path
        $launched = $true
        Write-Host "  Launched: $path" -ForegroundColor Green
        break
    }
}

if (-not $launched) {
    # Fallback: try to open via code command (VS Code fork behavior)
    try {
        Start-Process "antigravity" -ErrorAction Stop
        $launched = $true
        Write-Host "  Launched via PATH" -ForegroundColor Green
    } catch {
        Write-Host "  Could not find Antigravity. Open manually." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkCyan
Write-Host "  M4ST × ANTIGRAVITY READY" -ForegroundColor Cyan
Write-Host "  Vision LLM   : http://localhost:8080/v1" -ForegroundColor DarkGray
Write-Host "  Memory DB    : ~/.m4st/memory/" -ForegroundColor DarkGray
Write-Host "  Logs         : $LOG_DIR" -ForegroundColor DarkGray
Write-Host "  SOUL.md      : $soulDst" -ForegroundColor DarkGray
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkCyan
Write-Host ""

if ($launched) {
    Write-Host "  Build fast. Ship. Iterate. 👽" -ForegroundColor Cyan
} else {
    Write-Host "  Open Antigravity manually to complete setup." -ForegroundColor Yellow
}

Write-Host ""

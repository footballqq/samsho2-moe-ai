<#
.SYNOPSIS
    Automated clean repository export and open-source packaging tool.
.DESCRIPTION
    Packages all production modules, expert models, savestates, documentation,
    and runner scripts into a clean, zero-clutter directory ready for GitHub publication.
#>

param (
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

if ($OutputDir -eq "") {
    $OutputDir = Join-Path $ProjectRoot "dist\samsho2_ai_release"
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Samurai Shodown II - Clean Repo Export & Packaging" -ForegroundColor Cyan
Write-Host "  Source: $ProjectRoot" -ForegroundColor DarkGray
Write-Host "  Destination: $OutputDir" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

if (Test-Path $OutputDir) {
    Write-Host "[1/6] Cleaning existing destination directory..." -ForegroundColor DarkGray
    Remove-Item -Path $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

# 1. Copy top-level runnable scripts and configs
Write-Host "[2/6] Copying top-level scripts and configs..." -ForegroundColor Green
$TopFiles = @(
    "play_demo.ps1",
    "play_demo.cmd",
    "record_video.ps1",
    "record_video.cmd",
    "README.md",
    "README_EN.md",
    "LICENSE",
    "requirements.txt"
)
foreach ($f in $TopFiles) {
    $src = Join-Path $ProjectRoot $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $OutputDir $f) -Force
    }
}

# Generate clean release-specific .gitignore (never ignores tools/ or essential .sta anchors!)
$ReleaseGitIgnore = @"
# Python / Virtual Environment
.venv/
__pycache__/
*.py[cod]
*$py.class

# Runtime outputs
logs/
videos/
dist/
*.avi
*.mp4
*.log

# Runtime MAME instances (preserve bundled 17 savestate anchors)
data/mame/instance/*
!data/mame/instance/rl/
data/mame/instance/rl/*
!data/mame/instance/rl/state/
data/mame/instance/rl/state/*
!data/mame/instance/rl/state/samsho2/
data/mame/instance/rl/state/samsho2/*
!data/mame/instance/rl/state/samsho2/*.sta

# IDE / OS
.vscode/
.idea/
.DS_Store
Thumbs.db
"@
[System.IO.File]::WriteAllText((Join-Path $OutputDir ".gitignore"), $ReleaseGitIgnore, (New-Object System.Text.UTF8Encoding($false)))

# 2. Copy core production source code (src) - strict whitelist of runtime dependencies
Write-Host "[3/6] Copying core production src/ modules (whitelist)..." -ForegroundColor Green
$DstSrc = Join-Path $OutputDir "src"
New-Item -ItemType Directory -Path $DstSrc -Force | Out-Null
$CoreSrcFiles = @(
    "bo3_controller.py",
    "commentary_engine.py",
    "demo_logger.py",
    "demo_player.py",
    "diff_scan.py",
    "mame_client.py",
    "mame_features_schema.py",
    "mame_gym.py",
    "mame_hitbox.py",
    "mame_hud.py",
    "mame_macro.py",
    "mame_moe.py",
    "mame_nav.py",
    "mame_process.py",
    "mame_protocol.py",
    "mame_reflex.py",
    "mame_screen.py",
    "mame_types.py",
    "moe_roster.py",
    "profiles.py",
    "train_rl.py",
    "watch_agent.py",
    "win32_process.py"
)
foreach ($sf in $CoreSrcFiles) {
    $srcPath = Join-Path $ProjectRoot "src\$sf"
    if (Test-Path $srcPath) {
        Copy-Item -Path $srcPath -Destination $DstSrc -Force
    } else {
        Write-Warning "Core module missing: $srcPath"
    }
}

# 3. Copy models/experts (all 16 verified expert configs + manifest.json, excluding legacy)
Write-Host "[4/6] Copying models/experts/ (16 character experts + manifest)..." -ForegroundColor Green
$DstModels = Join-Path $OutputDir "models\experts"
New-Item -ItemType Directory -Path $DstModels -Force | Out-Null
Get-ChildItem -Path (Join-Path $ProjectRoot "models\experts") -Filter "*.json" | Where-Object {
    $_.Name -notlike "*legacy*"
} | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $DstModels -Force
}

# 4. Copy mame/bridge.lua
Write-Host "[5/6] Copying MAME bridge script..." -ForegroundColor Green
$DstMame = Join-Path $OutputDir "mame"
New-Item -ItemType Directory -Path $DstMame -Force | Out-Null
Copy-Item -Path (Join-Path $ProjectRoot "mame\bridge.lua") -Destination (Join-Path $DstMame "bridge.lua") -Force

# 5. Copy essential savestates (.sta for 16 characters + r1) and movesets (*.yaml)
Write-Host "[6/6] Copying character savestate anchors and movesets..." -ForegroundColor Green
$DstMovesets = Join-Path $OutputDir "data\mame\movesets"
New-Item -ItemType Directory -Path $DstMovesets -Force | Out-Null
$SrcMovesets = Join-Path $ProjectRoot "data\mame\movesets"
if (Test-Path $SrcMovesets) {
    Get-ChildItem -Path $SrcMovesets -Filter "*.yaml" | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $DstMovesets -Force
    }
}
$DstCfg = Join-Path $OutputDir "data\mame\cfg"
New-Item -ItemType Directory -Path $DstCfg -Force | Out-Null
$SrcCfg = Join-Path $ProjectRoot "data\mame\cfg"
if (Test-Path $SrcCfg) {
    Get-ChildItem -Path $SrcCfg -Filter "*.cfg" | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $DstCfg -Force
    }
}
$DstSta = Join-Path $OutputDir "data\mame\instance\rl\state\samsho2"
New-Item -ItemType Directory -Path $DstSta -Force | Out-Null
$StaNames = @(
    "earthquake.sta", "genjuro.sta", "galford.sta", "nakoruru.sta",
    "kyoshiro.sta", "genan.sta", "nicotine.sta", "mizuki.sta",
    "hanzo.sta", "wanfu.sta", "sieger.sta", "haowmaru.sta",
    "chamcham.sta", "ukyo.sta", "jubei.sta", "charlotte.sta", "r1.sta"
)
$SrcStaDir = Join-Path $ProjectRoot "data\mame\instance\rl\state\samsho2"
foreach ($st in $StaNames) {
    $f = Join-Path $SrcStaDir $st
    if (Test-Path $f) {
        Copy-Item -Path $f -Destination (Join-Path $DstSta $st) -Force
    }
}

# Copy documentation and finaldoc (Chinese + English)
$DstFinalDoc = Join-Path $OutputDir "finaldoc"
New-Item -ItemType Directory -Path $DstFinalDoc -Force | Out-Null
Get-ChildItem -Path (Join-Path $ProjectRoot "finaldoc") -Filter "*.md" | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $DstFinalDoc -Force
}
$SrcFinalDocEn = Join-Path $ProjectRoot "finaldoc\en"
if (Test-Path $SrcFinalDocEn) {
    $DstFinalDocEn = Join-Path $DstFinalDoc "en"
    New-Item -ItemType Directory -Path $DstFinalDocEn -Force | Out-Null
    Get-ChildItem -Path $SrcFinalDocEn -Filter "*.md" | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $DstFinalDocEn -Force
    }
}

# Copy tools
$DstTools = Join-Path $OutputDir "tools"
New-Item -ItemType Directory -Path $DstTools -Force | Out-Null
Copy-Item -Path (Join-Path $ProjectRoot "tools\record_match_mp4.py") -Destination $DstTools -Force
Copy-Item -Path (Join-Path $ProjectRoot "tools\export_clean_repo.ps1") -Destination $DstTools -Force

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  Export Complete! Clean Release Directory Created At:" -ForegroundColor Green
Write-Host "  $OutputDir" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Green

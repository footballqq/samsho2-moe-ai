<#
.SYNOPSIS
    Automated MP4 match video recorder for Samurai Shodown II MoE experts.
.DESCRIPTION
    Captures full 60 FPS gameplay and victory celebration of any opponent
    (or all 16 opponents) and encodes to compressed H.264 MP4.
#>

param (
    [string]$Target = "charlotte",
    [string]$Mode = "bo3",
    [int]$Speed = 1,
    [switch]$All,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Resolve-PythonExe {
    if ($env:SAMSHO2_PYTHON -and (Test-Path $env:SAMSHO2_PYTHON)) { return $env:SAMSHO2_PYTHON }
    $cur = $ScriptDir
    for ($i = 0; $i -lt 4 -and $cur; $i++) {
        $cand1 = Join-Path $cur ".venv\Scripts\python.exe"
        if (Test-Path $cand1) { return $cand1 }
        $cand2 = Join-Path $cur "SamuraiShodownII\.venv\Scripts\python.exe"
        if (Test-Path $cand2) { return $cand2 }
        $cur = Split-Path -Parent $cur
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return ""
}

$PythonExe = Resolve-PythonExe
if (-not $PythonExe) {
    Write-Error "Python not found. Create a .venv in this repo, install Python in PATH, or set env:SAMSHO2_PYTHON."
    exit 1
}

$RecorderScript = Join-Path $ScriptDir "tools\record_match_mp4.py"
if (-not (Test-Path $RecorderScript)) {
    Write-Error "record_match_mp4.py not found at: $RecorderScript"
    exit 1
}

$ArgsList = @($RecorderScript)
if ($All) {
    $ArgsList += @("--all")
} else {
    $ArgsList += @("--target", $Target)
}
$ArgsList += @("--mode", $Mode)
$ArgsList += @("--speed", "$Speed")
if ($Force) {
    $ArgsList += @("--force")
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Starting Samurai Shodown II Automated MP4 Video Capture" -ForegroundColor Cyan
Write-Host "  Target: $(if ($All) {'ALL 16 OPPONENTS'} else {$Target})" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

& $PythonExe @ArgsList

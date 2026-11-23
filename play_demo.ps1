<#
.SYNOPSIS
    Samurai Shodown II - MoE Expert Interactive Battle & Spectator Demo.
.DESCRIPTION
    Launches an interactive menu to choose an opponent (e.g. 1: Earthquake)
    and watch the MoE specialized AI fight on screen in a visible MAME window.
#>

param (
    [string]$Target = "",
    [string]$Mode = "bo3",
    [int]$Speed = 1,
    [switch]$Headless,
    [switch]$Human,
    [switch]$HumanP2,
    [switch]$Record
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

$DemoScript = Join-Path $ScriptDir "src\demo_player.py"
if (-not (Test-Path $DemoScript)) {
    Write-Error "demo_player.py not found at: $DemoScript"
    exit 1
}

$ArgsList = @($DemoScript)
if ($Target -ne "") {
    $ArgsList += @("--target", $Target)
    if ($Mode -ne "") {
        $ArgsList += @("--mode", $Mode)
    }
}
if ($Speed -gt 1) {
    $ArgsList += @("--speed", "$Speed")
}
if ($Headless) {
    $ArgsList += @("--headless")
}
if ($Human) {
    $ArgsList += @("--human")
}
if ($HumanP2) {
    $ArgsList += @("--human-p2")
}
if ($Record) {
    $ArgsList += @("--record")
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Starting Samurai Shodown II MoE Spectator Demonstration" -ForegroundColor Cyan
Write-Host "  Directory: $ScriptDir" -ForegroundColor DarkGray
Write-Host "==========================================================" -ForegroundColor Cyan

& $PythonExe @ArgsList

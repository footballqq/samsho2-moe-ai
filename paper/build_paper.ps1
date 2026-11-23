# Build script for the Samurai Shodown II MoE technical paper (pure ASCII)
$ErrorActionPreference = "Stop"
$PaperDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $PaperDir

$PythonExe = "E:\games\SamuraiShodownII\.venv\Scripts\python.exe"
if (Test-Path $PythonExe) {
    Write-Host "[1/2] Regenerating 300-DPI paper figures..." -ForegroundColor Cyan
    & $PythonExe (Join-Path $PaperDir "scripts\generate_figures.py")
}

Write-Host "[2/3] Compiling English PDF with pdflatex (2 passes)..." -ForegroundColor Cyan
& pdflatex -interaction=nonstopmode -halt-on-error samsho2_moe_paper.tex | Out-Null
& pdflatex -interaction=nonstopmode -halt-on-error samsho2_moe_paper.tex | Out-Null

Write-Host "[3/3] Compiling Chinese PDF with xelatex (2 passes)..." -ForegroundColor Cyan
& xelatex -interaction=nonstopmode -halt-on-error samsho2_moe_paper_zh.tex | Out-Null
& xelatex -interaction=nonstopmode -halt-on-error samsho2_moe_paper_zh.tex | Out-Null

foreach ($pdf in @("samsho2_moe_paper.pdf", "samsho2_moe_paper_zh.pdf")) {
    $fp = Join-Path $PaperDir $pdf
    if (Test-Path $fp) {
        $sz = [math]::Round((Get-Item $fp).Length / 1KB, 1)
        Write-Host "SUCCESS: $pdf ($sz KB)" -ForegroundColor Green
    } else {
        Write-Error "PDF generation failed: $pdf"
        exit 1
    }
}

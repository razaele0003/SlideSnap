param([string]$Python = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Python) {
    $Python = if (Test-Path -LiteralPath '.venv\Scripts\python.exe') { '.\.venv\Scripts\python.exe' } else { '..\.venv-slidesnap\Scripts\python.exe' }
}
& $Python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
& $Python -m PyInstaller --noconfirm SlideSnap.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
& $Python tools\package_notices.py
if ($LASTEXITCODE -ne 0) { throw 'License packaging failed.' }
Write-Host 'Built dist\SlideSnap\SlideSnap.exe. Keep the complete folder together.'

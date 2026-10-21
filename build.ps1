param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv-build\Scripts\python.exe')) {
        & $Python -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw 'Creating build environment failed.' }
    }
    $buildPython = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
    & $buildPython -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }
    & $buildPython -m PyInstaller --noconfirm OCSLocalBank.spec
    if ($LASTEXITCODE -ne 0) { throw 'Building EXE failed.' }
    Write-Host 'Build complete. See dist/.'
} finally { Pop-Location }

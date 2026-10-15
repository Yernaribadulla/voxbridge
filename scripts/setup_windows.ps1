$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip update failed.' }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Write-Host 'Run: .\.venv\Scripts\python.exe -m app'
    Write-Host 'Preview without audio or model downloads: .\.venv\Scripts\python.exe -m app --preview'
} finally {
    Pop-Location
}

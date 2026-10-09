$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) { py -3.14 -m venv .venv } else { python -m venv .venv }
if (-not (Test-Path '.\.venv\Scripts\python.exe')) { throw 'Virtual environment was not created' }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host 'Run without activation: .\.venv\Scripts\python.exe -m app'

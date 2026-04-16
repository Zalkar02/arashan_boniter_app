$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$LegacyVenvPython = Join-Path $ProjectDir "env\Scripts\python.exe"

if (Test-Path $VenvPython) {
  $Python = $VenvPython
} elseif (Test-Path $LegacyVenvPython) {
  $Python = $LegacyVenvPython
} else {
  Write-Host "Virtual environment not found."
  Write-Host "Run: .\setup.ps1"
  exit 1
}

Set-Location $ProjectDir

if ((Test-Path "$ProjectDir\sheep_local.example.db") -and -not (Test-Path "$ProjectDir\sheep_local.db")) {
  Copy-Item "$ProjectDir\sheep_local.example.db" "$ProjectDir\sheep_local.db"
}
if ((Test-Path "$ProjectDir\last_sync.example.txt") -and -not (Test-Path "$ProjectDir\last_sync.txt")) {
  Copy-Item "$ProjectDir\last_sync.example.txt" "$ProjectDir\last_sync.txt"
}

& $Python migrate_local_db.py
& $Python app.py
